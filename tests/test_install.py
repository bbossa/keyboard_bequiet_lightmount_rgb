"""install.sh / uninstall.sh in a temporary HOME, with a fake systemctl. Never touches the real setup."""
import os, shutil, subprocess, tempfile, unittest

import fixtures

REPO = os.path.realpath(os.path.join(fixtures.HERE, '..'))
INSTALL = os.path.join(REPO, 'install', 'install.sh')
UNINSTALL = os.path.join(REPO, 'install', 'uninstall.sh')

# Fake systemctl: logs its arguments; enable --now / disable --now toggle an "active" state file.
SYSTEMCTL = '''#!/bin/bash
echo "$*" >> "$FAKE_STATE/systemctl.log"
case "$*" in
    "--user show-environment") exit 0 ;;
    "--user enable --now lightmount.service") touch "$FAKE_STATE/active" ;;
    "--user disable --now lightmount.service") rm -f "$FAKE_STATE/active" ;;
    "--user is-enabled --quiet lightmount.service" | "--user is-active --quiet lightmount.service")
        [ -e "$FAKE_STATE/active" ] ;;
esac
'''


@unittest.skipUnless(shutil.which('bash'), 'bash needed')
class Install(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='lightmount-install-')
        self.addCleanup(shutil.rmtree, self.root)
        self.home = os.path.join(self.root, 'home')
        self.state = os.path.join(self.root, 'state')
        self.runtime = os.path.join(self.root, 'run')
        bin_dir = os.path.join(self.root, 'bin')
        for d in (self.home, self.state, self.runtime, bin_dir):
            os.makedirs(d)
        with open(os.path.join(bin_dir, 'systemctl'), 'w') as f:
            f.write(SYSTEMCTL)
        os.chmod(os.path.join(bin_dir, 'systemctl'), 0o755)
        self.env = {'HOME': self.home, 'FAKE_STATE': self.state, 'XDG_RUNTIME_DIR': self.runtime,
                    'PATH': f'{bin_dir}:{os.path.join(self.home, ".local/bin")}:/usr/bin:/bin', 'LANG': 'C'}

    def run_script(self, script, *args, ok=True):
        result = subprocess.run(['bash', script, *args], env=self.env, capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def path(self, relative):
        return os.path.join(self.home, relative)

    def systemctl_log(self):
        try:
            with open(os.path.join(self.state, 'systemctl.log')) as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    def files(self):
        return sorted(os.path.relpath(os.path.join(d, f), self.home)
                      for d, _, names in os.walk(self.home) for f in names)

    def test_dry_run_changes_nothing(self):
        out = self.run_script(INSTALL, '--dry-run').stdout
        self.assertEqual(self.files(), [])
        self.assertIn('would install', out)
        self.assertNotIn('--user enable --now lightmount.service', self.systemctl_log())

    def test_install(self):
        out = self.run_script(INSTALL).stdout
        self.assertEqual(os.readlink(self.path('.local/bin/lightmount')), os.path.join(REPO, 'bin/lightmount'))
        for name in ('.config/lightmount/config.toml', '.config/systemd/user/lightmount.service'):
            self.assertTrue(os.path.isfile(self.path(name)), name)
        if shutil.which('fish'):
            self.assertTrue(os.path.isfile(self.path('.config/fish/conf.d/lightmount.fish')))
        self.assertTrue(os.path.isfile(self.path('.local/share/lightmount/lightmount.bash')))
        self.assertIn('source ~/.local/share/lightmount/lightmount.bash', out)
        log = self.systemctl_log()
        self.assertIn('--user daemon-reload', log)
        self.assertIn('--user enable --now lightmount.service', log)
        self.assertIn('config OK', out)  # lightmount check through the installed link

    def test_idempotent(self):
        self.run_script(INSTALL)
        before = self.systemctl_log()
        out = self.run_script(INSTALL).stdout
        new_calls = self.systemctl_log()[len(before):]
        self.assertNotIn('installed', out)
        self.assertNotIn('updated', out)
        self.assertNotIn('--user daemon-reload', new_calls)
        self.assertNotIn('--user restart lightmount.service', new_calls)
        self.assertIn('running    lightmount.service', out)

    def test_changed_unit_restarts(self):
        self.run_script(INSTALL)
        with open(self.path('.config/systemd/user/lightmount.service'), 'a') as f:
            f.write('# local edit\n')
        out = self.run_script(INSTALL).stdout
        self.assertIn('updated  ' + self.path('.config/systemd/user/lightmount.service'), out)
        self.assertIn('--user restart lightmount.service', self.systemctl_log())

    def test_existing_config_kept(self):
        os.makedirs(self.path('.config/lightmount'))
        with open(self.path('.config/lightmount/config.toml'), 'w') as f:
            f.write('[zones]\ntop = "ffffff"\nkeys = "000000"\nknob = "000000"\nleft = "000000"\nright = "000000"\n')
        out = self.run_script(INSTALL).stdout
        self.assertIn('kept', out)
        with open(self.path('.config/lightmount/config.toml')) as f:
            self.assertIn('top = "ffffff"', f.read())

    def test_invalid_config_reported(self):
        os.makedirs(self.path('.config/lightmount'))
        with open(self.path('.config/lightmount/config.toml'), 'w') as f:
            f.write('[zones]\ntop = "nope"\n')
        result = self.run_script(INSTALL)
        self.assertIn('the config has errors', result.stderr)

    def test_foreign_command_not_replaced(self):
        os.makedirs(self.path('.local/bin'))
        with open(self.path('.local/bin/lightmount'), 'w') as f:
            f.write('#!/bin/sh\n')
        result = self.run_script(INSTALL, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('is not a symlink', result.stderr)

    def test_udev_needs_root(self):
        if os.getuid() == 0:
            self.skipTest('running as root')
        result = self.run_script(INSTALL, '--udev', ok=False)
        self.assertIn('needs root', result.stderr)

    def test_unknown_option(self):
        self.assertEqual(self.run_script(INSTALL, '--bogus', ok=False).returncode, 2)

    def test_uninstall(self):
        self.run_script(INSTALL)
        os.mkfifo(os.path.join(self.runtime, 'lightmount.fifo'))
        dry = self.run_script(UNINSTALL, '--dry-run').stdout
        self.assertIn('would remove', dry)
        self.assertTrue(os.path.lexists(self.path('.local/bin/lightmount')))
        out = self.run_script(UNINSTALL).stdout
        self.assertEqual(self.files(), ['.config/lightmount/config.toml'])
        self.assertIn('--purge-config', out)
        self.assertFalse(os.path.exists(os.path.join(self.runtime, 'lightmount.fifo')))
        self.assertIn('--user disable --now lightmount.service', self.systemctl_log())
        self.run_script(UNINSTALL, '--purge-config')
        self.assertEqual(self.files(), [])

    def test_uninstall_keeps_foreign_command(self):
        os.makedirs(self.path('.local/bin'))
        os.symlink('/usr/bin/true', self.path('.local/bin/lightmount'))
        out = self.run_script(UNINSTALL).stdout
        self.assertIn('does not point to this checkout', out)
        self.assertTrue(os.path.lexists(self.path('.local/bin/lightmount')))


@unittest.skipUnless(shutil.which('bash'), 'bash needed')
class Hooks(unittest.TestCase):
    def test_syntax(self):
        install = os.path.join(REPO, 'install')
        subprocess.run(['bash', '-n', os.path.join(install, 'lightmount.bash')], check=True)
        for shell, flag in (('fish', '-n'), ('zsh', '-n')):
            if shutil.which(shell):
                subprocess.run([shell, flag, os.path.join(install, f'lightmount.{shell}')], check=True)

    @unittest.skipUnless(shutil.which('script'), 'script (util-linux) needed for a pty')
    def test_bash_hook(self):
        self.check_hook(f'bash --rcfile {REPO}/install/lightmount.bash -i', [])

    @unittest.skipUnless(shutil.which('script') and shutil.which('zsh'), 'script and zsh needed')
    def test_zsh_hook(self):
        # -f: no startup file; the hook is sourced as the first typed line
        self.check_hook('zsh -f -i', [f'source {REPO}/install/lightmount.zsh'])

    def check_hook(self, shell, setup):
        """Real interactive shell on a pty, with a fake lightmount (the real one must never run here)."""
        root = tempfile.mkdtemp(prefix='lightmount-hook-')
        self.addCleanup(shutil.rmtree, root)
        os.mkfifo(os.path.join(root, 'lightmount.fifo'))
        fake = os.path.join(root, 'lightmount')
        with open(fake, 'w') as f:
            f.write(f'#!/bin/bash\necho "$*" >> {root}/calls\n')
        os.chmod(fake, 0o755)
        typed = setup + [f'command -v lightmount > {root}/resolved',
                 'false', '', '', 'true', '(exit 130)', '(exit 2)', '(exit 2)', ' false', 'sleep 0.3', 'exit']
        # SHELL: script runs its command through $SHELL, which must not load a user config
        env = {'HOME': root, 'ZDOTDIR': root, 'SHELL': '/bin/bash', 'PATH': f'{root}:/usr/bin:/bin',
               'XDG_RUNTIME_DIR': root, 'TERM': 'dumb', 'HISTCONTROL': 'ignoreboth'}
        subprocess.run(['script', '-q', '-c', shell, '/dev/null'],
                       input='\n'.join(typed) + '\n', env=env, capture_output=True, text=True, timeout=20)
        with open(os.path.join(root, 'resolved')) as f:
            self.assertEqual(f.read().strip(), fake)
        self.assertFalse(os.path.exists(os.path.join(root, 'lightmount.lock')))  # real lightmount never ran
        # false, (exit 2) twice (ignoredups must not hide a repeat), " false" (ignorespace);
        # not: empty lines, true, Ctrl+C (130)
        with open(os.path.join(root, 'calls')) as f:
            self.assertEqual(f.read().splitlines(), ['alert error'] * 4)

if __name__ == '__main__':
    unittest.main()
