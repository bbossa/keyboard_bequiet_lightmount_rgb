"""Vendor LED indexes (10:0d) per zone, checked visually on the keyboard."""

UNUSED = (0x62, 0x89)              # never written by IO Center

TOP = range(0x00, 0x2d)            # top strip
KNOB = range(0x2d, 0x2e)           # knob LED
KEYS = [i for i in range(0x2e, 0x9e) if i not in UNUSED]
LEFT = range(0x9e, 0xa3)           # left side strip
RIGHT = range(0xa3, 0xa8)          # right side strip

LAST = 0xa7
ALL = [i for i in range(LAST + 1) if i not in UNUSED]  # 166 LEDs

ZONES = {'top': TOP, 'knob': KNOB, 'keys': KEYS, 'left': LEFT, 'right': RIGHT}  # predefined zones
