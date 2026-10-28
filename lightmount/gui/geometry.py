"""Drawing geometry of the Light Mount, ISO layout, in key units (1 u = 19.05 mm).

keymap.py holds LampArray LED positions, which are not key outlines (the M1-M5
column would overlap Esc): the outlines come from the standard ISO sizes below,
and each row's LEDs are matched left to right with the keys of keymap.py on the
same row, sorted by x. The strips are drawn as segments around the keys.
"""
from .. import keymap, layout

MAIN = 1.25             # left edge of the main block (M1-M5 and the knob are at 0)
NAV = MAIN + 15.25      # Ins/Del/arrows block
PAD = NAV + 3.5         # numeric pad
WIDTH = PAD + 4         # keys area: 0 .. WIDTH
HEIGHT = 6.5            # F row at 0, gap of 0.5, then 5 rows
STRIP = 0.35            # thickness of the strips
STRIP_GAP = 0.45        # between the strips and the keys

TALL, ISO_ENTER = 'tall', 'iso_enter'

# (y, tokens): a number is a key of that width, ('at', x) moves to x,
# ('gap', w) skips w, TALL is a 1 u key two rows high, ISO_ENTER the L-shaped Enter.
ROWS = [
    (0.0, [1, ('at', MAIN), 1, ('gap', 1), 1, 1, 1, 1, ('gap', 0.5), 1, 1, 1, 1, ('gap', 0.5), 1, 1, 1, 1,
           ('at', NAV), 1, 1, 1]),
    (1.5, [1, ('at', MAIN)] + [1] * 13 + [2, ('at', NAV), 1, 1, 1, ('at', PAD), 1, 1, 1, 1]),
    (2.5, [1, ('at', MAIN), 1.5] + [1] * 12 + [('at', NAV), 1, 1, 1, ('at', PAD), 1, 1, 1, TALL]),
    (3.5, [1, ('at', MAIN), 1.75] + [1] * 12 + [ISO_ENTER, ('at', PAD), 1, 1, 1]),
    (4.5, [1, ('at', MAIN), 1.25] + [1] * 11 + [2.75, ('at', NAV + 1), 1, ('at', PAD), 1, 1, 1, TALL]),
    (5.5, [1, ('at', MAIN), 1.25, 1.25, 1.25, 6.25, 1.25, 1.25, 1.25, 1.25, ('at', NAV), 1, 1, 1,
           ('at', PAD), 2, 1]),
]


KEY, KNOB, SEGMENT = 'key', 'knob', 'strip'  # Shape.kind


class Shape:
    """A key, the knob or a strip segment: one or two rectangles (x, y, w, h)."""

    def __init__(self, index, legend, rects, kind=KEY):
        self.index, self.legend, self.rects, self.kind = index, legend, rects, kind

    def contains(self, x, y):
        return any(rx <= x <= rx + rw and ry <= y <= ry + rh for rx, ry, rw, rh in self.rects)

    def intersects(self, x0, y0, x1, y1):
        """Overlap with the rectangle (x0, y0)-(x1, y1), corners in any order."""
        x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        return any(rx < x1 and x0 < rx + rw and ry < y1 and y0 < ry + rh for rx, ry, rw, rh in self.rects)

    @property
    def label_rect(self):
        return self.rects[-1]


def row_leds():
    """{y in mm: [LED index sorted by x]} for the keys, the knob on the F row."""
    rows = {}
    for i, (_, x, y) in {**keymap.KNOB, **keymap.KEYS}.items():
        rows.setdefault(y, []).append((x, i))
    return [[i for _, i in sorted(leds)] for _, leds in sorted(rows.items())]


def keys():
    """Shapes of the knob and the keys."""
    legends = {i: legend for i, (legend, _, _) in {**keymap.KNOB, **keymap.KEYS}.items()}
    rows = row_leds()
    if len(rows) != len(ROWS):
        raise ValueError(f'keymap has {len(rows)} rows, geometry {len(ROWS)}')
    shapes = []
    for (y, tokens), leds in zip(ROWS, rows):
        leds, x = iter(leds), 0.0
        for token in tokens:
            if isinstance(token, tuple):
                kind, value = token
                x = value if kind == 'at' else x + value
                continue
            i = next(leds)
            if token == TALL:
                rects = [(x, y, 1, 2)]
                x += 1
            elif token == ISO_ENTER:  # 1.5 u on the row above, 1.25 u on this one
                rects = [(x - 0.25, y - 1, 1.5, 1), (x, y - 0.01, 1.25, 1.01)]
                x += 1.25
            else:
                rects = [(x, y, token, 1)]
                x += token
            shapes.append(Shape(i, legends[i], rects, KNOB if i in keymap.KNOB else KEY))
        if next(leds, None) is not None:
            raise ValueError(f'row at y={y}: more LEDs than keys')
    return shapes


def strips():
    """Top strip above the keys, side strips left and right, each LED a segment."""
    shapes = []
    top = list(layout.TOP)
    step = WIDTH / len(top)
    for n, i in enumerate(top):
        shapes.append(Shape(i, keymap.TOP[i][0], [(n * step + 0.02, -STRIP_GAP - STRIP, step - 0.04, STRIP)], SEGMENT))
    for leds, x in ((layout.LEFT, -STRIP_GAP - STRIP), (layout.RIGHT, WIDTH + STRIP_GAP)):
        leds = list(leds)
        step = HEIGHT / len(leds)
        for n, i in enumerate(leds):
            shapes.append(Shape(i, keymap.ALL[i][0], [(x, n * step + 0.02, STRIP, step - 0.04)], SEGMENT))
    return shapes


def shapes():
    return keys() + strips()


# whole drawing, strips included: x0, y0, x1, y1
BOUNDS = (-STRIP_GAP - STRIP, -STRIP_GAP - STRIP, WIDTH + STRIP_GAP + STRIP, HEIGHT)
