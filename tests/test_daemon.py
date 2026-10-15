"""Daemon event handling, throttling, supervision and FIFO, with a fake clock and no keyboard."""
import contextlib, io, logging, os, tempfile, threading, time, unittest
from unittest import mock

import fixtures  # noqa: F401  (sys.path)
from lightmount import cli, config, daemon, device, layout, protocol

GREEN, RED, BLUE = (0, 0xff, 0), (0xff, 0, 0), (0, 0, 0xff)
TOP_COLOR = config.rgb('49412f')


class Stop(Exception):
    pass


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def defaults(**sections):
    raw = {key: value for key, value in sections.items()}
    cfg, errors, _ = config.validate(raw)
    assert not errors, errors
    return cfg


class DaemonTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.writes = []
        self.daemon = self.make(defaults())

    def make(self, cfg, path='/nonexistent/lightmount.toml'):
        return daemon.Daemon(cfg, path, writer=lambda cfg, entries: self.writes.append(entries),
                             clock=self.clock, sleep=self.clock.sleep)

    def colors(self, entries):
        return {color for _, color in entries}


class Alerts(DaemonTest):
    def test_alert_then_restore(self):
        self.daemon.handle(['normal'])
        self.assertEqual(len(self.writes), 1)
        self.assertEqual([i for i, _ in self.writes[0]], list(layout.TOP))
        self.assertEqual(self.colors(self.writes[0]), {GREEN})
        self.assertEqual(self.daemon.restore_at, self.clock.now + 1.25)
        self.clock.now += 2
        self.daemon.step()  # queue empty, deadline passed
        self.assertEqual(self.colors(self.writes[1]), {TOP_COLOR})
        self.assertIsNone(self.daemon.alert)

    def test_burst_is_one_write(self):
        for _ in range(50):
            self.daemon.events.put('normal')
        self.daemon.step()
        self.assertEqual(len(self.writes), 1)

    def test_same_alert_extends(self):
        self.daemon.handle(['normal'])
        self.clock.now += 1
        self.daemon.handle(['normal'])
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.daemon.restore_at, self.clock.now + 1.25)

    def test_higher_priority_replaces(self):
        self.daemon.handle(['normal'])
        self.daemon.handle(['critical'])
        self.assertEqual(len(self.writes), 2)
        self.assertEqual(self.colors(self.writes[1]), {RED})
        self.assertEqual(self.daemon.alert, 'critical')

    def test_lower_priority_does_not_replace(self):
        self.daemon.handle(['critical'])
        self.daemon.handle(['normal', 'error'])
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.daemon.alert, 'critical')

    def test_batch_picks_highest(self):
        self.daemon.handle(['normal', 'error', 'normal'])
        self.assertEqual(self.colors(self.writes[0]), {BLUE})

    def test_shell_source_disabled(self):
        d = self.make(defaults(alerts={'sources': {'shell': False}}))
        d.handle(['error'])
        self.assertEqual(self.writes, [])
        d.handle(['normal'])
        self.assertEqual(len(self.writes), 1)

    def test_alert_zone(self):
        d = self.make(defaults(alerts={'zone': 'knob'}))
        d.handle(['normal'])
        self.assertEqual(self.writes[0], [(0x2d, GREEN)])

    def test_notifications_source_disabled(self):
        d = self.make(defaults(alerts={'sources': {'notifications': False}}))
        self.assertNotIn('notifications', d.sources())
        self.assertIn('notifications', self.daemon.sources())

    def test_effect_keys_source(self):
        self.assertIn('effect keys', self.daemon.sources())
        d = self.make(defaults(daemon={'reapply_on_effect_key': False}))
        self.assertNotIn('effect keys', d.sources())

    def test_poll_source(self):
        self.assertNotIn('poll', self.daemon.sources())
        self.assertIn('poll', self.make(defaults(daemon={'poll_interval': 10})).sources())


class Reapply(DaemonTest):
    def config_file(self, text):
        f = tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_plug_reloads_and_applies(self):
        d = self.make(defaults(), self.config_file('[zones]\ntop = "ffffff"\nknob = "000000"\n'))
        d.handle(['normal'])
        with self.assertLogs('lightmount', 'WARNING'):  # LEDs in no zone
            d.handle(['plug'])
        self.assertIn(daemon.REAPPLY['plug'], self.clock.sleeps)
        self.assertEqual(len(self.writes[-1]), 46)
        self.assertIsNone(d.alert)
        self.assertIsNone(d.restore_at)

    def test_plug_keeps_previous_config_if_invalid(self):
        d = self.make(defaults(), self.config_file('[zones]\ntop = "nope"\n'))
        with self.assertLogs('lightmount', 'ERROR') as logs:
            d.handle(['plug'])
        self.assertIn('keeping the previous one', logs.output[0])
        self.assertEqual(self.writes[-1], daemon.zone_entries(defaults()))

    def test_reapply_without_settle(self):
        self.daemon.handle(['reapply'])
        self.assertNotIn(daemon.REAPPLY['plug'], self.clock.sleeps)
        self.assertEqual(self.writes[-1], daemon.zone_entries(defaults()))

    def test_effect_key(self):
        # Fn+←/→ clears the custom colors: reapply after a short delay, without reloading the config
        d = self.make(defaults(), self.config_file('[zones]\ntop = "nope"\n'))
        d.handle(['normal'])
        d.handle(['effect'])
        self.assertEqual(self.clock.sleeps[-1], daemon.REAPPLY['effect'])
        self.assertEqual(self.writes[-1], daemon.zone_entries(defaults()))
        self.assertIsNone(d.alert)

    def test_plug_and_effect_wait_longest(self):
        self.daemon.handle(['effect', 'plug'])
        self.assertEqual(self.clock.sleeps, [daemon.REAPPLY['plug']])
        self.assertEqual(len(self.writes), 1)

    def test_plug_and_alert_in_one_batch(self):
        self.daemon.handle(['plug', 'normal'])
        self.assertEqual(len(self.writes), 2)
        self.assertEqual(len(self.writes[0]), 166)
        self.assertEqual(self.colors(self.writes[1]), {GREEN})


class Throttle(DaemonTest):
    def test_min_interval(self):
        self.daemon.send([(0, GREEN)])
        self.clock.now += 0.010
        self.daemon.send([(0, RED)])
        self.assertAlmostEqual(self.clock.sleeps[-1], daemon.MIN_INTERVAL - 0.010)

    def test_no_wait_when_idle(self):
        self.daemon.send([(0, GREEN)])
        self.clock.now += 1
        self.daemon.send([(0, RED)])
        self.assertEqual(self.clock.sleeps, [])

    def test_failed_write_still_counts(self):
        def fail(cfg, entries):
            raise device.DeviceError('gone')
        self.daemon.writer = fail
        with self.assertLogs('lightmount', 'ERROR'):
            self.daemon.guarded('events', self.daemon.handle, ['normal'])
        self.assertIsNone(self.daemon.alert)  # not marked active if it was not sent
        self.daemon.writer = lambda cfg, entries: None
        self.daemon.send([(0, RED)])
        self.assertEqual(len(self.clock.sleeps), 1)


class Errors(DaemonTest):
    def test_device_error_does_not_stop(self):
        def fail(cfg, entries):
            raise device.ReadOnlyError('unknown version')
        self.daemon.writer = fail
        self.daemon.events.put('normal')
        with self.assertLogs('lightmount', 'ERROR'):
            self.daemon.step()

    def test_unplugged_while_sending(self):
        def fail(cfg, entries):
            raise OSError(19, 'No such device')
        self.daemon.writer = fail
        with self.assertLogs('lightmount', 'ERROR'):
            self.daemon.guarded('events', self.daemon.handle, ['plug'])

    def test_events_are_logged_without_content(self):
        with self.assertLogs('lightmount', 'INFO') as logs:
            self.daemon.handle(['critical', 'normal'])
        self.assertEqual(logs.output, ['INFO:lightmount:events: critical, normal'])


class Supervise(unittest.TestCase):
    def run_source(self, source, failures):
        clock = Clock()
        calls = []

        def sleep(seconds):
            calls.append(seconds)
            if len(calls) == failures:
                raise Stop
            clock.sleep(seconds)
        with self.assertRaises(Stop), self.assertLogs('lightmount', 'INFO') as logs:
            daemon.supervise('test', source, None, sleep=sleep, clock=clock)
        return calls, logs.output

    def test_backoff(self):
        def crash(events):
            raise FileNotFoundError('busctl')
        delays, logs = self.run_source(crash, 8)
        self.assertEqual(delays, [1, 2, 4, 8, 16, 32, 60, 60])
        self.assertIn('test failed: FileNotFoundError', logs[0])

    def test_stopped_source(self):
        delays, logs = self.run_source(lambda events: None, 2)
        self.assertIn('WARNING:lightmount:test stopped', logs)

    def test_long_run_resets_delay(self):
        clock = Clock()
        runs = []

        def source(events):
            runs.append(1)
            if len(runs) == 3:
                clock.now += daemon.RETRY_MAX + 1  # third run lasts a while
            raise RuntimeError('x')
        delays = []

        def sleep(seconds):
            delays.append(seconds)
            if len(delays) == 4:
                raise Stop
        with self.assertRaises(Stop), self.assertLogs('lightmount'):
            daemon.supervise('test', source, None, sleep=sleep, clock=clock)
        self.assertEqual(delays, [1, 2, 1, 2])


class Fifo(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lightmount-run-')
        self.addCleanup(lambda: os.path.exists(self.dir) and __import__('shutil').rmtree(self.dir))
        self.fifo = os.path.join(self.dir, 'lightmount.fifo')
        patcher = mock.patch.object(daemon, 'FIFO', self.fifo)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.writes = []
        patcher = mock.patch.object(daemon, 'write', lambda cfg, entries: self.writes.append(entries))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(daemon.time, 'sleep')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_through_daemon(self):
        os.mkfifo(self.fifo, 0o600)
        reader = os.open(self.fifo, os.O_RDONLY | os.O_NONBLOCK)
        self.addCleanup(os.close, reader)
        daemon.alert('error', '/nonexistent.toml')
        self.assertEqual(os.read(reader, 64), b'error\n')
        self.assertEqual(self.writes, [])

    def test_no_fifo_standalone(self):
        daemon.alert('normal', '/nonexistent.toml')
        self.assertEqual(len(self.writes), 2)  # alert, then restore

    def test_standalone_restores_when_killed(self):
        import signal
        handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)}
        self.addCleanup(lambda: [signal.signal(sig, h) for sig, h in handlers.items()])

        def killed(seconds):
            os.kill(os.getpid(), signal.SIGHUP)  # terminal closed during the alert
        with mock.patch.object(daemon.time, 'sleep', killed), self.assertRaises(SystemExit) as ctx:
            daemon.alert('normal', '/nonexistent.toml')
        self.assertEqual(ctx.exception.code, 128 + signal.SIGHUP)
        self.assertEqual(len(self.writes), 2)
        self.assertEqual(self.writes[1], daemon.restore_entries(config.validate({})[0]))

    def test_stale_fifo_standalone(self):
        os.mkfifo(self.fifo, 0o600)  # left by a crashed daemon: nobody reads it
        daemon.alert('normal', '/nonexistent.toml')
        self.assertEqual(len(self.writes), 2)

    def test_regular_file_not_written(self):
        with open(self.fifo, 'w'):
            pass
        daemon.alert('normal', '/nonexistent.toml')
        self.assertEqual(os.path.getsize(self.fifo), 0)
        self.assertEqual(len(self.writes), 2)

    def open_when_read(self):
        """Writer end, once the watcher thread has created and opened the FIFO."""
        deadline = time.monotonic() + 2
        while True:
            try:
                if daemon.is_fifo(self.fifo):
                    return os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK)
            except OSError:  # ENXIO: created, not opened yet
                if time.monotonic() > deadline:
                    raise
            time.sleep(0.005)

    def test_watch_replaces_regular_file(self):
        with open(self.fifo, 'w'):
            pass
        events = __import__('queue').Queue()
        with self.assertLogs('lightmount', 'WARNING'):
            threading.Thread(target=daemon.watch_fifo, args=(events,), daemon=True).start()
            fd = self.open_when_read()
        os.write(fd, b'critical\nbogus\nnormal\n')
        os.close(fd)
        self.assertEqual([events.get(timeout=2), events.get(timeout=2)], ['critical', 'normal'])


class Poll(unittest.TestCase):
    def poll(self, modes):
        replies = iter(modes)
        events = __import__('queue').Queue()
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) > len(modes):
                raise Stop

        @contextlib.contextmanager
        def vendor(cfg, writing=True):
            self.assertFalse(writing)
            yield 99

        def read_mode(fd, seq):
            mode = next(replies)
            if isinstance(mode, Exception):
                raise mode
            return mode
        with mock.patch.object(daemon.time, 'sleep', sleep), mock.patch.object(device, 'vendor', vendor), \
                mock.patch.object(device, 'read_mode', read_mode), mock.patch.object(daemon, 'locked', contextlib.nullcontext), \
                self.assertRaises(Stop):
            daemon.poller(30, lambda: {})(events)
        self.assertEqual(set(sleeps), {30})
        return [events.get_nowait() for _ in range(events.qsize())]

    def test_custom_mode_kept(self):
        self.assertEqual(self.poll([protocol.MODE_CUSTOM, protocol.MODE_CUSTOM]), [])

    def test_custom_mode_lost(self):
        with self.assertLogs('lightmount', 'INFO'):
            self.assertEqual(self.poll([protocol.MODE_CUSTOM, protocol.MODE_EFFECTS]), ['reapply'])

    def test_absent_or_silent(self):
        self.assertEqual(self.poll([device.DeviceError('absent'), None]), [])


def key_event(data):
    return protocol.frame(*protocol.CMD_KEY_EVENT, bytes.fromhex(data), 0, protocol.SESSION)


# key events captured on 2026-10-15 (Fn alone, ←, →, Fn+→)
FN, LEFT, RIGHT, FN_RIGHT = '4b80011b', '530001010050', '5c000101004f', '5c80010903'


class EffectKeys(unittest.TestCase):
    def run_source(self, packets):
        import socket
        events = __import__('queue').Queue()
        opened = []

        def open_(path, flags):
            if opened:
                raise Stop  # second open: the first stream ended (unplug)
            ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            with theirs:
                for raw in packets:
                    theirs.send(raw)
            opened.append(path)
            return ours.detach()
        kb = device.Keyboard('1-7.2', {2: '/dev/hidraw6', 3: '/dev/hidraw7'}, 'x')
        with mock.patch.object(device, 'find', return_value=kb), mock.patch.object(daemon.os, 'open', open_), \
                self.assertRaises(Stop):
            daemon.effect_keys(lambda: {})(events)
        self.assertEqual(opened, ['/dev/hidraw6'])
        return [events.get_nowait() for _ in range(events.qsize())]

    def test_effect_change(self):
        with self.assertLogs('lightmount', 'DEBUG') as logs:
            events = self.run_source([key_event(FN), key_event(LEFT), key_event(FN_RIGHT), key_event(RIGHT)])
        self.assertEqual(events, ['effect'])
        self.assertIn('DEBUG:lightmount:Fn function 1b', logs.output)

    def test_plain_keys_ignored(self):
        # plain keys produce no event and no log line at all, not even in debug
        with mock.patch.object(daemon.log, 'debug') as debug:
            self.assertEqual(self.run_source([key_event(LEFT), key_event(RIGHT)]), [])
        debug.assert_not_called()

    def test_absent_keyboard_retries(self):
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            raise Stop
        with mock.patch.object(device, 'find', side_effect=device.DeviceError('absent')), \
                mock.patch.object(daemon.time, 'sleep', sleep), self.assertRaises(Stop):
            daemon.effect_keys(lambda: {})(None)
        self.assertEqual(sleeps, [daemon.KEYS_RETRY])


class Logging(unittest.TestCase):
    def test_journal_prefix(self):
        fmt = cli.JournalFormatter('%(message)s')
        record = logging.LogRecord('lightmount', logging.WARNING, '', 0, 'a\nb', None, None)
        self.assertEqual(fmt.format(record), '<4>a\n<4>b')
        record = logging.LogRecord('lightmount', logging.ERROR, '', 0, 'x', None, None)
        self.assertEqual(fmt.format(record), '<3>x')

    def test_watch_invalid_config_exit_code(self):
        f = tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False)
        f.write('[zones]\ntop = "nope"\n')
        f.close()
        self.addCleanup(os.unlink, f.name)
        with self.assertRaises(SystemExit) as ctx, self.assertLogs('lightmount', 'ERROR'), \
                contextlib.redirect_stderr(io.StringIO()):
            cli.main(['--config', f.name, 'watch'])
        self.assertEqual(ctx.exception.code, cli.EXIT_CONFIG)


if __name__ == '__main__':
    unittest.main()
