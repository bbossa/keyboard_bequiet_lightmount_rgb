"""lightmount: lighting for the be quiet! Light Mount keyboard (fixed zones + alerts)."""
import argparse, logging, os, shutil, subprocess, sys

from . import __version__, config, daemon, device, protocol

MODES = {protocol.MODE_EFFECTS: 'effects (01): firmware effects, 10:0d ignored',
         protocol.MODE_CUSTOM: 'custom (03): per-LED colors'}


def check(args):
    """Validate the config without touching the keyboard."""
    cfg, errors, warnings = config.validate(config.read(args.config))
    for e in errors:
        print(f'error: {args.config}: {e}', file=sys.stderr)
    for w in warnings:
        print(f'warning: {args.config}: {w}', file=sys.stderr)
    if errors:
        return 1
    leds = sum(len(z['leds']) for z in cfg['zones'].values())
    source = args.config if os.path.exists(args.config) else 'built-in defaults (no config file)'
    print(f'config OK: {len(cfg["zones"])} zones, {leds} LEDs, alerts on "{cfg["alerts"]["zone"]}" ({source})')
    return 0


def load(args):
    cfg, warnings = config.load(args.config)
    for w in warnings:
        logging.getLogger('lightmount').warning('%s', w)
    return cfg


def apply(args):
    daemon.apply(load(args))
    return 0


def status(args):
    try:
        cfg = load(args)
        print('config:  OK')
    except config.ConfigError as e:
        print(f'config:  invalid ({len(e.errors)} errors, see `lightmount check`)')
        cfg = config.validate({})[0]
    print(f'daemon:  {daemon_state()}')
    with daemon.locked():
        kb, ident, mode = device.status(cfg)
    print(f'device:  {kb.usb_path} (vendor {kb.vendor}, LampArray {kb.hidraw[device.LAMPARRAY_INTERFACE]})')
    print(f'version: {ident.version.hex(" ")} ({"known" if ident.known else "UNKNOWN: read-only"})')
    print(f'mode:    {"no reply" if mode is None else MODES.get(mode, f"{mode:02x} (unknown)")}')
    return 0


def daemon_state():
    if not shutil.which('systemctl'):
        return 'unknown (no systemctl)'
    result = subprocess.run(['systemctl', '--user', 'is-active', 'lightmount.service'],
                            capture_output=True, text=True)
    return result.stdout.strip() or 'unknown'


def alert(args):
    daemon.alert(args.kind, args.config)
    return 0


EXIT_CONFIG = 2  # the service does not restart on it (RestartPreventExitStatus)


def watch(args):
    try:
        daemon.watch(args.config)
    except config.ConfigError as e:
        logging.getLogger('lightmount').error('invalid config, not starting:\n%s', e)
        return EXIT_CONFIG
    return 0


class JournalFormatter(logging.Formatter):
    """syslog priority prefix, read by journald on a service's stderr (SyslogLevelPrefix)."""
    PRIORITIES = {logging.DEBUG: 7, logging.INFO: 6, logging.WARNING: 4, logging.ERROR: 3, logging.CRITICAL: 2}

    def format(self, record):
        prefix = f'<{self.PRIORITIES.get(record.levelno, 6)}>'
        return '\n'.join(prefix + line for line in super().format(record).splitlines())


def setup_logging():
    log = logging.getLogger('lightmount')
    if log.handlers:  # main() called again (tests)
        return
    handler = logging.StreamHandler()
    if os.environ.get('JOURNAL_STREAM'):  # stderr is connected to journald
        handler.setFormatter(JournalFormatter('%(message)s'))
    else:
        handler.setFormatter(logging.Formatter('lightmount: %(levelname)s: %(message)s'))
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if os.environ.get('LIGHTMOUNT_DEBUG') else logging.INFO)


def parser():
    ap = argparse.ArgumentParser(prog='lightmount', description=__doc__,
                                 epilog='LIGHTMOUNT_DEBUG=1 adds debug messages (device version, hashed serial).')
    ap.add_argument('--config', default=config.CONFIG, help=f'config file (default: {config.CONFIG})')
    ap.add_argument('--version', action='version', version=f'lightmount {__version__}')
    sub = ap.add_subparsers(dest='command', required=True, metavar='command')
    sub.add_parser('check', help='validate the config, without touching the keyboard').set_defaults(run=check)
    sub.add_parser('apply', help='apply the zones of the config once').set_defaults(run=apply)
    sub.add_parser('status', help='device, version, lighting mode, daemon state').set_defaults(run=status)
    p = sub.add_parser('alert', help='one-shot alert (through the daemon if it runs)')
    p.add_argument('kind', choices=config.ALERTS)
    p.set_defaults(run=alert)
    sub.add_parser('watch', help='daemon (systemd user service)').set_defaults(run=watch)
    return ap


def main(argv=None):
    setup_logging()
    args = parser().parse_args(argv)
    try:
        sys.exit(args.run(args))
    except config.ConfigError as e:
        sys.exit(f'{e}\n(run `lightmount check` for details)')
    except device.DeviceError as e:  # includes ReadOnlyError
        sys.exit(str(e))
    except PermissionError as e:
        sys.exit(f'{e.filename}: permission denied (is the udev rule 70-bequiet-light-mount.rules installed? '
                 'see README.md)')
