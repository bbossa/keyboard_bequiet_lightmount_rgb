"""`lightmount-gui` entry point: GTK4 application, one window."""
import argparse, sys

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, Gtk  # noqa: E402

from .. import __version__, config  # noqa: E402
from .window import Window  # noqa: E402

APP_ID = 'io.github.bbossa.lightmount'


class App(Gtk.Application):
    def __init__(self, path):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.path = path

    def do_activate(self):
        window = self.get_active_window() or Window(self, self.path)
        window.present()


def main(argv=None):
    ap = argparse.ArgumentParser(prog='lightmount-gui', description='Edit the lightmount zones and alerts.')
    ap.add_argument('--config', default=config.CONFIG, help=f'config file (default: {config.CONFIG})')
    ap.add_argument('--version', action='version', version=f'lightmount-gui {__version__}')
    args, gtk_args = ap.parse_known_args(argv)
    sys.exit(App(args.config).run([sys.argv[0]] + gtk_args))
