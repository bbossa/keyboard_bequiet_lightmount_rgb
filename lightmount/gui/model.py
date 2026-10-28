"""Editable zones and alerts, converted from and to the raw TOML tables. No GTK, no device access.

Zones keep the color and the dim factor apart (the file stores both), LEDs are
sets of vendor indexes. A LED is in one zone at most: assigning it to a zone
takes it out of the others. Zones left empty are kept while editing but not
written (an empty `leds` list is invalid).
"""
import copy, re

from .. import config, layout

NAME = re.compile(r'[A-Za-z0-9_-]+')  # bare TOML key: no quoting in the file


class Zone:
    def __init__(self, leds, color, dim=None):
        self.leds, self.color, self.dim = set(leds), color, dim

    @property
    def rgb(self):
        """Rendered color (dim applied), as written to the keyboard."""
        dim = 1 if self.dim is None else self.dim
        return tuple(round(c * dim) for c in config.rgb(self.color))


def hex_color(value):
    """'#FF2A00' → 'ff2a00'; None if not a color."""
    text = value.lstrip('#').lower() if isinstance(value, str) else ''
    return text if len(text) == 6 and all(c in '0123456789abcdef' for c in text) else None


def compact(leds):
    """{0, 1, 2, 0x61, 0x63} → ['00-02', '61-63']: runs follow layout.ALL, so a range may span 62 and 89."""
    order = {led: n for n, led in enumerate(layout.ALL)}
    out, start, prev = [], None, None
    for led in sorted(leds, key=order.__getitem__):
        if start is not None and order[led] == order[prev] + 1:
            prev = led
            continue
        if start is not None:
            out.append(span(start, prev))
        start = prev = led
    if start is not None:
        out.append(span(start, prev))
    return out


def span(lo, hi):
    return f'{lo:02x}' if lo == hi else f'{lo:02x}-{hi:02x}'


class Model:
    def __init__(self, raw):
        """`raw`: TOML content of the config file ({} if none). Problems are collected in `errors`."""
        self.errors = []
        self.zones = {}
        section = raw.get('zones', config.DEFAULTS['zones'])
        if not isinstance(section, dict):
            self.errors.append('zones: expected a table')
            section = {}
        for name, value in section.items():
            zone = self.parse_zone(name, value)
            if zone is not None:
                self.zones[name] = zone
        self.alerts = copy.deepcopy(config.DEFAULTS['alerts'])
        alerts = raw.get('alerts', {})
        if isinstance(alerts, dict):
            for key, value in alerts.items():
                if key == 'sources' and isinstance(value, dict):
                    self.alerts['sources'].update(value)
                elif key in config.ALERTS:
                    self.alerts[key] = hex_color(value) or value
                else:
                    self.alerts[key] = value

    def parse_zone(self, name, value):
        errors = []
        if isinstance(value, str):  # predefined zone given as a plain color
            leds, color, dim = layout.ZONES.get(name, ()), value, None
        elif isinstance(value, dict):
            leds = (config.parse_leds(value['leds'], f'zones.{name}.leds', errors) if 'leds' in value
                    else layout.ZONES.get(name, ()))
            color, dim = value.get('color', '000000'), value.get('dim')
        else:
            self.errors.append(f'zones.{name}: expected a color string or a table')
            return None
        self.errors += errors
        if hex_color(color) is None:
            self.errors.append(f'zones.{name}: {color!r} is not a color')
        return Zone(leds, hex_color(color) or '000000', dim)

    # --- queries ----------------------------------------------------------------------

    def owner(self, led):
        return next((name for name, zone in self.zones.items() if led in zone.leds), None)

    def colors(self):
        """{LED: (r, g, b)} as the keyboard would show them; LEDs in no zone are absent."""
        return {led: zone.rgb for zone in self.zones.values() for led in zone.leds}

    def unassigned(self):
        owned = set().union(*(z.leds for z in self.zones.values())) if self.zones else set()
        return [i for i in layout.ALL if i not in owned]

    def raw(self):
        """{'zones': ..., 'alerts': ...} raw tables, for save.write() and daemon.preview()."""
        zones = {}
        for name, zone in self.zones.items():
            if not zone.leds:
                continue
            table = {'leds': compact(zone.leds), 'color': zone.color}
            if zone.dim is not None and zone.dim != 1:
                table['dim'] = zone.dim
            zones[name] = table
        return {'zones': zones, 'alerts': copy.deepcopy(self.alerts)}

    def validate(self):
        """(errors, warnings) of the config this model would write."""
        _, errors, warnings = config.validate(self.raw())
        empty = [name for name, zone in self.zones.items() if not zone.leds]
        if empty:
            warnings.append(f'empty zones, not saved: {", ".join(empty)}')
        return errors, warnings

    # --- edits ------------------------------------------------------------------------

    def assign(self, leds, name):
        """Put `leds` in zone `name`, taking them out of any other zone."""
        leds = set(leds)
        for other, zone in self.zones.items():
            if other != name:
                zone.leds -= leds
        self.zones[name].leds |= leds

    def unassign(self, leds):
        for zone in self.zones.values():
            zone.leds -= set(leds)

    def new_zone(self, leds, color='ffffff'):
        n = len(self.zones) + 1
        while f'zone{n}' in self.zones:
            n += 1
        name = f'zone{n}'
        self.zones[name] = Zone((), color)
        self.assign(leds, name)
        return name

    def rename(self, old, new):
        """False if `new` is not a valid name or already taken. The alert zone follows."""
        if new == old:
            return True
        if not NAME.fullmatch(new) or new in self.zones:
            return False
        self.zones = {new if k == old else k: v for k, v in self.zones.items()}
        if self.alerts.get('zone') == old:
            self.alerts['zone'] = new
        return True

    def delete(self, name):
        del self.zones[name]
