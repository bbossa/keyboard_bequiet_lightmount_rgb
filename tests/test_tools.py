"""The tools/ scripts still import against the package (they only run with captures or a keyboard).

tools/ is the private reverse-engineering kit: not in the public repository, skipped there.
"""
import importlib, os, sys, unittest

import fixtures

TOOLS = os.path.join(fixtures.HERE, '..', 'tools')
sys.path.insert(0, TOOLS)


@unittest.skipUnless(os.path.isdir(TOOLS), 'tools/ not present (public checkout)')
class Imports(unittest.TestCase):
    def test_import(self):
        # map_keys.py is left out: it reads the keyboard as soon as it is imported
        for name in ('lightmount_color', 'lightmount_zones', 'extract_fixtures'):
            with self.subTest(name=name):
                importlib.import_module(name)


if __name__ == '__main__':
    unittest.main()
