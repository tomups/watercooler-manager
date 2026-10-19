"""Per-user desktop autostart using the freedesktop.org XDG specifications."""

import configparser
import os
from pathlib import Path
import sys
import tempfile


FILENAME = 'watercooler-manager.desktop'


def _config_home():
    if os.environ.get('SNAP_USER_DATA'):
        return Path(os.environ['SNAP_USER_DATA']) / '.config'
    configured = Path(os.environ.get('XDG_CONFIG_HOME', ''))
    # The base-directory specification requires ignoring relative paths.
    return configured if configured.is_absolute() else Path.home() / '.config'


def entry_path():
    return _config_home() / 'autostart' / FILENAME


def is_enabled():
    directories = [_config_home()]
    directories.extend(Path(directory) for directory in
                       (os.environ.get('XDG_CONFIG_DIRS') or '/etc/xdg').split(os.pathsep)
                       if Path(directory).is_absolute())
    for directory in directories:
        path = directory / 'autostart' / FILENAME
        try:
            with path.open(encoding='utf-8') as stream:
                entry = configparser.ConfigParser(interpolation=None)
                entry.read_file(stream)
            desktop = entry['Desktop Entry']
            return (desktop.get('Type') == 'Application'
                    and bool(desktop.get('Exec'))
                    and not desktop.getboolean('Hidden', fallback=False)
                    and desktop.getboolean('X-GNOME-Autostart-enabled', fallback=True))
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError, configparser.Error, KeyError, ValueError):
            return False
    return False


def _escape(value):
    return (value.replace('\\', '\\\\').replace('\n', r'\n')
            .replace('\r', r'\r').replace('\t', r'\t'))


def _quote_argument(argument):
    # Exec uses desktop-entry quoting, not shell quoting. The string-value
    # escape layer is decoded before the command-line quoting layer.
    quoted = ''.join('\\' + char if char in '"`$\\' else char
                     for char in argument.replace('%', '%%'))
    return '"' + _escape(quoted) + '"'


def _command():
    if os.environ.get('SNAP'):
        # snapd's session agent re-enters the snap and forwards Exec arguments.
        # Do not forward our native shell wrapper or a revision-specific path.
        return ['watercooler-manager']
    if os.environ.get('WATERCOOLER_LAUNCHER'):
        launcher = Path(os.environ['WATERCOOLER_LAUNCHER'])
        if not launcher.is_absolute():
            raise ValueError('The packaged launcher must be an absolute path')
        return ['/bin/sh', '-c', 'exec "$@"', 'watercooler-manager', str(launcher)]
    # GLib checks the executable before expanding %% escapes; the desktop
    # standard also disallows '=' in that token. A fixed shell wrapper keeps
    # unusual installation paths in arguments. Paths never enter shell code.
    script = 'exec "$@"'
    if os.environ.get('PYSTRAY_BACKEND') == 'gtk':
        # Preserve a deliberate legacy-tray choice on older X11 desktops.
        script = 'PYSTRAY_BACKEND=gtk ' + script
    command = ['/bin/sh', '-c', script, 'watercooler-manager']
    # Keep the venv interpreter path: resolving its symlink would lose the
    # environment. Frozen executables must never point into _MEIPASS.
    command.append(str(Path(sys.executable).absolute()))
    if not getattr(sys, 'frozen', False):
        command.append(str(Path(__file__).resolve().parents[1] / 'main.py'))
    return command


def set_enabled(enabled):
    if os.environ.get('FLATPAK_ID'):
        from .flatpak_autostart import set_enabled as portal_set_enabled
        portal_set_enabled(enabled)
        return
    path = entry_path()
    if enabled:
        command = ' '.join(_quote_argument(argument) for argument in _command())
        content = ('[Desktop Entry]\nType=Application\nVersion=1.0\n'
                   'Name=Watercooler Manager\n'
                   'Comment=Bluetooth water cooler controls\n'
                   f'Exec={command}\nTerminal=false\n')
    else:
        # An override also disables a matching system-wide installation.
        content = ('[Desktop Entry]\nType=Application\n'
                   'Name=Watercooler Manager\nHidden=true\n')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=path.parent, prefix='.' + FILENAME,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
