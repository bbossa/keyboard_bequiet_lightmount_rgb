"""Key legend and position of each vendor LED index (10:0d), ISO French (AZERTY) layout.

Keys: LampArray positions (interface 3, LampAttributesResponse, lamps-map.tsv) matched
row by row, left to right, with the vendor indexes 2e-9d (numbered the same way).
0x62 is the ANSI backslash slot (no LED), 0x89 is never written by IO Center.
Confirmed on the keyboard, key by key, with `lightmount calibrate` (2026-10-24,
0 mismatch out of 110 keys and the knob).

Strips and knob: drawn positions, not measured (the LampArray has no side strips).

Legends: as printed on the keycaps (be quiet! product image 02_Light_Mount_ISO_FR.jpg).
Positions are key centers in mm, origin top left of the keyboard.
"""
from . import layout

# index: (legend, x, y)
KEYS = {
    0x2e: ('Esc', 19.0, 17.4),
    0x2f: ('F1', 57.0, 17.4),
    0x30: ('F2', 76.0, 17.4),
    0x31: ('F3', 95.0, 17.4),
    0x32: ('F4', 114.0, 17.4),
    0x33: ('F5', 142.5, 17.4),
    0x34: ('F6', 161.5, 17.4),
    0x35: ('F7', 180.5, 17.4),
    0x36: ('F8', 199.5, 17.4),
    0x37: ('F9', 228.0, 17.4),
    0x38: ('F10', 247.0, 17.4),
    0x39: ('F11', 266.0, 17.4),
    0x3a: ('F12', 285.0, 17.4),
    0x3b: ('Print', 310.9, 17.4),
    0x3c: ('Scr Lk', 329.9, 17.4),
    0x3d: ('Pause', 348.9, 17.4),
    0x3e: ('M1', 8.0, 42.7),
    0x3f: ('²', 19.0, 42.7),
    0x40: ('1 &', 38.0, 42.7),
    0x41: ('2 é ~', 57.0, 42.7),
    0x42: ('3 " #', 76.0, 42.7),
    0x43: ("4 ' {", 95.0, 42.7),
    0x44: ('5 ( [', 114.0, 42.7),
    0x45: ('6 - ¦', 133.0, 42.7),
    0x46: ('7 è `', 152.0, 42.7),
    0x47: ('8 _ \\', 171.0, 42.7),
    0x48: ('9 ç ^', 190.0, 42.7),
    0x49: ('0 à @', 209.0, 42.7),
    0x4a: ('° ) ]', 228.0, 42.7),
    0x4b: ('+ = }', 247.0, 42.7),
    0x4c: ('Back', 275.5, 42.7),
    0x4d: ('Ins', 310.9, 42.7),
    0x4e: ('Home', 329.9, 42.7),
    0x4f: ('PgUp', 348.9, 42.7),
    0x50: ('Num', 374.8, 42.7),
    0x51: ('/', 393.8, 42.7),
    0x52: ('*', 412.8, 42.7),
    0x53: ('-', 431.8, 42.7),
    0x54: ('M2', 8.0, 61.7),
    0x55: ('Tab', 23.7, 61.7),
    0x56: ('A', 47.5, 61.7),
    0x57: ('Z', 66.5, 61.7),
    0x58: ('E €', 85.5, 61.7),
    0x59: ('R', 104.5, 61.7),
    0x5a: ('T', 123.5, 61.7),
    0x5b: ('Y', 142.5, 61.7),
    0x5c: ('U', 161.5, 61.7),
    0x5d: ('I', 180.5, 61.7),
    0x5e: ('O', 199.5, 61.7),
    0x5f: ('P', 218.5, 61.7),
    0x60: ('¨ ^', 237.5, 61.7),
    0x61: ('£ $ ¤', 256.5, 61.7),
    0x63: ('Del', 310.9, 61.7),
    0x64: ('End', 329.9, 61.7),
    0x65: ('PgDn', 348.9, 61.7),
    0x66: ('7', 374.8, 61.7),
    0x67: ('8', 393.8, 61.7),
    0x68: ('9', 412.8, 61.7),
    0x69: ('+', 431.8, 61.7),
    0x6a: ('M3', 8.0, 80.7),
    0x6b: ('Caps', 26.1, 80.7),
    0x6c: ('Q', 52.2, 80.7),
    0x6d: ('S', 71.2, 80.7),
    0x6e: ('D', 90.2, 80.7),
    0x6f: ('F', 109.2, 80.7),
    0x70: ('G', 128.2, 80.7),
    0x71: ('H', 147.2, 80.7),
    0x72: ('J', 166.2, 80.7),
    0x73: ('K', 185.2, 80.7),
    0x74: ('L', 204.2, 80.7),
    0x75: ('M', 223.2, 80.7),
    0x76: ('% ù', 242.2, 80.7),
    0x77: ('µ *', 263.1, 80.7),
    0x78: ('Enter', 273.1, 80.7),
    0x79: ('4', 374.8, 80.7),
    0x7a: ('5', 393.8, 80.7),
    0x7b: ('6', 412.8, 80.7),
    0x7c: ('M4', 8.0, 99.7),
    0x7d: ('Shift', 30.9, 99.7),
    0x7e: ('< >', 45.9, 99.7),
    0x7f: ('W', 61.7, 99.7),
    0x80: ('X', 80.7, 99.7),
    0x81: ('C', 99.7, 99.7),
    0x82: ('V', 118.7, 99.7),
    0x83: ('B', 137.7, 99.7),
    0x84: ('N', 156.7, 99.7),
    0x85: ('? ,', 175.7, 99.7),
    0x86: ('. ;', 194.7, 99.7),
    0x87: ('/ :', 213.7, 99.7),
    0x88: ('§ !', 232.7, 99.7),
    0x8a: ('Shift', 268.4, 99.7),
    0x8b: ('↑', 329.9, 99.7),
    0x8c: ('1', 374.8, 99.7),
    0x8d: ('2', 393.8, 99.7),
    0x8e: ('3', 412.8, 99.7),
    0x8f: ('Enter', 431.8, 99.7),
    0x90: ('M5', 8.0, 118.7),
    0x91: ('Ctrl', 21.3, 118.7),
    0x92: ('Win', 45.1, 118.7),
    0x93: ('Alt', 68.8, 118.7),
    0x94: ('Space', 140.1, 118.7),
    0x95: ('Alt Gr', 211.3, 118.7),
    0x96: ('Win', 235.1, 118.7),
    0x97: ('Fn', 258.9, 118.7),
    0x98: ('Ctrl', 282.6, 118.7),
    0x99: ('←', 310.9, 118.7),
    0x9a: ('↓', 329.9, 118.7),
    0x9b: ('→', 348.9, 118.7),
    0x9c: ('0', 384.3, 118.7),
    0x9d: (',', 412.8, 118.7),
}

KNOB = {0x2d: ('Knob', 8.0, 17.4)}

# top strip: 45 LEDs over the width of the 23 LampArray top lamps (8.0 to 431.8 mm)
TOP = {i: (f'Top strip {n + 1}', round(8.0 + n * (431.8 - 8.0) / 44, 1), 3.0)
       for n, i in enumerate(layout.TOP)}

# side strips: 5 LEDs each, top to bottom, outside the key area
LEFT = {i: (f'Left strip {n + 1}', -6.0, 30.0 + n * 20.0) for n, i in enumerate(layout.LEFT)}
RIGHT = {i: (f'Right strip {n + 1}', 446.0, 30.0 + n * 20.0) for n, i in enumerate(layout.RIGHT)}

ALL = {**TOP, **KNOB, **KEYS, **LEFT, **RIGHT}
