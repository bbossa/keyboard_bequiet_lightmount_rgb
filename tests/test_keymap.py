"""Key map (keymap.py) consistency and the `calibrate` command, with a fake keyboard."""
import contextlib, io, unittest
from unittest import mock

import fixtures  # noqa: F401  (sys.path)
from lightmount import cli, config, daemon, keymap, layout


class KeyMap(unittest.TestCase):
    def test_covers_every_led_once(self):
        self.assertEqual(sorted(keymap.ALL), layout.ALL)
        self.assertEqual(len(keymap.TOP) + len(keymap.KNOB) + len(keymap.KEYS)
                         + len(keymap.LEFT) + len(keymap.RIGHT), len(layout.ALL))

    def test_zones_match_layout(self):
        self.assertEqual(sorted(keymap.KEYS), layout.KEYS)
        self.assertEqual(sorted(keymap.TOP), list(layout.TOP))
        self.assertEqual(sorted(keymap.KNOB), list(layout.KNOB))
        self.assertEqual(sorted(keymap.LEFT), list(layout.LEFT))
        self.assertEqual(sorted(keymap.RIGHT), list(layout.RIGHT))

    def test_checked_on_the_keyboard(self):
        # indexes checked visually before the key map existed (NOTES.md)
        checked = {0x2e: 'Esc', 0x30: 'F2', 0x73: 'K', 0x88: '§ !', 0x8a: 'Shift'}
        self.assertEqual({i: keymap.KEYS[i][0] for i in checked}, checked)

    def test_rows_left_to_right(self):
        # vendor indexes follow the rows, left to right: x grows within a row
        rows = {}
        for i in sorted(keymap.KEYS):
            rows.setdefault(keymap.KEYS[i][2], []).append(keymap.KEYS[i][1])
        self.assertEqual(len(rows), 6)
        for y, xs in rows.items():
            self.assertEqual(xs, sorted(xs), f'row y={y}')


class Calibrate(unittest.TestCase):
    def run_calibrate(self, answers, start=0):
        writes = []
        answers = iter(answers)
        args = mock.Mock(config='/nonexistent/lightmount.toml', start=start)
        out = io.StringIO()
        with mock.patch.object(daemon, 'write', lambda cfg, entries: writes.append(entries)), \
                contextlib.redirect_stdout(out):
            code = cli.calibrate(args, ask=lambda prompt: next(answers))
        return code, writes, out.getvalue()

    def test_all_match(self):
        leds = sorted({**keymap.KNOB, **keymap.KEYS})
        code, writes, out = self.run_calibrate([''] * len(leds))
        self.assertEqual(code, 0)
        self.assertEqual(len(writes), 1 + len(leds) + 1)  # all off, one per LED, zones
        self.assertEqual(writes[1], [(leds[0], cli.CALIBRATE_ON)])
        self.assertEqual(writes[2], [(leds[0], cli.CALIBRATE_OFF), (leds[1], cli.CALIBRATE_ON)])
        self.assertEqual(writes[-1], daemon.zone_entries(config.validate({})[0]))
        self.assertIn('0 mismatch', out)

    def test_mismatch_and_quit(self):
        code, writes, out = self.run_calibrate(['', 'Enter', 'q'], start=0x76)
        self.assertEqual(code, 1)
        self.assertIn("77: expected 'µ *', lit: 'Enter'", out)
        self.assertEqual(writes[-1], daemon.zone_entries(config.validate({})[0]))  # zones restored

    def test_zones_restored_on_interrupt(self):
        def ask(prompt):
            raise KeyboardInterrupt
        writes = []
        args = mock.Mock(config='/nonexistent/lightmount.toml', start=0)
        with mock.patch.object(daemon, 'write', lambda cfg, entries: writes.append(entries)), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            cli.calibrate(args, ask=ask)
        self.assertEqual(writes[-1], daemon.zone_entries(config.validate({})[0]))
