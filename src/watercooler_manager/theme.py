"""Read the desktop appearance without changing its settings."""

import os
import sys


def is_dark_theme():
    if sys.platform == 'win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                # The taskbar follows the system theme, which can differ from
                # the theme chosen for application windows.
                for name in ('SystemUsesLightTheme', 'AppsUseLightTheme'):
                    try:
                        return winreg.QueryValueEx(key, name)[0] == 0
                    except OSError:
                        continue
        except OSError:
            pass
    elif sys.platform == 'linux':
        try:
            from gi.repository import Gio, GLib
        except ImportError:
            return 'dark' in os.environ.get('GTK_THEME', '').lower()
        try:
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            for method in ('ReadOne', 'Read'):
                try:
                    value = connection.call_sync(
                        'org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                        'org.freedesktop.portal.Settings', method,
                        GLib.Variant('(ss)', ('org.freedesktop.appearance', 'color-scheme')),
                        None, Gio.DBusCallFlags.NO_AUTO_START, 750, None,
                    ).unpack()[0]
                    # Older portals return a doubly wrapped variant for Read.
                    while isinstance(value, GLib.Variant):
                        value = value.unpack()
                    if value in (1, 2):
                        return value == 1
                    break
                except GLib.Error:
                    continue
        except GLib.Error:
            pass
        override = os.environ.get('GTK_THEME')
        if override:
            return 'dark' in override.lower()
        source = Gio.SettingsSchemaSource.get_default()
        schema = source.lookup('org.gnome.desktop.interface', True) if source else None
        if schema:
            settings = Gio.Settings.new_full(schema, None, None)
            if schema.has_key('color-scheme'):
                preference = settings.get_string('color-scheme')
                if preference in ('prefer-dark', 'prefer-light'):
                    return preference == 'prefer-dark'
            if schema.has_key('gtk-theme'):
                return 'dark' in settings.get_string('gtk-theme').lower()
    return False
