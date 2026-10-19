"""Build the native executable using the current Python environment."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--onedir', action='store_true',
                        help='Build an unpacked application for Linux packages')
    parser.add_argument('--distpath', default='dist')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        '--onedir' if args.onedir else '--onefile', '--distpath', args.distpath,
        "--icon", "src/icons/connected.png", "--add-data", "src/icons:icons",
        "--name", "WaterCoolerManager",
    ]
    if sys.platform == "win32":
        command.append("--windowed")
    elif sys.platform == "linux":
        # pystray chooses its backend dynamically. Keep the GTK fallback for
        # older X11 desktops as well as the default AppIndicator backend.
        command.extend([
            "--hidden-import", "pystray._appindicator",
            "--hidden-import", "pystray._gtk",
            "--hidden-import", "gi.repository.Gtk",
            "--hidden-import", "gi.repository.GdkPixbuf",
            "--hidden-import", "gi.repository.DBus",
            "--hidden-import", "gi.repository.AppIndicator3",
            "--hidden-import", "gi.repository.AyatanaAppIndicator3",
        ])
        # GTK links both display backends even on an X11-only system.
        # PyInstaller normally excludes Wayland libraries as system libraries;
        # include these explicitly for AppImage/Snap and minimal X11 desktops.
        from PyInstaller.depend.bindepend import resolve_library_path
        for library in ('libwayland-client.so.0', 'libwayland-cursor.so.0', 'libwayland-egl.so.1'):
            path = resolve_library_path(library)
            if path is None:
                raise RuntimeError(f'Install the Wayland runtime before building: {library}')
            command.extend(['--add-binary', str(path) + ':.'])
    command.append("src/main.py")
    subprocess.run(command, cwd=root, check=True)
    if sys.platform == 'linux' and args.onedir:
        # PyInstaller leaves libxcb to the desktop. Snap's minimal core24 base
        # has no X11 libraries: carry it separately for that format instead of
        # overriding other desktops' XCB (which must match graphics drivers).
        runtime = root / args.distpath / 'snap-runtime'
        runtime.mkdir(parents=True, exist_ok=True)
        path = resolve_library_path('libxcb.so.1')
        if path is None:
            raise RuntimeError('Install the XCB runtime before building')
        shutil.copy2(path, runtime / 'libxcb.so.1')


if __name__ == "__main__":
    main()
