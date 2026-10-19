"""Launch generated XDG entries with GLib; no login, settings, or hardware I/O."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from watercooler_manager import linux_autostart


def launch(path):
    application = Gio.DesktopAppInfo.new_from_filename(str(path))
    assert application, f'GLib rejected {path}'
    pids = []
    application.launch_uris_as_manager([], None, GLib.SpawnFlags.DO_NOT_REAP_CHILD,
                                       None, None,
                                       lambda app, pid, data: pids.append(pid), None)
    assert len(pids) == 1, pids
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        pid, status = os.waitpid(pids[0], os.WNOHANG)
        if pid:
            assert os.waitstatus_to_exitcode(status) == 0, status
            return
        time.sleep(0.05)
    os.kill(pids[0], 9)
    os.waitpid(pids[0], 0)
    raise AssertionError('Autostart command did not exit within 10 seconds')


def main(executable=None):
    with tempfile.TemporaryDirectory(prefix='watercooler-autostart-') as directory:
        root = Path(directory)
        output = root / 'arguments.json'
        # Exercise actual desktop parsing, percent expansion, and argument
        # boundaries, including shell metacharacters that must stay literal.
        interpreter = root / 'Python café %f "quote" \\ $HOME `id` ; space = value'
        interpreter.write_text('#!' + sys.executable + '\n'
                               'import json, os, pathlib, sys\n'
                               'pathlib.Path(os.environ["WATERCOOLER_TEST_OUTPUT"]).write_text('
                               'json.dumps([sys.argv, os.environ.get("PYSTRAY_BACKEND")]))\n')
        interpreter.chmod(0o700)
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(root / 'config'),
                        XDG_CONFIG_DIRS=str(root / 'system'),
                        WATERCOOLER_TEST_OUTPUT=str(output), NO_AT_BRIDGE='1',
                        PYSTRAY_BACKEND='appindicator'):
            for frozen, backend in ((False, 'appindicator'), (True, 'appindicator'), (False, 'gtk')):
                with patch.object(sys, 'executable', str(interpreter)), \
                        patch.object(sys, 'frozen', frozen, create=True), \
                        patch.dict(os.environ, PYSTRAY_BACKEND=backend):
                    linux_autostart.set_enabled(True)
                path = linux_autostart.entry_path()
                subprocess.run(['desktop-file-validate', str(path)], check=True)
                launch(path)
                arguments, actual_backend = json.loads(output.read_text())
                expected = [str(interpreter)]
                if not frozen:
                    expected.append(str(ROOT / 'src/main.py'))
                assert arguments == expected, (arguments, expected)
                assert actual_backend == backend, (actual_backend, backend)
            # Launch the real source/binary help command from an unrelated CWD.
            # This proves the saved command works without touching the cooler.
            with patch.object(sys, 'frozen', bool(executable), create=True), \
                    patch.object(sys, 'executable', str(Path(executable).resolve())
                                 if executable else sys.executable):
                linux_autostart.set_enabled(True)
            path.write_text(path.read_text().replace('\nTerminal=', ' --help\nTerminal='))
            previous = Path.cwd()
            try:
                os.chdir(root)
                launch(path)
            finally:
                os.chdir(previous)
            linux_autostart.set_enabled(False)
            assert not linux_autostart.is_enabled()
            subprocess.run(['desktop-file-validate', str(path)], check=True)
    print('PASS: XDG launch, source/frozen commands, special paths, GTK override, and disable')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', help='Also launch the packaged executable with --help')
    main(parser.parse_args().executable)
