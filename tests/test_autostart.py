import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from watercooler_manager import linux_autostart
from watercooler_manager.settings import Settings
from watercooler_manager import settings as settings_module


class LinuxAutostartTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / 'custom configuration'
        self.system_config = self.root / 'system'
        self.enterContext(patch.dict(os.environ, XDG_CONFIG_HOME=str(self.config),
                                     XDG_CONFIG_DIRS=str(self.system_config),
                                     PYSTRAY_BACKEND='appindicator'))

    def test_enable_and_disable_survive_settings_reload(self):
        with patch.object(Settings, 'CONFIG_FILE', str(self.root / 'settings.json')), \
                patch.object(settings_module.platform, 'system', return_value='Linux'):
            settings = Settings()
            self.assertFalse(settings.auto_start)
            settings.set_autostart(True)
            self.assertTrue(linux_autostart.entry_path().is_file())
            self.assertTrue(Settings().auto_start)
            settings.set_autostart(False)
            self.assertFalse(Settings().auto_start)
        self.assertIn('Hidden=true', linux_autostart.entry_path().read_text())

    def test_missing_or_relative_config_home_uses_default(self):
        with patch.object(Path, 'home', return_value=self.root):
            for value in ('', 'relative/path'):
                with self.subTest(value=value), patch.dict(os.environ, XDG_CONFIG_HOME=value):
                    self.assertEqual(linux_autostart.entry_path(),
                                     self.root / '.config/autostart' / linux_autostart.FILENAME)
            with patch.dict(os.environ):
                del os.environ['XDG_CONFIG_HOME']
                self.assertEqual(linux_autostart.entry_path(),
                                 self.root / '.config/autostart' / linux_autostart.FILENAME)

    def test_source_entry_preserves_venv_python_and_absolute_script(self):
        interpreter = self.root / 'venv with spaces/bin/python'
        with patch.object(sys, 'executable', str(interpreter)), \
                patch.object(sys, 'frozen', False, create=True):
            linux_autostart.set_enabled(True)
        text = linux_autostart.entry_path().read_text()
        script = Path(linux_autostart.__file__).resolve().parents[1] / 'main.py'
        self.assertIn(linux_autostart._quote_argument(str(interpreter)) + ' '
                      + linux_autostart._quote_argument(str(script)) + '\n', text)
        self.assertNotIn('OnlyShowIn', text)
        self.assertNotIn('NotShowIn', text)

    def test_frozen_entry_uses_persistent_executable(self):
        executable = self.root / 'installed app/WaterCoolerManager'
        with patch.object(sys, 'executable', str(executable)), \
                patch.object(sys, 'frozen', True, create=True):
            linux_autostart.set_enabled(True)
        text = linux_autostart.entry_path().read_text()
        self.assertIn(linux_autostart._quote_argument(str(executable)) + '\n', text)
        self.assertNotIn('main.py', text)
        self.assertNotIn('_MEI', text)

    def test_legacy_gtk_choice_is_preserved(self):
        with patch.dict(os.environ, PYSTRAY_BACKEND='gtk'):
            linux_autostart.set_enabled(True)
        self.assertIn('PYSTRAY_BACKEND=gtk ', linux_autostart.entry_path().read_text())

    def test_desktop_entry_overrides_stale_json_preference(self):
        with patch.object(settings_module.platform, 'system', return_value='Linux'), \
                patch.object(Settings, '_load_from_file',
                             lambda settings: setattr(settings, 'auto_start', True)):
            self.assertFalse(Settings().auto_start)
        linux_autostart.set_enabled(True)
        with patch.object(settings_module.platform, 'system', return_value='Linux'), \
                patch.object(Settings, '_load_from_file'):
            self.assertTrue(Settings().auto_start)
        text = linux_autostart.entry_path().read_text()
        linux_autostart.entry_path().write_text(text + 'X-GNOME-Autostart-enabled=false\n')
        with patch.object(settings_module.platform, 'system', return_value='Linux'), \
                patch.object(Settings, '_load_from_file'):
            self.assertFalse(Settings().auto_start)

    def test_user_entry_overrides_system_entry(self):
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(self.system_config)):
            linux_autostart.set_enabled(True)
        self.assertTrue(linux_autostart.is_enabled())
        linux_autostart.set_enabled(False)
        self.assertFalse(linux_autostart.is_enabled())
        linux_autostart.set_enabled(True)
        self.assertTrue(linux_autostart.is_enabled())

    def test_invalid_entry_does_not_break_startup(self):
        path = linux_autostart.entry_path()
        path.parent.mkdir(parents=True)
        for content in ('garbage', '[Desktop Entry]\nType=Application\nExec=test\nHidden=invalid\n',
                        '[Desktop Entry]\nType=Application\n', '[Other]\nExec=test\n'):
            with self.subTest(content=content):
                path.write_text(content)
                self.assertFalse(linux_autostart.is_enabled())

    def test_failed_atomic_write_keeps_previous_entry_and_cleans_tempfile(self):
        linux_autostart.set_enabled(False)
        path = linux_autostart.entry_path()
        before = path.read_bytes()
        with patch.object(Path, 'replace', side_effect=PermissionError('Read only')):
            with self.assertRaises(PermissionError):
                linux_autostart.set_enabled(True)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_unwritable_config_does_not_mark_autostart_enabled(self):
        with patch.object(Settings, 'load'):
            settings = Settings()
        self.config.write_text('a file blocks the directory')
        with patch.object(settings_module.platform, 'system', return_value='Linux'), \
                patch.object(settings, 'save') as save:
            with self.assertRaises(OSError):
                settings.set_autostart(True)
        self.assertFalse(settings.auto_start)
        save.assert_not_called()


class WindowsAutostartTests(unittest.TestCase):
    def test_windows_shortcut_enable_and_disable_are_preserved(self):
        with patch.object(Settings, 'load'):
            settings = Settings()
        shell = Mock()
        shell.startup.return_value = 'startup'
        with patch.object(settings_module.platform, 'system', return_value='Windows'), \
                patch.object(settings_module, 'winshell', shell, create=True), \
                patch.object(settings, 'save') as save, \
                patch.object(settings_module.os.path, 'exists', return_value=True), \
                patch.object(settings_module.os, 'remove') as remove:
            settings.set_autostart(True)
            self.assertTrue(settings.auto_start)
            shell.CreateShortcut.assert_called_once_with(
                Path=os.path.join('startup',
                                  Path(settings_module.executable).stem + '.lnk'),
                Target=settings_module.executable, Icon=(settings_module.executable, 0),
                Description='Utility to manage LCT21001 / LCT22002 laptop water coolers')
            settings.set_autostart(False)
            self.assertFalse(settings.auto_start)
            remove.assert_called_once_with(shell.CreateShortcut.call_args.kwargs['Path'])
            self.assertEqual(save.call_count, 2)


class PackagedAutostartTests(unittest.TestCase):
    def test_packaged_and_appimage_launchers_use_persistent_entry_point(self):
        launcher = str(Path(tempfile.gettempdir()) / 'My App.AppImage')
        with patch.dict(os.environ, WATERCOOLER_LAUNCHER=launcher, PYSTRAY_BACKEND='gtk'):
            command = linux_autostart._command()
        self.assertEqual(command[-1], launcher)
        self.assertEqual(command[2], 'PYSTRAY_BACKEND=gtk exec "$@"')
        self.assertNotIn('main.py', ' '.join(command))
        self.assertNotIn('_MEI', ' '.join(command))

    def test_snap_uses_session_agent_without_forwarding_shell_arguments(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, SNAP='/snap/watercooler-manager/42',
                           SNAP_USER_DATA=directory):
            linux_autostart.set_enabled(True)
            self.assertTrue(linux_autostart.is_enabled())
            path = Path(directory) / '.config/autostart/watercooler-manager.desktop'
            self.assertIn('Exec="watercooler-manager"\n', path.read_text())
            self.assertNotIn('/42', path.read_text())

    def test_flatpak_calls_portal_and_never_writes_host_autostart(self):
        with patch.dict(os.environ, FLATPAK_ID='io.github.tomups.WatercoolerManager'), \
                patch('watercooler_manager.flatpak_autostart.set_enabled') as portal, \
                patch.object(linux_autostart, 'entry_path') as entry:
            linux_autostart.set_enabled(True)
            portal.assert_called_once_with(True)
            entry.assert_not_called()

    def test_portal_denial_does_not_save_enabled_setting(self):
        with patch.object(Settings, 'load'):
            settings = Settings()
        with patch.dict(os.environ, FLATPAK_ID='io.github.tomups.WatercoolerManager'), \
                patch.object(settings_module.platform, 'system', return_value='Linux'), \
                patch('watercooler_manager.flatpak_autostart.set_enabled',
                      side_effect=OSError('Permission denied')), \
                patch.object(settings, 'save') as save:
            with self.assertRaisesRegex(OSError, 'Permission denied'):
                settings.set_autostart(True)
            self.assertFalse(settings.auto_start)
            save.assert_not_called()

    def test_flatpak_reload_keeps_portal_confirmed_setting(self):
        with patch.dict(os.environ, FLATPAK_ID='io.github.tomups.WatercoolerManager'), \
                patch.object(settings_module.platform, 'system', return_value='Linux'), \
                patch.object(Settings, '_load_from_file',
                             lambda settings: setattr(settings, 'auto_start', True)), \
                patch.object(linux_autostart, 'is_enabled') as entry:
            self.assertTrue(Settings().auto_start)
            entry.assert_not_called()

    def test_sandbox_preferences_use_persistent_private_directory(self):
        base = Path(tempfile.gettempdir())
        with patch.dict(os.environ, FLATPAK_ID='io.github.tomups.WatercoolerManager',
                        XDG_CONFIG_HOME=str(base / 'sandbox/config')):
            self.assertEqual(settings_module._config_file(),
                             str(base / 'sandbox/config/watercooler-manager/settings.json'))
        with patch.dict(os.environ, SNAP_USER_COMMON=str(base / 'snap/app/common')):
            self.assertEqual(settings_module._config_file(),
                             str(base / 'snap/app/common/settings.json'))


if __name__ == '__main__':
    unittest.main()
