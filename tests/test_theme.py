import builtins
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from watercooler_manager import theme


class ThemeTests(unittest.TestCase):
    def windows_theme(self, values):
        registry = MagicMock()

        def query(key, name):
            if name not in values:
                raise FileNotFoundError(name)
            return values[name], 0

        registry.QueryValueEx.side_effect = query
        with patch.object(theme.sys, 'platform', 'win32'), patch.dict(sys.modules, winreg=registry):
            return theme.is_dark_theme()

    def test_windows_uses_taskbar_theme_when_application_theme_differs(self):
        self.assertTrue(self.windows_theme({'SystemUsesLightTheme': 0, 'AppsUseLightTheme': 1}))
        self.assertFalse(self.windows_theme({'SystemUsesLightTheme': 1, 'AppsUseLightTheme': 0}))

    def test_windows_falls_back_when_theme_keys_are_missing(self):
        self.assertTrue(self.windows_theme({'AppsUseLightTheme': 0}))
        self.assertFalse(self.windows_theme({}))

    def linux_theme(self, preference, legacy=False):
        class Variant:
            def __init__(self, signature, value):
                self.value = value

            def unpack(self):
                return self.value

        class PortalError(Exception):
            pass

        connection = Mock()
        response = Variant('(v)', (Variant('v', Variant('u', preference)),))
        connection.call_sync.side_effect = [PortalError(), response] if legacy else [response]
        gio = Mock()
        gio.bus_get_sync.return_value = connection
        repository = SimpleNamespace(Gio=gio, GLib=SimpleNamespace(Variant=Variant, Error=PortalError))
        original_import = builtins.__import__

        def import_module(name, *args, **kwargs):
            return repository if name == 'gi.repository' else original_import(name, *args, **kwargs)

        with patch.object(theme.sys, 'platform', 'linux'), patch('builtins.__import__', import_module):
            return theme.is_dark_theme()

    def test_linux_reads_portal_dark_and_light_preferences(self):
        self.assertTrue(self.linux_theme(1))
        self.assertFalse(self.linux_theme(2))

    def test_linux_supports_legacy_portals_with_nested_variants(self):
        self.assertTrue(self.linux_theme(1, legacy=True))
        self.assertFalse(self.linux_theme(2, legacy=True))


if __name__ == '__main__':
    unittest.main()
