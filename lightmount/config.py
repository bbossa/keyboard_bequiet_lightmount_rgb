"""User configuration (~/.config/lightmount/config.toml): loading and validation. No device access.

A zone is either a color string, for the predefined zones of layout.ZONES:
    [zones]
    top = "49412f"
or a table, for any zone:
    [zones.top]
    leds = ["00-2c"]   # vendor LED indexes (hex), single or ranges
    color = "f4dbae"
    dim = 0.3          # 10:0d has no brightness: the color is scaled instead
If the file has a [zones] section, it replaces the default zones entirely.
"""
import os, tomllib

from . import layout

CONFIG = os.path.expanduser('~/.config/lightmount/config.toml')
ALERTS = ('normal', 'critical', 'error')
SOURCES = ('notifications', 'shell')
MAX_DURATION = 60
MAX_POLL = 3600

DEFAULTS = {
    'device': {'usb_path': '', 'allow_unknown_firmware': False},
    'daemon': {'poll_interval': 0, 'reapply_on_effect_key': True},
    'zones': {'top': '49412f', 'knob': 'ff2a00', 'keys': 'ff2a00', 'left': '0000ff', 'right': 'ff0000'},
    'alerts': {'zone': 'top', 'duration': 1.25, 'normal': '00ff00', 'critical': 'ff0000', 'error': 'ff2a00',
               'sources': {'notifications': True, 'shell': True}},
}


class ConfigError(Exception):
    def __init__(self, errors):
        super().__init__('\n'.join(errors))
        self.errors = errors


def rgb(hexcolor):
    return tuple(bytes.fromhex(hexcolor.lstrip('#')))


def read(path=CONFIG):
    """Raw TOML content ({} if the file does not exist)."""
    try:
        with open(path, 'rb') as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise ConfigError([f'{path}: TOML syntax: {e}'])


def validate(raw):
    """Raw TOML → (normalized config, errors, warnings).

    Normalized: {'device': {...}, 'daemon': {'poll_interval', 'reapply_on_effect_key'}, 'zones': {name: {'leds': [int], 'color': (r, g, b)}},
                 'alerts': {'zone', 'duration', 'colors': {kind: rgb}, 'sources': {source: bool}}}
    """
    errors, warnings = [], []
    unknown(raw, ('device', 'daemon', 'zones', 'alerts'), '', errors)

    device = dict(DEFAULTS['device'])
    section = table(raw, 'device', errors)
    unknown(section, device, 'device.', errors)
    if 'usb_path' in section:
        device['usb_path'] = typed(section['usb_path'], str, 'device.usb_path', errors, '')
    if 'allow_unknown_firmware' in section:
        device['allow_unknown_firmware'] = typed(section['allow_unknown_firmware'], bool,
                                                 'device.allow_unknown_firmware', errors, False)

    daemon = dict(DEFAULTS['daemon'])
    section = table(raw, 'daemon', errors)
    unknown(section, daemon, 'daemon.', errors)
    poll = section.get('poll_interval', daemon['poll_interval'])
    if isinstance(poll, bool) or not isinstance(poll, (int, float)) or not (poll == 0 or 1 <= poll <= MAX_POLL):
        errors.append(f'daemon.poll_interval: expected 0 (off) or seconds between 1 and {MAX_POLL}, got {poll!r}')
    else:
        daemon['poll_interval'] = float(poll)
    if 'reapply_on_effect_key' in section:
        daemon['reapply_on_effect_key'] = typed(section['reapply_on_effect_key'], bool,
                                                'daemon.reapply_on_effect_key', errors, True)

    zones = {}
    zone_section = table(raw, 'zones', errors) if 'zones' in raw else DEFAULTS['zones']
    if not zone_section:
        errors.append('zones: no zone defined')
    for name, value in zone_section.items():
        zone = parse_zone(name, value, errors)
        if zone is not None:
            zones[name] = zone

    owner = {}
    for name, zone in zones.items():
        for i in zone['leds']:
            if i in owner and owner[i] != name:
                errors.append(f'zones.{name}: LED {i:02x} is already in zone {owner[i]}')
            owner.setdefault(i, name)
    missing = [i for i in layout.ALL if i not in owner]
    if zones and missing:
        warnings.append(f'LEDs in no zone (keep their previous color, off after a mode switch): '
                        f'{format_leds(missing)}')

    defaults = DEFAULTS['alerts']
    section = table(raw, 'alerts', errors)
    unknown(section, defaults, 'alerts.', errors)
    alerts = {'zone': typed(section.get('zone', defaults['zone']), str, 'alerts.zone', errors, ''),
              'duration': defaults['duration'], 'colors': {}, 'sources': {}}
    if zones and alerts['zone'] not in zones:
        errors.append(f'alerts.zone: no zone named "{alerts["zone"]}" (zones: {", ".join(zones)})')
    duration = section.get('duration', defaults['duration'])
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 0 < duration <= MAX_DURATION:
        errors.append(f'alerts.duration: expected seconds between 0 and {MAX_DURATION}, got {duration!r}')
    else:
        alerts['duration'] = float(duration)
    for kind in ALERTS:
        alerts['colors'][kind] = color(section.get(kind, defaults[kind]), f'alerts.{kind}', errors)
    sources = section.get('sources', {})
    if not isinstance(sources, dict):
        errors.append('alerts.sources: expected a table')
        sources = {}
    unknown(sources, SOURCES, 'alerts.sources.', errors)
    for source in SOURCES:
        alerts['sources'][source] = typed(sources.get(source, defaults['sources'][source]), bool,
                                          f'alerts.sources.{source}', errors, True)

    return {'device': device, 'daemon': daemon, 'zones': zones, 'alerts': alerts}, errors, warnings


def load(path=CONFIG):
    """Validated config; ConfigError lists every problem. Warnings are returned, not raised."""
    cfg, errors, warnings = validate(read(path))
    if errors:
        raise ConfigError([f'{path}: {e}' for e in errors])
    return cfg, warnings


# --- helpers ------------------------------------------------------------------

def unknown(section, allowed, prefix, errors):
    for key in section:
        if key not in allowed:
            errors.append(f'{prefix}{key}: unknown key')


def table(raw, key, errors):
    value = raw.get(key, {})
    if not isinstance(value, dict):
        errors.append(f'{key}: expected a table')
        return {}
    return value


def typed(value, kind, where, errors, fallback):
    if type(value) is not kind:
        errors.append(f'{where}: expected {kind.__name__}, got {value!r}')
        return fallback
    return value


def color(value, where, errors):
    text = value.lstrip('#') if isinstance(value, str) else ''
    if len(text) != 6 or any(c not in '0123456789abcdefABCDEF' for c in text):
        errors.append(f'{where}: expected an RRGGBB color, got {value!r}')
        return (0, 0, 0)
    return rgb(text)


def parse_leds(value, where, errors):
    """["00-2c", "2d", 0x30] → sorted list of indexes."""
    if not isinstance(value, list) or not value:
        errors.append(f'{where}: expected a non-empty list such as ["00-2c", "2d"]')
        return []
    leds = []
    for item in value:
        if isinstance(item, int) and not isinstance(item, bool):
            lo = hi = item
        elif isinstance(item, str):
            first, _, last = item.partition('-')
            try:
                lo, hi = int(first, 16), int(last or first, 16)
            except ValueError:
                errors.append(f'{where}: {item!r} is not a hex index or range')
                continue
        else:
            errors.append(f'{where}: {item!r} is not a hex index or range')
            continue
        if lo > hi:
            errors.append(f'{where}: range {item!r} is reversed')
            continue
        for i in range(lo, hi + 1):
            if i > layout.LAST:
                errors.append(f'{where}: LED {i:02x} out of range (00-{layout.LAST:02x})')
                break
            if i in layout.UNUSED:
                if lo != hi:  # ranges may span the unused indexes, as in the default keys zone
                    continue
                errors.append(f'{where}: LED {i:02x} is not used by the keyboard')
                continue
            leds.append(i)
    if len(set(leds)) != len(leds):
        errors.append(f'{where}: LED listed twice')
    return sorted(set(leds))


def parse_zone(name, value, errors):
    where = f'zones.{name}'
    if isinstance(value, str):
        if name not in layout.ZONES:
            errors.append(f'{where}: "{name}" is not a predefined zone ({", ".join(layout.ZONES)}); '
                          f'use a [{where}] table with leds and color')
            return None
        return {'leds': list(layout.ZONES[name]), 'color': color(value, where, errors)}
    if not isinstance(value, dict):
        errors.append(f'{where}: expected a color string or a table')
        return None
    unknown(value, ('leds', 'color', 'dim'), f'{where}.', errors)
    if 'leds' in value:
        leds = parse_leds(value['leds'], f'{where}.leds', errors)
    elif name in layout.ZONES:
        leds = list(layout.ZONES[name])
    else:
        errors.append(f'{where}: leds missing')
        leds = []
    if 'color' not in value:
        errors.append(f'{where}: color missing')
    rgb_value = color(value.get('color', '000000'), f'{where}.color', errors)
    dim = value.get('dim', 1)
    if isinstance(dim, bool) or not isinstance(dim, (int, float)) or not 0 <= dim <= 1:
        errors.append(f'{where}.dim: expected a number between 0 and 1, got {dim!r}')
        dim = 1
    return {'leds': leds, 'color': tuple(round(c * dim) for c in rgb_value)}


def format_leds(leds):
    """[0, 1, 2, 5] → '00-02, 05'."""
    spans, start = [], None
    for i, led in enumerate(leds):
        if start is None:
            start = led
        if i + 1 == len(leds) or leds[i + 1] != led + 1:
            spans.append(f'{start:02x}' if start == led else f'{start:02x}-{led:02x}')
            start = None
    return ', '.join(spans)
