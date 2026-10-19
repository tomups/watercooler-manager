"""Check the Linux desktop requirements without changing cooler settings."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    try:
        from watercooler_manager.tray import pystray
        from gi.repository import Gio, GLib

        print(f"Python: {sys.version.split()[0]} ({sys.executable})")
        print(f"Tray backend: {pystray.Icon.__module__}")
        if not pystray.Icon.HAS_MENU:
            raise RuntimeError("The selected tray backend does not support menus")
        if pystray.Icon.__module__ == 'pystray._appindicator':
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            host = connection.call_sync(
                "org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher",
                "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", ("org.kde.StatusNotifierWatcher",
                                       "IsStatusNotifierHostRegistered")),
                None, Gio.DBusCallFlags.NONE, 3000, None,
            ).unpack()[0]
            if not host:
                raise RuntimeError("No active StatusNotifier tray host")
            print("StatusNotifier tray host: available")
        elif pystray.Icon.__module__ == 'pystray._gtk':
            print("Legacy GTK tray: check icon visibility in your X11 panel")
        else:
            raise RuntimeError("Select a native AppIndicator or GTK tray backend")
        connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        objects = connection.call_sync(
            "org.bluez", "/", "org.freedesktop.DBus.ObjectManager",
            "GetManagedObjects", None, None, Gio.DBusCallFlags.NONE, 3000, None,
        ).unpack()[0]
        adapters = [interfaces["org.bluez.Adapter1"] for interfaces in objects.values()
                    if "org.bluez.Adapter1" in interfaces]
        if not any(adapter.get("Powered") for adapter in adapters):
            raise RuntimeError("No powered Bluetooth adapter; enable Bluetooth first")
        print("BlueZ: powered adapter available")
    except Exception as error:
        print(f"Linux check failed: {error}\nSee the Linux instructions in README.md.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
