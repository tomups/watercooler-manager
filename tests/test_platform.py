import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from PIL import Image
from watercooler_manager import WaterCoolerManager
from watercooler_manager.settings import Settings
from watercooler_manager import tray

ROOT = Path(__file__).resolve().parents[1]


class StartupTests(unittest.TestCase):
    def run_main(self, *arguments):
        environment = dict(os.environ, PYSTRAY_BACKEND='invalid')
        return subprocess.run([sys.executable, str(ROOT / 'src/main.py'), *arguments],
                              env=environment, capture_output=True, text=True, timeout=10)

    def test_help_works_without_a_tray_backend(self):
        result = self.run_main('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('usage:', result.stdout)

    def test_unavailable_backend_fails_with_actionable_error(self):
        result = self.run_main()
        self.assertEqual(result.returncode, 1)
        self.assertIn('could not start', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        if sys.platform == 'linux':
            self.assertIn('README.md', result.stderr)


class TrayPlatformTests(unittest.TestCase):
    def setUp(self):
        with patch.object(Settings, 'load'):
            self.app = WaterCoolerManager()
        self.addCleanup(self.app.loop.close)

    def test_linux_icons_are_small_and_distinct(self):
        with patch.object(tray.sys, 'platform', 'linux'):
            disconnected = self.app.tray.create_icon_image(False)
            connected = self.app.tray.create_icon_image(True)
        self.assertEqual(disconnected.size, (64, 64))
        self.assertEqual(connected.size, (64, 64))
        self.assertNotEqual(disconnected.tobytes(), connected.tobytes())

    def test_windows_keeps_original_icon_resolution(self):
        with Image.open(ROOT / 'src/icons/connected.png') as original:
            with patch.object(tray.sys, 'platform', 'win32'):
                connected = self.app.tray.create_icon_image(True)
            self.assertEqual(connected.size, original.size)
            self.assertEqual(connected.tobytes(), original.tobytes())

    def test_disconnected_icon_has_theme_appropriate_grey_and_a_slash(self):
        self.app.tray._dark_theme = False
        light = self.app.tray.create_icon_image(False)
        self.app.tray._dark_theme = True
        dark = self.app.tray.create_icon_image(False)
        self.assertEqual(light.getchannel('A').tobytes(), dark.getchannel('A').tobytes())
        point = (light.width // 3, light.height // 2)
        self.assertEqual(light.getpixel(point), (96, 96, 96, 255))
        self.assertEqual(dark.getpixel(point), (160, 160, 160, 255))
        with Image.open(ROOT / 'src/icons/disconnected.png') as original:
            original = original.resize(light.size, Image.Resampling.LANCZOS)
        self.assertNotEqual(light.getchannel('A').tobytes(), original.getchannel('A').tobytes())
        gap = (light.width // 2, round(light.height * .65))
        self.assertGreater(original.getpixel(gap)[3], 240)
        self.assertLess(light.getpixel(gap)[3], 64)

    def test_connected_icon_is_identical_in_both_themes(self):
        self.app.tray._dark_theme = False
        light = self.app.tray.create_icon_image(True)
        self.app.tray._dark_theme = True
        dark = self.app.tray.create_icon_image(True)
        self.assertEqual(light.tobytes(), dark.tobytes())

    def test_live_theme_switch_updates_disconnected_icon_only(self):
        self.app.tray.icon = Mock()
        with patch.object(tray, 'is_dark_theme', return_value=True):
            self.app.tray.refresh_theme()
        dark = self.app.tray.icon.icon
        self.assertEqual(dark.getpixel((dark.width // 3, dark.height // 2)), (160, 160, 160, 255))
        self.app.tray.update_connection_status(True)
        connected = self.app.tray.icon.icon
        with patch.object(tray, 'is_dark_theme', return_value=False):
            self.app.tray.refresh_theme()
        self.assertIs(self.app.tray.icon.icon, connected)
        self.app.tray.update_connection_status(False)
        light = self.app.tray.icon.icon
        self.assertEqual(light.getpixel((light.width // 3, light.height // 2)), (96, 96, 96, 255))

    def test_frozen_resource_path_does_not_need_a_package_directory(self):
        archived_module = ROOT / 'src/package_only_in_archive/tray.py'
        self.assertFalse(archived_module.parent.exists())
        with patch.object(tray, '__file__', str(archived_module)):
            self.assertIsInstance(self.app.tray.create_icon_image(), Image.Image)

    def test_backend_without_menus_is_rejected(self):
        with patch.object(tray.pystray.Icon, 'HAS_MENU', False):
            with self.assertRaisesRegex(RuntimeError, 'no menus'):
                self.app.tray.setup()

    def test_autostart_is_enabled_on_windows_and_linux(self):
        for platform, enabled in [('linux', True), ('unsupported', False), ('win32', True)]:
            with self.subTest(platform=platform), patch.object(tray.sys, 'platform', platform):
                menu = {item.text: item for item in self.app.tray.create_menu()}
                settings = {item.text: item for item in menu['Settings'].submenu}
                self.assertEqual(settings['Start on boot'].enabled, enabled)

    def test_autostart_failure_is_reported_without_changing_checked_state(self):
        self.app.tray.show_notification = Mock()
        self.app.tray.refresh = Mock()
        with patch.object(Settings, 'save') as save, \
                patch('watercooler_manager.settings.platform.system', return_value='Linux'), \
                patch('watercooler_manager.linux_autostart.set_enabled',
                      side_effect=PermissionError('Read-only config directory')):
            self.app.handle_autostart_settings()
        self.assertFalse(self.app.settings.auto_start)
        save.assert_not_called()
        self.app.tray.show_notification.assert_called_once()
        self.assertIn('Read-only config directory', self.app.tray.show_notification.call_args.args[0])
        self.app.tray.refresh.assert_called_once()

    def test_notification_unavailable_still_logs_message(self):
        self.app.tray.icon = Mock(HAS_NOTIFICATION=False)
        with self.assertLogs(tray.__name__, level='INFO') as messages:
            self.app.tray.show_notification('Bluetooth adapter unavailable')
        self.assertIn('Bluetooth adapter unavailable', messages.output[0])
        self.app.tray.icon.notify.assert_not_called()


if __name__ == '__main__':
    unittest.main()
