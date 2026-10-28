"""lightmount-gui parts that do not need GTK: drawing geometry and the zone model."""
import os, tempfile, tomllib, unittest

import fixtures  # noqa: F401  (sys.path)
from lightmount import config, layout, save
from lightmount.gui import geometry, model

EXAMPLE = os.path.join(os.path.dirname(__file__), '..', 'install', 'config.toml')


class Geometry(unittest.TestCase):
    def test_every_led_drawn_once(self):
        indexes = [s.index for s in geometry.shapes()]
        self.assertEqual(sorted(indexes), sorted(layout.ALL))

    def test_keys_do_not_overlap(self):
        keys = geometry.keys()
        for n, a in enumerate(keys):
            for b in keys[n + 1:]:
                for x, y, w, h in a.rects:
                    self.assertFalse(b.intersects(x + 0.01, y + 0.01, x + w - 0.01, y + h - 0.01),
                                     f'{a.legend} / {b.legend}')

    def test_iso_sizes(self):
        by_legend = {}
        for s in geometry.keys():
            by_legend.setdefault(s.legend, []).append(s)
        self.assertEqual(by_legend['Back'][0].rects[0][2], 2)
        self.assertEqual(by_legend['Space'][0].rects[0][2], 6.25)
        self.assertEqual([s.rects[0][2] for s in by_legend['Shift']], [1.25, 2.75])
        enter = [s for s in by_legend['Enter'] if len(s.rects) == 2]
        self.assertEqual(len(enter), 1)  # the L-shaped ISO Enter; the pad Enter is 2 rows high
        self.assertEqual(by_legend['Knob'][0].rects, [(0.0, 0.0, 1, 1)])

    def test_rows_ends_aligned(self):
        # the main block is 15 u wide on every row (ISO): last key of the main block ends at MAIN + 15
        ends = {}
        for s in geometry.keys():
            for x, y, w, h in s.rects:
                if x < geometry.NAV - 0.1:
                    ends[y] = max(ends.get(y, 0), x + w)
        for y in (1.5, 2.5, 4.5, 5.5):
            self.assertAlmostEqual(ends[y], geometry.MAIN + 15)

    def test_hit(self):
        esc = next(s for s in geometry.keys() if s.legend == 'Esc')
        self.assertTrue(esc.contains(geometry.MAIN + 0.5, 0.5))
        self.assertFalse(esc.contains(geometry.MAIN + 1.5, 0.5))
        self.assertTrue(esc.intersects(geometry.MAIN + 0.9, 0.9, geometry.MAIN + 3, 3))


def example():
    with open(EXAMPLE, 'rb') as f:
        return tomllib.load(f)


class Model(unittest.TestCase):
    def test_defaults(self):
        m = model.Model({})
        self.assertEqual(list(m.zones), ['top', 'knob', 'keys', 'left', 'right'])
        self.assertEqual(m.errors, [])
        self.assertEqual(config.validate(m.raw())[0], config.validate({})[0])

    def test_example_round_trip(self):
        raw = example()
        m = model.Model(raw)
        self.assertEqual(config.validate(m.raw())[0], config.validate(raw)[0])

    def test_dim_kept_apart(self):
        m = model.Model({'zones': {'top': {'leds': ['00-2c'], 'color': 'f4dbae', 'dim': 0.3}}})
        self.assertEqual(m.zones['top'].color, 'f4dbae')
        self.assertEqual(m.zones['top'].rgb, tuple(round(c * 0.3) for c in (0xf4, 0xdb, 0xae)))
        self.assertEqual(m.raw()['zones']['top'], {'leds': ['00-2c'], 'color': 'f4dbae', 'dim': 0.3})

    def test_compact_spans_unused(self):
        self.assertEqual(model.compact(layout.KEYS), ['2e-9d'])
        self.assertEqual(model.compact({0, 1, 2, 5}), ['00-02', '05'])
        self.assertEqual(model.compact(set()), [])

    def test_assign_moves_leds(self):
        m = model.Model({})
        m.assign({0x2e, 0x2f}, 'knob')
        self.assertIn(0x2e, m.zones['knob'].leds)
        self.assertNotIn(0x2e, m.zones['keys'].leds)
        self.assertEqual(config.validate(m.raw())[1], [])

    def test_new_zone(self):
        m = model.Model({})
        name = m.new_zone({0x9e, 0x9f}, 'ffffff')
        self.assertEqual(name, 'zone6')
        self.assertEqual(m.owner(0x9e), name)
        self.assertEqual(m.zones['left'].leds, set(range(0xa0, 0xa3)))

    def test_unassign_warns(self):
        m = model.Model({})
        m.unassign({0x00})
        errors, warnings = m.validate()
        self.assertEqual(errors, [])
        self.assertTrue(any('LEDs in no zone' in w for w in warnings))
        self.assertEqual(m.unassigned(), [0x00])

    def test_empty_zone_not_written(self):
        m = model.Model({})
        m.unassign(layout.KNOB)
        self.assertNotIn('knob', m.raw()['zones'])
        self.assertTrue(any('empty zones' in w for w in m.validate()[1]))

    def test_rename_follows_alert_zone(self):
        m = model.Model({})
        self.assertTrue(m.rename('top', 'strip'))
        self.assertEqual(m.alerts['zone'], 'strip')
        self.assertEqual(list(m.zones)[0], 'strip')  # order kept
        self.assertFalse(m.rename('strip', 'keys'))
        self.assertFalse(m.rename('strip', 'with space'))

    def test_delete_alert_zone_invalid(self):
        m = model.Model({})
        m.delete('top')
        errors, _ = m.validate()
        self.assertTrue(any('alerts.zone' in e for e in errors))

    def test_bad_file_values_reported(self):
        m = model.Model({'zones': {'top': {'leds': ['zz'], 'color': 'nope'}}, 'alerts': {'normal': '#00FF00'}})
        self.assertEqual(len(m.errors), 2)
        self.assertEqual(m.alerts['normal'], '00ff00')

    def test_save_from_model(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'config.toml')
            m = model.Model(example())
            m.zones['knob'].color = '00ff00'
            raw = m.raw()
            save.write(path, raw['zones'], raw['alerts'])
            self.assertEqual(config.load(path)[0]['zones']['knob']['color'], (0, 0xff, 0))


if __name__ == '__main__':
    unittest.main()
