"""Daemon: fixed zones + alerts on one zone.

Custom mode (10:0d) does not survive a power cycle: the keyboard restarts in
effects mode. The daemon therefore reapplies the zones at startup, on every
replug and on resume from suspend (the USB controller is reset: the keyboard
stays plugged but loses its colors), and colors the alert zone for a moment on a notification (D-Bus) or a
shell error (FIFO).

Events are handled in batches: a burst of notifications is one write, an
active alert is extended rather than sent again, and a higher-priority alert
replaces a lower one. Updates are at least MIN_INTERVAL apart.
"""
import errno, fcntl, json, logging, os, queue, signal, stat, subprocess, threading, time
from contextlib import contextmanager

from . import config, device, protocol

log = logging.getLogger('lightmount')

RUNTIME = os.environ.get('XDG_RUNTIME_DIR', '/tmp')
FIFO = os.path.join(RUNTIME, 'lightmount.fifo')
LOCK = os.path.join(RUNTIME, 'lightmount.lock')
ALERTS = config.ALERTS
PRIORITY = {'normal': 1, 'error': 2, 'critical': 3}
# event -> delay before reapplying: let the keyboard initialize after a replug
# or a resume, or finish switching effect (Fn+←/→ clears the custom colors, mode stays 03)
REAPPLY = {'plug': 1.5, 'resume': 1.5, 'effect': 0.3, 'reapply': 0}
KEYS_RETRY = 2  # seconds between attempts to open the keyboard for key events
MIN_INTERVAL = 0.040  # between two updates
RETRY_MIN, RETRY_MAX = 1, 60  # event source restart delay, doubled on each failure


@contextmanager
def locked():
    """Serialize keyboard exchanges between the daemon and the CLI."""
    with open(LOCK, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def write(cfg, entries):
    with locked():
        device.send_leds(cfg, entries)


def zone_entries(cfg):
    """Every zone, sorted by LED index."""
    return sorted((i, zone['color']) for zone in cfg['zones'].values() for i in zone['leds'])


def alert_entries(cfg, kind):
    color = cfg['alerts']['colors'][kind]
    return [(i, color) for i in cfg['zones'][cfg['alerts']['zone']]['leds']]


def restore_entries(cfg):
    zone = cfg['zones'][cfg['alerts']['zone']]
    return [(i, zone['color']) for i in zone['leds']]


def apply(cfg):
    write(cfg, zone_entries(cfg))


# --- event sources: each runs in a thread and puts event names in a queue --------

def watch_notifications(events):
    """Notify calls on the session bus; urgency 2 = critical. The content is never read."""
    cmd = ['busctl', '--user', 'monitor', 'org.freedesktop.Notifications', '--json=short']
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as proc:
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get('type') != 'method_call' or msg.get('member') != 'Notify':
                continue
            hints = (msg.get('payload', {}).get('data') or [None] * 7)[6] or {}
            urgency = (hints.get('urgency') or {}).get('data', 1)
            events.put('critical' if urgency == 2 else 'normal')


def watch_plug(events):
    """Keyboard replug: a be quiet! hidraw (373f:0002) is added."""
    cmd = ['udevadm', 'monitor', '--udev', '--subsystem-match=hidraw', '--property']
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as proc:
        action = None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith('ACTION='):
                action = line.split('=', 1)[1]
            elif action == 'add' and line.startswith('DEVPATH=') and '373F:0002' in line.upper():
                events.put('plug')
                action = None


def watch_sleep(events):
    """Resume from suspend: logind's PrepareForSleep(false) on the system bus. No privilege needed."""
    cmd = ['busctl', '--system', '--json=short', 'wait', 'org.freedesktop.login1', '/org/freedesktop/login1',
           'org.freedesktop.login1.Manager', 'PrepareForSleep']
    while True:  # `busctl wait` returns after one signal
        out = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True).stdout
        try:
            going_to_sleep = json.loads(out)['data'][0]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            log.debug('sleep: unexpected output %r', out)
            continue
        if going_to_sleep is False:
            events.put('resume')


def is_fifo(path):
    try:
        return stat.S_ISFIFO(os.stat(path).st_mode)
    except FileNotFoundError:
        return False


def watch_fifo(events):
    """Shell errors and manual alerts: `lightmount alert <kind>` or the shell hook write here."""
    if not is_fifo(FIFO):
        if os.path.lexists(FIFO):
            log.warning('%s is not a FIFO, replacing it', FIFO)
            os.unlink(FIFO)
        os.mkfifo(FIFO, 0o600)
    fd = os.open(FIFO, os.O_RDWR)  # keep a writer open: read never sees EOF
    with os.fdopen(fd) as f:
        for line in f:
            if line.strip() in ALERTS:
                events.put(line.strip())


def effect_keys(cfg_of):
    """Fn-layer lighting effect key (Fn+←/→) → 'effect'. Only bytes 1 and 3 of key events are read."""
    def watch_effect_keys(events):
        while True:
            try:
                fd = os.open(device.find(cfg_of()).vendor, os.O_RDONLY)
            except (device.DeviceError, OSError) as e:  # absent: retry, the replug reapplies anyway
                log.debug('effect keys: %s', e)
                time.sleep(KEYS_RETRY)
                continue
            try:
                while raw := os.read(fd, protocol.PACKET_SIZE):
                    function = protocol.fn_function(raw)
                    if function == protocol.FN_EFFECT:
                        events.put('effect')
                    elif function is not None:
                        log.debug('Fn function %02x', function)
            except OSError as e:  # unplugged
                log.debug('effect keys: %s', e)
            finally:
                os.close(fd)
    return watch_effect_keys


def poller(interval, cfg_of):
    """Read the lighting mode (10:01) every `interval` s; custom mode lost → 'reapply'."""
    def watch_mode(events):
        while True:
            time.sleep(interval)
            try:
                with locked(), device.vendor(cfg_of(), writing=False) as fd:
                    mode = device.read_mode(fd, device.new_seq())
            except device.DeviceError as e:  # absent: the replug event will reapply
                log.debug('poll: %s', e)
                continue
            if mode is not None and mode != protocol.MODE_CUSTOM:
                log.info('poll: lighting mode %02x, custom mode lost', mode)
                events.put('reapply')
    return watch_mode


def supervise(name, source, events, sleep=time.sleep, clock=time.monotonic):
    """Run an event source forever: restart it with a growing delay when it stops or fails."""
    delay = RETRY_MIN
    while True:
        started = clock()
        try:
            source(events)
            log.warning('%s stopped', name)
        except Exception as e:
            log.error('%s failed: %s: %s', name, type(e).__name__, e)
        if clock() - started > RETRY_MAX:  # ran for a while: not a crash loop
            delay = RETRY_MIN
        log.info('%s: restarting in %d s', name, delay)
        sleep(delay)
        delay = min(delay * 2, RETRY_MAX)


# --- main loop ----------------------------------------------------------------------

class Daemon:
    def __init__(self, cfg, path=config.CONFIG, writer=write, clock=time.monotonic, sleep=time.sleep):
        self.cfg, self.path = cfg, path
        self.writer, self.clock, self.sleep = writer, clock, sleep
        self.events = queue.Queue()
        self.alert = None        # active alert kind
        self.restore_at = None   # when the active alert ends
        self.last_write = None

    def send(self, entries):
        if self.last_write is not None:
            wait = MIN_INTERVAL - (self.clock() - self.last_write)
            if wait > 0:
                self.sleep(wait)
        try:
            self.writer(self.cfg, entries)
        finally:
            self.last_write = self.clock()

    def reapply(self, events):
        self.sleep(max(REAPPLY[e] for e in events))
        if 'plug' in events:
            try:
                self.cfg, warnings = config.load(self.path)
                for w in warnings:
                    log.warning('%s', w)
            except config.ConfigError as e:
                log.error('config not reloaded, keeping the previous one:\n%s', e)
        self.alert = self.restore_at = None
        self.send(zone_entries(self.cfg))

    def handle(self, batch):
        """Handle a batch of events received together."""
        sources = self.cfg['alerts']['sources']
        batch = [e for e in batch if e != 'error' or sources['shell']]
        if not batch:
            return
        log.info('events: %s', ', '.join(sorted(set(batch))))
        reapply = [e for e in batch if e in REAPPLY]
        if reapply:
            self.reapply(reapply)
        alerts = [e for e in batch if e in PRIORITY]
        if not alerts:
            return
        kind = max(alerts, key=PRIORITY.get)
        if self.alert is None or PRIORITY[kind] > PRIORITY[self.alert]:
            self.send(alert_entries(self.cfg, kind))
            self.alert = kind
        self.restore_at = self.clock() + self.cfg['alerts']['duration']  # extends an active alert

    def restore(self):
        self.alert = self.restore_at = None
        self.send(restore_entries(self.cfg))

    def step(self):
        """Wait for events (or the end of the active alert) and handle them."""
        timeout = None if self.restore_at is None else max(0, self.restore_at - self.clock())
        try:
            batch = [self.events.get(timeout=timeout)]
        except queue.Empty:
            self.guarded('restore', self.restore)
            return
        while True:  # everything already queued is handled together
            try:
                batch.append(self.events.get_nowait())
            except queue.Empty:
                break
        self.guarded('events', self.handle, batch)

    def guarded(self, what, fn, *args):
        try:
            fn(*args)
        except device.DeviceError as e:  # absent, unexpected or read-only: the daemon keeps going
            log.error('%s: %s', what, e)
        except OSError as e:  # unplugged while sending, etc.
            log.error('%s: %s: %s', what, type(e).__name__, e)

    def sources(self):
        out = {'udev': watch_plug, 'sleep': watch_sleep, 'fifo': watch_fifo}
        if self.cfg['alerts']['sources']['notifications']:
            out['notifications'] = watch_notifications
        if self.cfg['daemon']['reapply_on_effect_key']:
            out['effect keys'] = effect_keys(lambda: self.cfg)
        if self.cfg['daemon']['poll_interval']:
            out['poll'] = poller(self.cfg['daemon']['poll_interval'], lambda: self.cfg)
        return out

    def run(self):
        for name, source in self.sources().items():
            threading.Thread(target=supervise, args=(name, source, self.events), name=name, daemon=True).start()
        self.guarded('startup', self.send, zone_entries(self.cfg))
        while True:
            self.step()


def watch(path=config.CONFIG):
    cfg, warnings = config.load(path)  # invalid config at startup: ConfigError, the CLI exits with 2
    for w in warnings:
        log.warning('%s', w)
    Daemon(cfg, path).run()


def alert(kind, path=config.CONFIG):
    """Through the daemon's FIFO if it runs, otherwise standalone."""
    if is_fifo(FIFO):
        try:
            fd = os.open(FIFO, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as e:
            if e.errno != errno.ENXIO:  # ENXIO: stale FIFO, no daemon reading it
                raise
        else:
            try:
                os.write(fd, f'{kind}\n'.encode())
            finally:
                os.close(fd)
            return
    cfg, _ = config.load(path)

    def interrupted(signum, frame):
        raise SystemExit(128 + signum)
    # a closed terminal (SIGHUP) or a kill must not leave the zone in the alert color
    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        write(cfg, alert_entries(cfg, kind))
        time.sleep(cfg['alerts']['duration'])
    finally:
        write(cfg, restore_entries(cfg))
