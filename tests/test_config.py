"""Config validation and the `check` command. No keyboard access."""
import contextlib, io, os, tempfile, unittest
from unittest import mock

import fixtures
from lightmount import cli, config, daemon, device, layout

EXAMPLE = os.path.join(fixtures.HERE, '..', 'install', 'config.toml')
# Format used until phase 2 (still accepted): predefined zones as plain colors
LEGACY = '''
[zones]
top = "49412f"
knob = "ff2a00"
keys = "ff2a00"
left = "0000ff"
right = "ff0000"

[alerts]
normal = "00ff00"
critical = "ff0000"
error = "0000ff"
duration = 1.25
'''


def parse(text, alert_zone=None):
    import tomllib
    if alert_zone:  # zone tests: point the alerts at the zone under test
        text += f'\n[alerts]\nzone = "{alert_zone}"\n'
    return config.validate(tomllib.loads(text))


def legacy_entries():
    """Entries as built before the configurable zones (phase 1 daemon)."""
    rgb = config.rgb
    return ([(i, rgb('49412f')) for i in layout.TOP] + [(i, rgb('ff2a00')) for i in layout.KNOB]
            + [(i, rgb('ff2a00')) for i in layout.KEYS]
            + [(i, rgb('0000ff')) for i in layout.LEFT] + [(i, rgb('ff0000')) for i in layout.RIGHT])


class Compatibility(unittest.TestCase):
    def test_legacy_format(self):
        cfg, errors, warnings = parse(LEGACY)
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual(daemon.zone_entries(cfg), legacy_entries())

    def test_defaults(self):
        cfg, errors, warnings = config.validate({})
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual(daemon.zone_entries(cfg), legacy_entries())

    def test_example(self):
        cfg, warnings = config.load(EXAMPLE)
        self.assertEqual(warnings, [])
        self.assertEqual(daemon.zone_entries(cfg), legacy_entries())

    def test_alert_zone_is_top(self):
        cfg, _, _ = parse(LEGACY)
        self.assertEqual(cfg['zones'][cfg['alerts']['zone']]['leds'], list(layout.TOP))
        self.assertEqual(cfg['alerts']['colors']['error'], (0, 0, 0xff))
        self.assertEqual(cfg['alerts']['sources'], {'notifications': True, 'shell': True})


class Zones(unittest.TestCase):
    def test_custom_zone(self):
        cfg, errors, _ = parse('[zones.wasd]\nleds = ["5d", "73-75"]\ncolor = "#00FF00"\n', 'wasd')
        self.assertEqual(errors, [])
        self.assertEqual(cfg['zones']['wasd'], {'leds': [0x5d, 0x73, 0x74, 0x75], 'color': (0, 255, 0)})

    def test_predefined_table_without_leds(self):
        cfg, errors, _ = parse('[zones.knob]\ncolor = "ff0000"\n', 'knob')
        self.assertEqual(errors, [])
        self.assertEqual(cfg['zones']['knob']['leds'], [0x2d])

    def test_dim(self):
        cfg, errors, _ = parse('[zones.top]\ncolor = "f4dbae"\ndim = 0.5\n')
        self.assertEqual(errors, [])
        self.assertEqual(cfg['zones']['top']['color'], (0x7a, 0x6e, 0x57))

    def test_range_spans_unused(self):
        cfg, errors, _ = parse('[zones.keys]\nleds = ["60-64"]\ncolor = "ffffff"\n', 'keys')
        self.assertEqual(errors, [])
        self.assertEqual(cfg['zones']['keys']['leds'], [0x60, 0x61, 0x63, 0x64])

    def test_integer_indexes(self):
        cfg, errors, _ = parse('[zones.a]\nleds = [0x2d, 46]\ncolor = "ffffff"\n', 'a')
        self.assertEqual(errors, [])
        self.assertEqual(cfg['zones']['a']['leds'], [0x2d, 0x2e])

    def test_uncovered_leds_warn(self):
        _, errors, warnings = parse('[zones]\ntop = "ffffff"\n')
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn('2d-61, 63-88, 8a-a7', warnings[0])  # 62 and 89 do not exist


class Errors(unittest.TestCase):
    def assertError(self, text, *fragments):
        _, errors, _ = parse(text)
        self.assertTrue(errors, f'no error for {text!r}')
        joined = '\n'.join(errors)
        for fragment in fragments:
            self.assertIn(fragment, joined)

    def test_bad_colors(self):
        for value in ('"ff00"', '"gg0000"', '"#ff00000"'):
            with self.subTest(value=value):
                self.assertError(f'[zones]\ntop = {value}\n', 'zones.top', 'RRGGBB')
        for value in ('255', 'true'):
            with self.subTest(value=value):
                self.assertError(f'[zones]\ntop = {value}\n', 'zones.top', 'color string or a table')

    def test_alert_color(self):
        self.assertError('[alerts]\nnormal = "green"\n', 'alerts.normal', 'RRGGBB')

    def test_out_of_range(self):
        self.assertError('[zones.a]\nleds = ["a0-b0"]\ncolor = "ffffff"\n', 'LED a8 out of range')

    def test_unused_single(self):
        self.assertError('[zones.a]\nleds = ["62"]\ncolor = "ffffff"\n', 'LED 62 is not used')

    def test_reversed_range(self):
        self.assertError('[zones.a]\nleds = ["10-05"]\ncolor = "ffffff"\n', 'reversed')

    def test_not_hex(self):
        self.assertError('[zones.a]\nleds = ["zz"]\ncolor = "ffffff"\n', "'zz' is not a hex index")

    def test_empty_leds(self):
        self.assertError('[zones.a]\nleds = []\ncolor = "ffffff"\n', 'non-empty list')

    def test_overlap(self):
        self.assertError('[zones.a]\nleds = ["00-10"]\ncolor = "ffffff"\n'
                         '[zones.b]\nleds = ["10-20"]\ncolor = "ffffff"\n', 'zones.b: LED 10 is already in zone a')

    def test_custom_zone_as_string(self):
        self.assertError('[zones]\nwasd = "ffffff"\n', 'not a predefined zone')

    def test_custom_zone_without_leds(self):
        self.assertError('[zones.wasd]\ncolor = "ffffff"\n', 'zones.wasd: leds missing')

    def test_zone_without_color(self):
        self.assertError('[zones.top]\nleds = ["00"]\n', 'color missing')

    def test_dim(self):
        for value in ('1.5', '-0.1', '"half"'):
            with self.subTest(value=value):
                self.assertError(f'[zones.top]\ncolor = "ffffff"\ndim = {value}\n', 'zones.top.dim')

    def test_no_zone(self):
        self.assertError('[zones]\n', 'no zone defined')

    def test_alert_zone_unknown(self):
        self.assertError('[alerts]\nzone = "knobb"\n', 'no zone named "knobb"')

    def test_alert_zone_removed(self):
        self.assertError('[zones]\nkeys = "ffffff"\n', 'alerts.zone', 'no zone named "top"')

    def test_duration(self):
        for value in ('0', '-1', '61', '"1s"', 'true'):
            with self.subTest(value=value):
                self.assertError(f'[alerts]\nduration = {value}\n', 'alerts.duration')

    def test_unknown_keys(self):
        self.assertError('[zone]\ntop = "ffffff"\n', 'zone: unknown key')
        self.assertError('[alerts]\nnormall = "ffffff"\n', 'alerts.normall: unknown key')
        self.assertError('[zones.top]\ncolour = "ffffff"\n', 'zones.top.colour: unknown key')
        self.assertError('[alerts.sources]\ndbus = true\n', 'alerts.sources.dbus: unknown key')
        self.assertError('[device]\nusb = "1-7"\n', 'device.usb: unknown key')

    def test_types(self):
        self.assertError('[device]\nallow_unknown_firmware = "yes"\n', 'expected bool')
        self.assertError('[device]\nusb_path = 17\n', 'expected str')
        self.assertError('[alerts.sources]\nshell = 1\n', 'expected bool')

    def test_every_error_reported(self):
        _, errors, _ = parse('[zones]\ntop = "x"\nknob = "y"\n[alerts]\nduration = 0\n')
        self.assertEqual(len(errors), 3)


class Files(unittest.TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_missing_file_uses_defaults(self):
        cfg, warnings = config.load('/nonexistent/lightmount.toml')
        self.assertEqual(daemon.zone_entries(cfg), legacy_entries())

    def test_syntax_error(self):
        with self.assertRaisesRegex(config.ConfigError, 'TOML syntax'):
            config.load(self.write('[zones\n'))

    def test_errors_prefixed_with_path(self):
        path = self.write('[zones]\ntop = "x"\n')
        with self.assertRaises(config.ConfigError) as ctx:
            config.load(path)
        self.assertTrue(all(e.startswith(path) for e in ctx.exception.errors))


class CheckCommand(Files):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        # `check` must never reach the keyboard
        with mock.patch.object(device, 'scan', side_effect=AssertionError('device scanned')), \
                mock.patch.object(device, 'vendor', side_effect=AssertionError('device opened')), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as ctx:
            cli.main(list(argv))
        return ctx.exception.code, out.getvalue(), err.getvalue()

    def test_ok(self):
        code, out, _ = self.run_cli('--config', EXAMPLE, 'check')
        self.assertEqual(code, 0)
        self.assertIn('config OK: 5 zones, 166 LEDs', out)

    def test_errors(self):
        code, _, err = self.run_cli('--config', self.write('[zones]\ntop = "x"\n'), 'check')
        self.assertEqual(code, 1)
        self.assertIn('error:', err)
        self.assertIn('zones.top', err)

    def test_warnings_only(self):
        code, out, err = self.run_cli('--config', self.write('[zones]\ntop = "ffffff"\n'), 'check')
        self.assertEqual(code, 0)
        self.assertIn('warning:', err)

    def test_syntax_error(self):
        code, _, _ = self.run_cli('--config', self.write('[zones\n'), 'check')
        self.assertIn('TOML syntax', str(code))

    def test_apply_refuses_invalid_config(self):
        code, _, _ = self.run_cli('--config', self.write('[zones]\ntop = "x"\n'), 'apply')
        self.assertIn('lightmount check', str(code))


if __name__ == '__main__':
    unittest.main()
