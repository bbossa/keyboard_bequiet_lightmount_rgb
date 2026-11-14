"""Vendor LED indexes (10:0d) per zone, checked visually on the keyboard.

The module constants describe the default layout (ISO French). `unused(name)` and
the functions below give the same for another layout: the numbering is shared, only
the keys that exist differ (ISO has 77 and 7e, ANSI has 62 instead).
"""

ISO_FR, ANSI_US = 'iso-fr', 'ansi-us'
NAMES = (ISO_FR, ANSI_US)
DEFAULT = ISO_FR

UNUSED = (0x62, 0x89)              # never written by IO Center
UNUSED_BY_LAYOUT = {
    ISO_FR: UNUSED,
    ANSI_US: (0x77, 0x7e, 0x89),   # ANSI has no ISO key 77 and 7e; 62 is its backslash key
}

TOP = range(0x00, 0x2d)            # top strip
KNOB = range(0x2d, 0x2e)           # knob LED
KEYS = [i for i in range(0x2e, 0x9e) if i not in UNUSED]
LEFT = range(0x9e, 0xa3)           # left side strip
RIGHT = range(0xa3, 0xa8)          # right side strip

LAST = 0xa7
ALL = [i for i in range(LAST + 1) if i not in UNUSED]  # 166 LEDs

ZONES = {'top': TOP, 'knob': KNOB, 'keys': KEYS, 'left': LEFT, 'right': RIGHT}  # predefined zones


def unused(name=DEFAULT):
    return UNUSED_BY_LAYOUT[name]


def keys(name=DEFAULT):
    return [i for i in range(0x2e, 0x9e) if i not in unused(name)]


def all_leds(name=DEFAULT):
    return [i for i in range(LAST + 1) if i not in unused(name)]


def zones(name=DEFAULT):
    return {**ZONES, 'keys': keys(name)}
