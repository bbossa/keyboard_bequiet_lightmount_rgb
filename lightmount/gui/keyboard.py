"""Keyboard view: the keys and strips drawn with their zone color, LED selection with the mouse."""
import math

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gdk, GObject, Gtk, Pango, PangoCairo  # noqa: E402

from . import geometry  # noqa: E402
from .i18n import _  # noqa: E402

MARGIN = 0.3   # around the drawing, in key units
RADIUS = 0.12
DRAG_MIN = 4   # pixels: below, a drag is a click


class KeyboardView(Gtk.DrawingArea):
    __gsignals__ = {
        'selection-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'zone-activated': (GObject.SignalFlags.RUN_FIRST, None, (str,)),  # double-click on a LED of a zone
    }

    def __init__(self, model):
        super().__init__(hexpand=True, vexpand=True, content_width=700, content_height=220)
        self.model = model
        self.shapes = geometry.shapes()
        self.selection = set()
        self.highlight = set()   # LEDs of the zone being edited: dashed outline
        self.band = None         # rubber band, in key units: (x0, y0, x1, y1)
        self.set_draw_func(self.draw)
        self.set_has_tooltip(True)
        self.connect('query-tooltip', self.on_tooltip)

        drag = Gtk.GestureDrag(button=Gdk.BUTTON_PRIMARY)
        drag.connect('drag-begin', self.on_drag_begin)
        drag.connect('drag-update', self.on_drag_update)
        drag.connect('drag-end', self.on_drag_end)
        self.add_controller(drag)
        click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
        click.connect('pressed', self.on_pressed)
        self.add_controller(click)
        self.base = set()        # selection kept during a Ctrl+drag
        self.double = False      # the release of a double-click is not a click

    # --- coordinates --------------------------------------------------------------------

    def transform(self):
        """Scale and offset from key units to pixels."""
        x0, y0, x1, y1 = geometry.BOUNDS
        w, h = x1 - x0 + 2 * MARGIN, y1 - y0 + 2 * MARGIN
        scale = min(self.get_width() / w, self.get_height() / h)
        ox = (self.get_width() - w * scale) / 2 - (x0 - MARGIN) * scale
        oy = (self.get_height() - h * scale) / 2 - (y0 - MARGIN) * scale
        return scale, ox, oy

    def to_units(self, px, py):
        scale, ox, oy = self.transform()
        return (px - ox) / scale, (py - oy) / scale

    def shape_at(self, px, py):
        x, y = self.to_units(px, py)
        return next((s for s in self.shapes if s.contains(x, y)), None)

    # --- drawing ------------------------------------------------------------------------

    def draw(self, area, cr, width, height):
        scale, ox, oy = self.transform()
        fg = self.get_color()
        colors = self.model.colors()
        cr.translate(ox, oy)
        cr.scale(scale, scale)
        cr.set_line_join(1)  # round
        for shape in self.shapes:
            rgb = colors.get(shape.index)
            outline_path(cr, shape)
            if rgb is None:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.10)
            else:
                cr.set_source_rgb(*(c / 255 for c in rgb))
            cr.fill()
            if shape.index in self.selection or shape.index in self.highlight:
                self.outline(cr, shape, fg, selected=shape.index in self.selection)
            if shape.kind != 'strip':
                self.legend(cr, shape, rgb, fg, scale)
        if self.band:
            x0, y0, x1, y1 = self.band
            cr.rectangle(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.15)
            cr.fill_preserve()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
            cr.set_line_width(1 / scale)
            cr.stroke()

    def outline(self, cr, shape, fg, selected):
        outline_path(cr, shape)
        if selected:
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 1)
            cr.set_line_width(0.09)
            cr.set_dash([])
        else:
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.8)
            cr.set_line_width(0.045)
            cr.set_dash([0.12, 0.08])
        cr.stroke()
        cr.set_dash([])

    def legend(self, cr, shape, rgb, fg, scale):
        """Drawn in pixels: Pango metrics are hinted, a font of a fraction of a unit gets wrong line heights."""
        x, y, w, h = shape.label_rect
        cr.save()
        px, py = cr.user_to_device(x, y)
        cr.identity_matrix()
        layout = PangoCairo.create_layout(cr)
        font = Pango.FontDescription.from_string('Sans')
        font.set_absolute_size(max(6, 0.24 * scale) * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_alignment(Pango.Alignment.CENTER)
        text = shape.legend
        layout.set_text(text, -1)
        if layout.get_pixel_size()[0] > w * scale * 0.9 and ' ' in text:  # too wide: one word per line
            layout.set_text(text.replace(' ', '\n'), -1)
        tw, th = layout.get_pixel_size()
        if rgb is None:
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.8)
        else:  # dark text on light colors
            luma = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255
            cr.set_source_rgb(*((0.1,) * 3 if luma > 0.5 else (0.95,) * 3))
        cr.move_to(px + (w * scale - tw) / 2, py + (h * scale - th) / 2)
        PangoCairo.show_layout(cr, layout)
        cr.restore()

    def on_tooltip(self, widget, px, py, keyboard_mode, tooltip):
        shape = self.shape_at(px, py)
        if shape is None:
            return False
        zone = self.model.owner(shape.index)
        tooltip.set_text(f'{shape.legend}  ·  LED {shape.index:02x}  ·  '
                         + (_('Zone {name}', name=zone) if zone else _('no zone')))
        return True

    # --- selection ----------------------------------------------------------------------

    def set_selection(self, leds):
        self.selection = set(leds)
        self.queue_draw()
        self.emit('selection-changed')

    def ctrl(self, gesture):
        return bool(gesture.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK)

    def on_pressed(self, gesture, n_press, px, py):
        if n_press != 2:
            return
        shape = self.shape_at(px, py)
        zone = shape and self.model.owner(shape.index)
        if zone:
            self.double = True
            self.set_selection(self.model.zones[zone].leds)
            self.emit('zone-activated', zone)

    def on_drag_begin(self, gesture, px, py):
        self.base = set(self.selection) if self.ctrl(gesture) else set()
        self.start = (px, py)

    def on_drag_update(self, gesture, dx, dy):
        if math.hypot(dx, dy) < DRAG_MIN:
            return
        px, py = self.start
        self.band = (*self.to_units(px, py), *self.to_units(px + dx, py + dy))
        hit = {s.index for s in self.shapes if s.intersects(*self.band)}
        self.selection = self.base | hit
        self.queue_draw()

    def on_drag_end(self, gesture, dx, dy):
        px, py = self.start
        if self.double:
            self.double = False
            return
        if self.band is None:  # a click
            shape = self.shape_at(px, py)
            if self.ctrl(gesture):
                selection = set(self.selection)
                if shape:
                    selection ^= {shape.index}
            else:
                selection = {shape.index} if shape else set()
            self.set_selection(selection)
            return
        self.band = None
        self.set_selection(self.selection)


def outline_path(cr, shape, d=0.05):
    """Knob: a circle. Strip segment: a slightly rounded bar. Key: a rounded rectangle,
    or the L of the ISO Enter (wide top, narrower bottom, right edges aligned)."""
    if shape.kind == 'knob':
        x, y, w, h = shape.rects[0]
        cr.new_sub_path()
        cr.arc(x + w / 2, y + h / 2, min(w, h) / 2 - d, 0, 2 * math.pi)
        cr.close_path()
        return
    if shape.kind == 'strip':
        rounded(cr, *shape.rects[0], r=0.05)
        return
    if len(shape.rects) == 1:
        rounded(cr, *inset(shape.rects[0], d))
        return
    (tx, ty, tw, th), (bx, by, bw, bh) = shape.rects
    right, bottom = tx + tw - d, by + bh - d
    cr.new_sub_path()
    for x, y in ((tx + d, ty + d), (right, ty + d), (right, bottom), (bx + d, bottom),
                 (bx + d, ty + th - d), (tx + d, ty + th - d)):
        cr.line_to(x, y)
    cr.close_path()


def inset(rect, d):
    x, y, w, h = rect
    return x + d, y + d, w - 2 * d, h - 2 * d


def rounded(cr, x, y, w, h, r=RADIUS):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
