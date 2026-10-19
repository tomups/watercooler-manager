"""Build the native executable using the current Python environment."""

from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
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
            "--hidden-import", "gi.repository.AppIndicator3",
            "--hidden-import", "gi.repository.AyatanaAppIndicator3",
        ])
    command.append("src/main.py")
    subprocess.run(command, cwd=root, check=True)


if __name__ == "__main__":
    main()
