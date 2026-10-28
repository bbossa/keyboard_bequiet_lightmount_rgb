"""Main window: keyboard view, zones, alerts, live preview, save."""
import os, threading

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import config, daemon, device, save  # noqa: E402
from .i18n import _  # noqa: E402
from .keyboard import KeyboardView  # noqa: E402
from .model import Model, hex_color  # noqa: E402

PREVIEW_DELAY = 120  # ms: a color drag sends one write per pause, not one per pixel


def rgba(hexcolor):
    color = Gdk.RGBA()
    color.parse(f'#{hexcolor}')
    return color


def to_hex(color):
    return ''.join(f'{round(c * 255):02x}' for c in (color.red, color.green, color.blue))


def in_thread(work, done=None):
    """Run `work()` off the GTK thread (the keyboard answers slowly), then `done(result, error)` on it."""
    def run():
        try:
            result, error = work(), None
        except Exception as e:  # reported in the window
            result, error = None, e
        if done:
            GLib.idle_add(lambda: done(result, error) and False)
    threading.Thread(target=run, daemon=True).start()


def device_message(error):
    if isinstance(error, PermissionError):
        return _('Permission denied on the keyboard: is the udev rule 70-bequiet-light-mount.rules installed?')
    return _('Keyboard: {error}', error=error)


class Window(Gtk.ApplicationWindow):
    def __init__(self, app, path):
        super().__init__(application=app, default_width=1100, default_height=720)
        self.path = path
        self.updating = False         # widgets being filled from the model: no change events
        self.dirty = False
        self.zone = None              # zone being edited
        self.preview_busy = self.preview_pending = False
        self.preview_timer = None
        self.load()

        header = Gtk.HeaderBar()
        self.save_button = Gtk.Button(label=_('Save'), sensitive=False)
        self.save_button.add_css_class('suggested-action')
        self.save_button.connect('clicked', lambda b: self.save())
        header.pack_end(self.save_button)
        self.revert_button = Gtk.Button(label=_('Revert'), sensitive=False)
        self.revert_button.connect('clicked', lambda b: self.revert())
        header.pack_end(self.revert_button)
        box = Gtk.Box(spacing=6, tooltip_text=_('Show the changes on the keyboard before saving'))
        box.append(Gtk.Label(label=_('Live preview')))
        self.preview_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.preview_switch.connect('notify::active', self.on_preview_toggled)
        box.append(self.preview_switch)
        header.pack_start(box)
        self.set_titlebar(header)

        self.view = KeyboardView(self.model)
        self.view.connect('selection-changed', lambda v: self.refresh_selection())
        self.view.connect('zone-activated', lambda v, name: self.select_zone(name))

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.banner = Gtk.Label(wrap=True, xalign=0, visible=False)
        self.banner.add_css_class('error')
        main.append(self.banner)
        main.append(self.view)
        hint = Gtk.Label(wrap=True, xalign=0, label=_(
            'Click a key, drag to select several, Ctrl+click to add or remove, double-click to select its zone.'))
        hint.add_css_class('dim-label')
        main.append(hint)
        row = Gtk.Box(spacing=8)
        self.selection_label = Gtk.Label(xalign=0, hexpand=True)
        row.append(self.selection_label)
        row.append(Gtk.Label(label=_('Edited zone only')))
        self.focus_switch = Gtk.Switch(active=True, valign=Gtk.Align.CENTER,
                                       tooltip_text=_('Off: every zone in its color, as on the keyboard'))
        self.focus_switch.connect('notify::active', lambda s, p: self.refresh_editor())
        row.append(self.focus_switch)
        main.append(row)
        main.append(Gtk.Separator())
        # zones, zone, alerts side by side; on a narrow window they wrap below each other
        panels = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                             min_children_per_line=1, max_children_per_line=3,
                             column_spacing=24, row_spacing=12, valign=Gtk.Align.START)
        for panel in self.build_panels():
            panels.append(panel)
        main.append(panels)
        self.status = Gtk.Label(wrap=True, xalign=0, selectable=True)
        main.append(self.status)
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scrolled.set_child(main)
        self.set_child(scrolled)

        self.connect('close-request', self.on_close)
        self.refresh_all()
        if self.model.errors:
            self.show_status(_('The config file has problems, they will be fixed on save:') + '\n'
                             + '\n'.join(self.model.errors), error=True)
        self.check_device()
        self.update_title()

    # --- model --------------------------------------------------------------------------

    def load(self):
        try:
            raw = config.read(self.path)
            errors = []
        except config.ConfigError as e:  # TOML syntax: start from the defaults, the file is kept as is
            raw, errors = {}, e.errors
        model = Model(raw)
        model.errors = errors + model.errors
        if hasattr(self, 'model'):  # revert: the view keeps the same object
            self.model.__dict__.update(model.__dict__)
        else:
            self.model = model
        if self.zone not in self.model.zones:
            self.zone = next(iter(self.model.zones), None)

    def changed(self):
        self.dirty = True
        self.update_title()
        self.refresh_zone_rows()
        self.view.queue_draw()
        errors, warnings = self.model.validate()
        if errors:
            self.show_status(_('Invalid: {error}', error='; '.join(errors)), error=True)
        else:
            self.show_status('\n'.join(warnings))
        self.schedule_preview()

    def update_title(self):
        self.set_title(('* ' if self.dirty else '') + f'lightmount — {self.path}')
        self.save_button.set_sensitive(self.dirty)
        self.revert_button.set_sensitive(self.dirty)

    def show_status(self, text, error=False):
        self.status.set_text(text)
        if error:
            self.status.add_css_class('error')
        else:
            self.status.remove_css_class('error')

    # --- sidebar ------------------------------------------------------------------------

    def build_panels(self):
        box = panel(_('Zones'))
        self.zone_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.zone_list.add_css_class('boxed-list')
        self.zone_list.connect('row-selected', self.on_zone_selected)
        box.append(Gtk.Frame(child=self.zone_list))

        actions = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        for n, (label, tip, handler) in enumerate( ((_('New zone'), _('Create a zone with the selected LEDs'), self.on_new_zone),
                                    (_('Add'), _('Add the selected LEDs to this zone'), self.on_add),
                                    (_('Remove'), _('Take the selected LEDs out of their zone'), self.on_remove),
                                    (_('Select'), _('Select the LEDs of this zone'), self.on_select))):
            button = Gtk.Button(label=label, tooltip_text=tip)
            button.connect('clicked', lambda b, h=handler: h())
            actions.attach(button, n % 2, n // 2, 1, 1)
            if n:
                setattr(self, ('add_button', 'remove_button', 'select_button')[n - 1], button)
        box.append(actions)
        zones = box

        box = panel(_('Zone'))
        grid = form()
        self.name_entry = Gtk.Entry(hexpand=True, width_chars=12, tooltip_text=_('Names: letters, digits, - and _ only, not already used.'))
        self.name_entry.connect('activate', lambda e: self.on_rename())
        focus = Gtk.EventControllerFocus()
        focus.connect('leave', lambda c: self.on_rename())
        self.name_entry.add_controller(focus)
        self.color_button = color_button(self.on_zone_color)
        self.dim_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.05)
        self.dim_scale.set_digits(2)
        self.dim_scale.set_draw_value(True)
        self.dim_scale.set_hexpand(True)
        self.dim_scale.connect('value-changed', self.on_dim)
        self.delete_button = Gtk.Button(label=_('Delete zone'))
        self.delete_button.add_css_class('destructive-action')
        self.delete_button.connect('clicked', lambda b: self.on_delete())
        add_row(grid, 0, _('Name'), self.name_entry)
        add_row(grid, 1, _('Color'), self.color_button)
        add_row(grid, 2, _('Dim'), self.dim_scale)
        grid.attach(self.delete_button, 1, 3, 1, 1)
        self.zone_form = grid
        box.append(grid)
        zone = box

        box = panel(_('Alerts'))
        grid = form()
        self.alert_zone = Gtk.DropDown.new_from_strings([])
        self.alert_zone.connect('notify::selected', self.on_alert_zone)
        self.duration = Gtk.SpinButton.new_with_range(0.05, config.MAX_DURATION, 0.05)
        self.duration.set_digits(2)
        self.duration.connect('value-changed', self.on_duration)
        self.alert_colors = {kind: color_button(lambda b, k=kind: self.on_alert_color(k, b))
                             for kind in config.ALERTS}
        self.sources = {}
        for source in config.SOURCES:
            switch = Gtk.Switch(halign=Gtk.Align.START)
            switch.connect('notify::active', lambda s, p, src=source: self.on_source(src, s))
            self.sources[source] = switch
        rows = [(_('Zone'), self.alert_zone), (_('Duration (s)'), self.duration),
                (_('Notification'), self.alert_colors['normal']), (_('Critical'), self.alert_colors['critical']),
                (_('Failed command'), self.alert_colors['error']),
                (_('Desktop notifications'), self.sources['notifications']),
                (_('Shell errors'), self.sources['shell'])]
        for n, (label, widget) in enumerate(rows):
            add_row(grid, n, label, widget)
        box.append(grid)
        return zones, zone, box

    def refresh_all(self):
        self.refresh_zone_rows(rebuild=True)
        self.refresh_editor()
        self.refresh_alerts()
        self.refresh_selection()
        self.view.queue_draw()

    def refresh_zone_rows(self, rebuild=False):
        names = list(self.model.zones)
        rows = list(children(self.zone_list))
        if rebuild or [r.zone for r in rows] != names:
            self.updating = True
            self.zone_list.remove_all()
            for name in names:
                self.zone_list.append(zone_row(name))
            self.updating = False
            rows = list(children(self.zone_list))
        for row in rows:
            zone = self.model.zones[row.zone]
            row.swatch.rgb = zone.rgb
            row.swatch.queue_draw()
            row.count.set_text(_('{n} LEDs', n=len(zone.leds)))
            if row.zone == self.zone and self.zone_list.get_selected_row() is not row:
                self.updating = True
                self.zone_list.select_row(row)
                self.updating = False
        self.refresh_alerts_zones()

    def refresh_editor(self):
        zone = self.model.zones.get(self.zone)
        self.zone_form.set_sensitive(zone is not None)
        self.view.focus = self.zone if self.focus_switch.get_active() else None
        self.view.queue_draw()
        if zone is None:
            return
        self.updating = True
        self.name_entry.set_text(self.zone)
        self.color_button.set_rgba(rgba(zone.color))
        self.dim_scale.set_value(1 if zone.dim is None else zone.dim)
        self.updating = False
        self.refresh_actions()

    def refresh_alerts_zones(self):
        names = list(self.model.zones)
        current = [self.alert_zone.get_model().get_string(i) for i in range(self.alert_zone.get_model().get_n_items())]
        zone = self.model.alerts.get('zone')
        self.updating = True
        if current != names:
            self.alert_zone.set_model(Gtk.StringList.new(names))
        if zone in names:
            self.alert_zone.set_selected(names.index(zone))
        self.updating = False

    def refresh_alerts(self):
        self.refresh_alerts_zones()
        alerts = self.model.alerts
        self.updating = True
        duration = alerts.get('duration')
        self.duration.set_value(duration if isinstance(duration, (int, float)) else 1.25)
        for kind, button in self.alert_colors.items():
            button.set_rgba(rgba(hex_color(alerts.get(kind)) or '000000'))
        for source, switch in self.sources.items():
            switch.set_active(bool(alerts['sources'].get(source, True)))
        self.updating = False

    def refresh_selection(self):
        n = len(self.view.selection)
        self.selection_label.set_text(_('{n} selected', n=n) if n else _('No LED selected'))
        self.refresh_actions()

    def refresh_actions(self):
        selection = bool(self.view.selection)
        self.add_button.set_sensitive(selection and self.zone is not None)
        self.remove_button.set_sensitive(selection)
        self.select_button.set_sensitive(self.zone is not None)

    def select_zone(self, name):
        self.zone = name
        self.refresh_zone_rows()
        self.refresh_editor()
        self.view.queue_draw()

    # --- handlers -----------------------------------------------------------------------

    def on_zone_selected(self, listbox, row):
        if self.updating or row is None:
            return
        self.on_rename()  # a name being typed is applied before switching
        self.zone = row.zone
        self.refresh_editor()
        self.view.queue_draw()

    def on_new_zone(self):
        self.zone = self.model.new_zone(self.view.selection)
        self.refresh_zone_rows(rebuild=True)
        self.refresh_editor()
        self.changed()

    def on_add(self):
        if self.zone is None:
            return
        self.model.assign(self.view.selection, self.zone)
        self.refresh_editor()
        self.changed()

    def on_remove(self):
        self.model.unassign(self.view.selection)
        self.refresh_editor()
        self.changed()

    def on_select(self):
        if self.zone in self.model.zones:
            self.view.set_selection(self.model.zones[self.zone].leds)

    def on_rename(self):
        if self.updating or self.zone not in self.model.zones:
            return
        new = self.name_entry.get_text().strip()
        if new == self.zone:
            return
        if not self.model.rename(self.zone, new):
            self.show_status(_('Names: letters, digits, - and _ only, not already used.'), error=True)
            self.updating = True
            self.name_entry.set_text(self.zone)
            self.updating = False
            return
        self.zone = new
        self.refresh_zone_rows(rebuild=True)
        self.changed()

    def on_zone_color(self, button):
        if self.updating or self.zone not in self.model.zones:
            return
        self.model.zones[self.zone].color = to_hex(button.get_rgba())
        self.changed()

    def on_dim(self, scale):
        if self.updating or self.zone not in self.model.zones:
            return
        value = round(scale.get_value(), 2)
        self.model.zones[self.zone].dim = None if value == 1 else value
        self.changed()

    def on_delete(self):
        if self.zone not in self.model.zones:
            return
        self.model.delete(self.zone)
        self.zone = next(iter(self.model.zones), None)
        self.refresh_zone_rows(rebuild=True)
        self.refresh_editor()
        self.changed()

    def on_alert_zone(self, dropdown, param):
        item = dropdown.get_selected_item()
        if self.updating or item is None:
            return
        self.model.alerts['zone'] = item.get_string()
        self.changed()

    def on_duration(self, spin):
        if not self.updating:
            self.model.alerts['duration'] = round(spin.get_value(), 2)
            self.changed()

    def on_alert_color(self, kind, button):
        if not self.updating:
            self.model.alerts[kind] = to_hex(button.get_rgba())
            self.changed()

    def on_source(self, source, switch):
        if not self.updating:
            self.model.alerts['sources'][source] = switch.get_active()
            self.changed()

    # --- keyboard -----------------------------------------------------------------------

    def check_device(self):
        cfg = config.validate(self.model.raw())[0]

        def work():
            kb = device.find(cfg)
            if not os.access(kb.vendor, os.R_OK | os.W_OK):
                raise PermissionError(13, 'permission denied', kb.vendor)

        def done(result, error):
            if error is not None:
                self.banner.set_text(device_message(error))
                self.banner.set_visible(True)
                self.preview_switch.set_sensitive(False)
        in_thread(work, done)

    def on_preview_toggled(self, switch, param):
        if switch.get_active():
            self.schedule_preview()
        else:  # back to the saved config
            self.restore_keyboard()

    def schedule_preview(self):
        if not self.preview_switch.get_active():
            return
        if self.preview_timer:
            GLib.source_remove(self.preview_timer)
        self.preview_timer = GLib.timeout_add(PREVIEW_DELAY, self.send_preview)

    def send_preview(self):
        self.preview_timer = None
        if self.preview_busy:  # one write at a time: the last state is sent when it ends
            self.preview_pending = True
            return False
        errors, _warnings = self.model.validate()
        if errors:
            return False
        raw = self.model.raw()
        self.preview_busy = True
        in_thread(lambda: daemon.preview(raw), self.preview_done)
        return False

    def preview_done(self, result, error):
        self.preview_busy = False
        if error is not None:
            self.banner.set_text(device_message(error) + ' ' + _('Live preview stopped.'))
            self.banner.set_visible(True)
            self.preview_switch.set_active(False)
            return
        if self.preview_pending:
            self.preview_pending = False
            self.send_preview()

    def restore_keyboard(self, then=None):
        """Show the saved config again (the service rereads it, or it is applied once)."""
        def done(result, error):
            if error is not None:
                self.show_status(device_message(error), error=True)
            if then:
                then()
        in_thread(lambda: daemon.reload(self.path), done)

    # --- save / revert / close ------------------------------------------------------------

    def save(self):
        self.on_rename()
        raw = self.model.raw()
        try:
            warnings = save.write(self.path, raw['zones'], raw['alerts'])
        except (save.SaveError, config.ConfigError, OSError) as e:
            self.show_status(_('Not saved: {error}', error=e), error=True)
            return False
        self.dirty = False
        self.model.errors = []
        self.update_title()

        def done(told, error):
            if error is not None:
                message = device_message(error)
            else:
                message = _('The service rereads the config.') if told else _('Service not running: zones applied once.')
            self.show_status('\n'.join([_('Saved: {path}', path=self.path), message] + warnings), error=error is not None)
        in_thread(lambda: daemon.reload(self.path), done)
        return True

    def revert(self):
        self.load()
        self.dirty = False
        self.update_title()
        self.refresh_all()
        self.show_status('')
        if self.preview_switch.get_active():
            self.restore_keyboard()

    def on_close(self, window):
        if not self.dirty:
            return False
        dialog = Gtk.AlertDialog(message=_('Unsaved changes'), detail=_('Save them before closing?'),
                                 buttons=[_('Cancel'), _('Discard'), _('Save')], cancel_button=0, default_button=2)

        def answered(dialog, result):
            try:
                choice = dialog.choose_finish(result)
            except GLib.Error:
                return
            if choice == 1:
                self.dirty = False
                if self.preview_switch.get_active():
                    self.restore_keyboard(then=self.destroy)
                else:
                    self.destroy()
            elif choice == 2 and self.save():
                self.destroy()
        dialog.choose(self, None, answered)
        return True


# --- widgets ------------------------------------------------------------------------------

def children(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        child = child.get_next_sibling()


def panel(title):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, width_request=300, valign=Gtk.Align.START)
    label = Gtk.Label(label=title, xalign=0)
    label.add_css_class('heading')
    box.append(label)
    return box


def form():
    return Gtk.Grid(column_spacing=12, row_spacing=8)


def add_row(grid, n, text, widget):
    label = Gtk.Label(label=text, xalign=1)
    label.add_css_class('dim-label')
    grid.attach(label, 0, n, 1, 1)
    grid.attach(widget, 1, n, 1, 1)


def color_button(handler):
    button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), halign=Gtk.Align.START)
    button.connect('notify::rgba', lambda b, p: handler(b))
    return button


def zone_row(name):
    row = Gtk.ListBoxRow()
    row.zone = name
    box = Gtk.Box(spacing=10, margin_top=6, margin_bottom=6, margin_start=8, margin_end=8)
    swatch = Gtk.DrawingArea(content_width=18, content_height=18, valign=Gtk.Align.CENTER)
    swatch.rgb = (0, 0, 0)

    def draw(area, cr, w, h):
        cr.rectangle(0, 0, w, h)
        cr.set_source_rgb(*(c / 255 for c in area.rgb))
        cr.fill()
    swatch.set_draw_func(draw)
    box.append(swatch)
    box.append(Gtk.Label(label=name, xalign=0, hexpand=True))
    count = Gtk.Label()
    count.add_css_class('dim-label')
    box.append(count)
    row.set_child(box)
    row.swatch, row.count = swatch, count
    return row
