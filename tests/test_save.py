"""Writing [zones] and [alerts] back to the config file, keeping the rest."""
import os, stat, tempfile, tomllib, unittest

import fixtures  # noqa: F401  (sys.path)
from lightmount import config, save

EXAMPLE = os.path.join(os.path.dirname(__file__), '..', 'install', 'config.toml')


def example():
    with open(EXAMPLE, encoding='utf-8') as f:
        return f.read()


class Render(unittest.TestCase):
    def test_values(self):
        text = save.render(('t',), {'s': 'a"b\\c', 'b': True, 'i': 3, 'f': 0.3, 'l': ['00-2c', 45]})
        self.assertEqual(tomllib.loads(text)['t'], {'s': 'a"b\\c', 'b': True, 'i': 3, 'f': 0.3, 'l': ['00-2c', 45]})

    def test_subtables_after_scalars(self):
        text = save.render(('alerts',), {'sources': {'shell': False}, 'zone': 'top'})
        self.assertEqual(text, '[alerts]\nzone = "top"\n\n[alerts.sources]\nshell = false')

    def test_quoted_key(self):
        text = save.render(('zones',), {'side strips': {'leds': ['9e-a7'], 'color': 'ffffff'}})
        self.assertIn('[zones."side strips"]', text)
        self.assertIn('side strips', tomllib.loads(text)['zones'])

    def test_unsupported(self):
        for bad in (float('nan'), None, 'a\x01b'):
            with self.subTest(bad=bad), self.assertRaises(save.SaveError):
                save.render(('t',), {'k': bad})


class Dumps(unittest.TestCase):
    def setUp(self):
        self.text = example()
        self.raw = tomllib.loads(self.text)

    def test_round_trip(self):
        new = save.dumps(self.text, self.raw['zones'], self.raw['alerts'])
        self.assertEqual(tomllib.loads(new), self.raw)
        self.assertEqual(config.validate(tomllib.loads(new))[0], config.validate(self.raw)[0])

    def test_comments_above_tables_kept(self):
        new = save.dumps(self.text, self.raw['zones'], self.raw['alerts'])
        for line in ('# --- zones ---', '# --- alerts ---', '# Several Light Mount keyboards plugged in',
                     '#   2e-9d  keys (62 and 89 do not exist; ranges may span them)'):
            self.assertIn(line, new)
        self.assertTrue(new.startswith('# lightmount configuration'))
        # the zones are written where they were: before the alerts
        self.assertLess(new.index('[zones.top]'), new.index('# --- alerts ---'))

    def test_end_of_line_comments_kept(self):
        new = save.dumps(self.text, self.raw['zones'], self.raw['alerts'])
        for line in ('color = "49412f"   # pokegawa warm white f4dbae, dimmed',
                     'zone = "top"         # any zone above, e.g. "knob" for a discreet alert',
                     'notifications = true # D-Bus notifications (only the urgency is read, never the content)'):
            self.assertIn(line, new)

    def test_end_of_line_comment_after_longer_value(self):
        alerts = dict(self.raw['alerts'], zone='a-much-longer-zone-name')
        zones = dict(self.raw['zones'])
        zones['a-much-longer-zone-name'] = zones.pop('top')
        new = save.dumps(self.text, zones, alerts)
        self.assertIn('zone = "a-much-longer-zone-name" # any zone above', new)

    def test_hash_inside_value_is_not_a_comment(self):
        text = '[zones]\ntop = "#ffffff"  # white\n\n[alerts]\nnormal = "#00ff00"\n'
        new = save.dumps(text, {'top': '#000000'}, {'normal': '#00ff00'})
        self.assertIn('top = "#000000"  # white', new)
        self.assertIn('normal = "#00ff00"\n', new)

    def test_comment_of_removed_key_dropped(self):
        alerts = {k: v for k, v in self.raw['alerts'].items() if k != 'duration'}
        self.assertNotIn('# seconds', save.dumps(self.text, self.raw['zones'], alerts))

    def test_other_comments_inside_replaced_tables_lost(self):
        text = '[zones]\n# full line\ntop = "ffffff"\n'
        self.assertNotIn('# full line', save.dumps(text, {'top': 'ffffff'}, {'zone': 'top'}))

    def test_change_one_color(self):
        zones = dict(self.raw['zones'], knob={'leds': ['2d'], 'color': '00ff00'})
        cfg = config.validate(tomllib.loads(save.dumps(self.text, zones, self.raw['alerts'])))[0]
        self.assertEqual(cfg['zones']['knob']['color'], (0, 0xff, 0))
        self.assertEqual(cfg['zones']['top'], config.validate(self.raw)[0]['zones']['top'])

    def test_no_blank_line_pile_up(self):
        new = save.dumps(self.text, self.raw['zones'], self.raw['alerts'])
        self.assertNotIn('\n\n\n', new)

    def test_missing_tables_appended(self):
        text = '[device]\nallow_unknown_firmware = false\n'
        new = save.dumps(text, {'top': 'ffffff'}, {'zone': 'top'})
        self.assertTrue(new.startswith(text))
        self.assertEqual(tomllib.loads(new)['zones'], {'top': 'ffffff'})

    def test_empty_file(self):
        new = save.dumps('', {'top': 'ffffff'}, {'zone': 'top'})
        self.assertEqual(new, '[zones]\ntop = "ffffff"\n\n[alerts]\nzone = "top"\n')

    def test_table_after_alerts_kept(self):
        text = self.text + '\n# poll the mode\n[daemon]\npoll_interval = 5\n'
        new = save.dumps(text, self.raw['zones'], self.raw['alerts'])
        self.assertEqual(tomllib.loads(new)['daemon'], {'poll_interval': 5})
        self.assertIn('# poll the mode\n[daemon]', new)

    def test_invalid_config_refused(self):
        zones = dict(self.raw['zones'], knob={'leds': ['00'], 'color': 'ffffff'})  # LED 00 is in top
        with self.assertRaises(config.ConfigError):
            save.dumps(self.text, zones, self.raw['alerts'])

    def test_unusual_layout_refused(self):
        # zones as dotted keys of the root table: no [zones] header to replace
        with self.assertRaises(save.SaveError):
            save.dumps('zones.top = "ffffff"\n', {'top': '000000'}, {'zone': 'top'})

    def test_header_in_multiline_string_refused(self):
        text = '[device]\nusb_path = """\n[zones]\n"""\n'
        with self.assertRaises(save.SaveError):
            save.dumps(text, {'top': 'ffffff'}, {'zone': 'top'})


class Write(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lightmount-save-')
        self.addCleanup(lambda: __import__('shutil').rmtree(self.dir))
        self.path = os.path.join(self.dir, 'lightmount', 'config.toml')
        raw = tomllib.loads(example())
        self.zones, self.alerts = raw['zones'], raw['alerts']

    def put(self, text, mode=0o600):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(text)
        os.chmod(self.path, mode)

    def test_new_file(self):
        umask = os.umask(0o022)
        self.addCleanup(os.umask, umask)
        save.write(self.path, self.zones, self.alerts)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o644)
        self.assertEqual(config.load(self.path)[0]['alerts']['zone'], 'top')
        self.assertFalse(os.path.exists(self.path + '.bak'))

    def test_backup_and_mode(self):
        self.put(example(), 0o640)
        save.write(self.path, dict(self.zones, knob={'leds': ['2d'], 'color': '00ff00'}), self.alerts)
        with open(self.path + '.bak', encoding='utf-8') as f:
            self.assertEqual(f.read(), example())
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o640)
        self.assertEqual(config.load(self.path)[0]['zones']['knob']['color'], (0, 0xff, 0))

    def test_invalid_leaves_file_untouched(self):
        self.put(example())
        with self.assertRaises(config.ConfigError):
            save.write(self.path, {'nope': 'ffffff'}, self.alerts)
        with open(self.path, encoding='utf-8') as f:
            self.assertEqual(f.read(), example())
        self.assertEqual(sorted(os.listdir(os.path.dirname(self.path))), ['config.toml'])

    def test_warnings_returned(self):
        warnings = save.write(self.path, {'top': 'ffffff'}, {'zone': 'top'})
        self.assertTrue(any('LEDs in no zone' in w for w in warnings))


if __name__ == '__main__':
    unittest.main()
