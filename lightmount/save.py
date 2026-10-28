"""Write the [zones] and [alerts] tables of the config, keeping the rest of the file. No device access.

tomllib only reads TOML: this writes the few value types the config uses (strings,
booleans, numbers, lists of those, nested tables). The other tables, the comments
above each table and the order of the file are kept, as well as the end-of-line
comment of each key still written; other comments inside the replaced tables are
lost. The result is checked before anything is written: it must parse, pass
config.validate(), and leave every other table unchanged.
"""
import math, os, re, shutil, tempfile, tomllib

from . import config

MANAGED = ('zones', 'alerts')
HEADER = re.compile(r'\s*\[(?!\[)(?P<name>[^\[\]#]+)\]\s*(#.*)?$')
ASSIGNMENT = re.compile(r'\s*(?P<key>[A-Za-z0-9_-]+|"[^"\\]*")\s*=\s*(?P<rest>.*?)\s*$')
BARE_KEY = re.compile(r'[A-Za-z0-9_-]+')


class SaveError(Exception):
    pass


# --- rendering ------------------------------------------------------------------

def key(name):
    if BARE_KEY.fullmatch(name):
        return name
    return string(name)


def string(text):
    escaped = (text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
               .replace('\t', '\\t').replace('\r', '\\r'))
    if any(ord(c) < 0x20 or c == '\x7f' for c in escaped):
        raise SaveError(f'{text!r}: control characters are not supported')
    return f'"{escaped}"'


def value(v, where):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise SaveError(f'{where}: {v!r} is not a finite number')
        return repr(v)
    if isinstance(v, str):
        return string(v)
    if isinstance(v, list):
        return '[' + ', '.join(value(item, where) for item in v) + ']'
    raise SaveError(f'{where}: cannot write a {type(v).__name__}')


def render(path, table, comments=None):
    """{'top': {'leds': ['00-2c'], 'color': 'f4dbae'}} under ('zones',) → TOML text, scalars before subtables.

    `comments`: {(table path, key): (column, '# text')} end-of-line comments to put back."""
    comments = comments or {}
    name = '.'.join(key(part) for part in path)
    lines = [f'[{name}]'] if any(not isinstance(v, dict) for v in table.values()) else []
    subtables = []
    for k, v in table.items():
        if isinstance(v, dict):
            subtables.append((path + (k,), v))
            continue
        line = f'{key(k)} = {value(v, f"{name}.{k}")}'
        if (path, k) in comments:
            column, comment = comments[path, k]
            line = line.ljust(column - 1) + ' ' + comment
        lines.append(line)
    blocks = ['\n'.join(lines)] if lines else []
    blocks += [render(sub, v, comments) for sub, v in subtables]
    return '\n\n'.join(blocks)


# --- replacing the managed tables -------------------------------------------------

def table_path(header):
    """'zones . "top"' → ('zones', 'top'). Quoted parts containing a dot are not supported."""
    return tuple(part.strip().strip('"\'') for part in header.split('.'))


def group(header):
    """'zones.top' → 'zones'; None for a table this module does not manage."""
    first = table_path(header)[0]
    return first if first in MANAGED else None


def inline_comment(rest):
    """'"ff0000"   # red' → (offset of '#', '# red'); None without a comment. A '#' inside a
    value (colors are often written "#ff0000") is skipped: the part before must parse."""
    for i, c in enumerate(rest):
        if c != '#':
            continue
        try:
            tomllib.loads(f'k = {rest[:i]}')
        except tomllib.TOMLDecodeError:
            continue
        return i, rest[i:]
    return None


def end_comments(text):
    """{(table path, key): (column, '# text')} for the keys of the managed tables."""
    out, path = {}, None
    for line in text.splitlines():
        match = HEADER.match(line)
        if match:
            path = table_path(match['name']) if group(match['name']) else None
            continue
        match = ASSIGNMENT.match(line) if path else None
        if match and (found := inline_comment(match['rest'])):
            offset, comment = found
            out[path, match['key'].strip('"')] = (match.start('rest') + offset, comment)
    return out


def segments(text):
    """Lines → [(group or None, comments, body)]: `comments` are the comment and blank
    lines just above a table header, `body` the header and its content. The first
    segment (before any header) has an empty body header."""
    out = [[None, [], []]]
    pending = []  # comment/blank lines: they belong to the next header, if any
    for line in text.splitlines(keepends=True):
        match = HEADER.match(line)
        if match:
            out.append([group(match['name']), pending, [line]])
            pending = []
        elif not line.strip() or line.lstrip().startswith('#'):
            pending.append(line)
        else:
            out[-1][2] += pending + [line]
            pending = []
    out[-1][2] += pending
    return out


def replace(text, rendered):
    """Swap the managed tables of `text` for `rendered` ({group: TOML text}).

    Each group is written where it first appeared, after the comments above it;
    a group the file did not have is appended. The comments above later tables
    of a group are kept, their content is dropped."""
    parts, done = [], set()
    for grp, comments, body in segments(text):
        if grp in done and not any(line.strip() for line in comments):
            continue  # only blank lines between two replaced tables
        parts += comments
        if grp is None:
            parts += body
        elif grp not in done:
            parts.append(rendered[grp] + '\n')
            done.add(grp)
    out = ''.join(parts)
    for grp in MANAGED:
        if grp not in done:
            out = out.rstrip('\n') + ('\n\n' if out.strip() else '') + rendered[grp] + '\n'
    return out


# --- writing ------------------------------------------------------------------------

def dumps(text, zones, alerts):
    """New file content; SaveError or config.ConfigError if it would not be valid."""
    comments = end_comments(text)
    new = replace(text, {grp: render((grp,), table, comments) for grp, table in (('zones', zones), ('alerts', alerts))})
    try:
        before, after = tomllib.loads(text), tomllib.loads(new)
    except tomllib.TOMLDecodeError as e:
        raise SaveError(f'TOML syntax: {e}')
    kept = lambda raw: {k: v for k, v in raw.items() if k not in MANAGED}
    if kept(before) != kept(after) or after.get('zones') != zones or after.get('alerts') != alerts:
        raise SaveError('the file could not be rewritten safely (unusual layout); edit it by hand')
    _, errors, _ = config.validate(after)
    if errors:
        raise config.ConfigError(errors)
    return new


def write(path, zones, alerts, backup=True):
    """Replace [zones] and [alerts] in the config file, atomically.

    The previous file is copied to `<path>.bak` first. Returns the validation warnings."""
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except FileNotFoundError:
        text = None
    new = dumps(text or '', zones, alerts)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    if text is not None and backup:
        shutil.copy2(path, path + '.bak')
    fd, tmp = tempfile.mkstemp(prefix='.config.', suffix='.toml', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(new)
            f.flush()
            os.fsync(f.fileno())
        if text is not None:
            shutil.copymode(path, tmp)
        else:  # mkstemp creates 0600: a new file gets the usual mode (umask)
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return config.validate(tomllib.loads(new))[2]
