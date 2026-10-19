"""Exercise the native Linux tray through D-Bus, without Bluetooth or settings I/O.

Run in a desktop session: .venv/bin/python tests/smoke_linux_tray.py
"""

from pathlib import Path
import argparse
import os
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def run_child():
    from unittest.mock import patch
    from watercooler_manager import WaterCoolerManager
    from watercooler_manager.settings import Settings

    with patch.object(Settings, "load"):
        app = WaterCoolerManager()
    # Exercise real native menu dispatch while keeping hardware untouched.
    app.tray.on_connect = lambda: app.tray.update_connection_status(True)
    app.tray.on_disconnect = lambda: app.tray.update_connection_status(False)
    app.tray.on_exit = app.tray.stop
    try:
        app.tray.setup()
        app.tray.run()
    finally:
        app.loop.close()


class VirtualHost:
    """A minimal StatusNotifier host and notification service for isolated CI."""

    def __init__(self, connection):
        from gi.repository import Gio, GLib

        self.items = []
        self.color_scheme = 2
        self.loop = GLib.MainLoop()
        xml = '''<node>
          <interface name="org.kde.StatusNotifierWatcher">
            <method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
            <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
            <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
            <property name="ProtocolVersion" type="i" access="read"/>
            <signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
          </interface>
          <interface name="org.freedesktop.Notifications">
            <method name="CloseNotification"><arg type="u" direction="in"/></method>
          </interface>
          <interface name="org.freedesktop.portal.Settings">
            <method name="ReadOne">
              <arg type="s" direction="in"/><arg type="s" direction="in"/>
              <arg type="v" direction="out"/>
            </method>
          </interface>
        </node>'''
        interfaces = Gio.DBusNodeInfo.new_for_xml(xml).interfaces

        def method(connection, sender, path, interface, name, parameters, invocation):
            if name == 'RegisterStatusNotifierItem':
                item = parameters.unpack()[0]
                item = sender + item if item.startswith('/') else item + '/StatusNotifierItem'
                self.items.append(item)
                connection.emit_signal(None, path, interface, 'StatusNotifierItemRegistered',
                                       GLib.Variant('(s)', (item,)))
            elif name == 'ReadOne':
                assert parameters.unpack() == ('org.freedesktop.appearance', 'color-scheme')
                invocation.return_value(GLib.Variant('(v)', (GLib.Variant('u', self.color_scheme),)))
                return
            invocation.return_value(None)

        def property_value(connection, sender, path, interface, name):
            return {'RegisteredStatusNotifierItems': GLib.Variant('as', self.items),
                    'IsStatusNotifierHostRegistered': GLib.Variant('b', True),
                    'ProtocolVersion': GLib.Variant('i', 0)}[name]

        self.objects = []
        services = ('org.kde.StatusNotifierWatcher', 'org.freedesktop.Notifications',
                    'org.freedesktop.portal.Desktop')
        paths = ('/StatusNotifierWatcher', '/org/freedesktop/Notifications',
                 '/org/freedesktop/portal/desktop')
        for interface, service, path in zip(interfaces, services, paths):
            result = connection.call_sync(
                'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                'RequestName', GLib.Variant('(su)', (service, 4)),
                None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
            assert result == 1, 'Use --virtual-host inside an isolated dbus-run-session'
            self.objects.append(connection.register_object(path, interface, method, property_value, None))
        self.thread = threading.Thread(target=self.loop.run, daemon=True)
        self.thread.start()


def run_parent(executable=None, virtual_host=False):
    from gi.repository import Gio, GLib
    from PIL import Image

    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    host = VirtualHost(connection) if virtual_host else None

    def call(service, path, interface, method, parameters=None):
        return connection.call_sync(service, path, interface, method, parameters,
                                    None, Gio.DBusCallFlags.NONE, 3000, None).unpack()

    def property_value(service, path, interface, name):
        return call(service, path, "org.freedesktop.DBus.Properties", "Get",
                    GLib.Variant("(ss)", (interface, name)))[0]

    def registered():
        return property_value("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher",
                              "org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems")

    def until(predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise AssertionError(f"Tray exited early ({child.returncode})")
            result = predicate()
            if result:
                return result
            time.sleep(0.1)
        raise AssertionError("Timed out waiting for tray update")

    before = set(registered())
    command = [str(Path(executable).resolve())] if executable else [sys.executable, __file__, "--child"]
    child = subprocess.Popen(command, cwd=ROOT,
                             # A private D-Bus session using the real display
                             # must not replace the desktop's AT-SPI socket.
                             env=dict(os.environ, NO_AT_BRIDGE='1'),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    icon_paths = []
    try:
        item = until(lambda: next(iter(set(registered()) - before), None))
        service, separator, suffix = item.partition("/")
        path = "/" + suffix if separator else "/StatusNotifierItem"
        interface = "org.kde.StatusNotifierItem"
        get = lambda name: property_value(service, path, interface, name)
        assert get("Id") == "WaterCooler", get("Id")
        assert get("Status") == "Active", get("Status")
        menu_path = get("Menu")

        def menu():
            layout = call(service, menu_path, "com.canonical.dbusmenu", "GetLayout",
                          GLib.Variant("(iias)", (0, -1, [])))[1]
            labels = {}

            def visit(node):
                identifier, properties, children = node
                if "label" in properties:
                    labels[properties["label"].replace("_", "")] = identifier
                for child_node in children:
                    visit(child_node)

            visit(layout)
            return labels

        def click(label):
            identifier = menu()[label]
            call(service, menu_path, "com.canonical.dbusmenu", "Event",
                 GLib.Variant("(isvu)", (identifier, "clicked", GLib.Variant("i", 0), 0)))

        def image():
            filename = get("IconName")
            assert Path(filename).is_file(), filename
            with Image.open(filename) as bitmap:
                assert bitmap.size == (64, 64), bitmap.size
            icon_paths.append(filename)
            return filename

        labels = menu()
        for label in ("Connect", "Mode", "Pump", "Fan", "RGB", "Water filling", "Settings", "Exit"):
            assert label in labels, (label, labels)
        disconnected_icon = image()
        if host:
            with Image.open(disconnected_icon) as bitmap:
                assert bitmap.getpixel((bitmap.width // 3, bitmap.height // 2)) == (96, 96, 96, 255)
            host.color_scheme = 1
            until(lambda: get('IconName') != disconnected_icon)
            disconnected_icon = image()
            with Image.open(disconnected_icon) as bitmap:
                assert bitmap.getpixel((bitmap.width // 3, bitmap.height // 2)) == (160, 160, 160, 255)
        if executable:
            # A real app's Connect/Exit actions can touch hardware/settings.
            # Inspect startup only; the source test exercises simulated clicks.
            child.terminate()
            child.communicate(timeout=10)
            Path(disconnected_icon).unlink(missing_ok=True)
            print('PASS: frozen executable registers a native tray, full menu, and theme-aware icon')
            return
        click("Connect")
        until(lambda: "Disconnect" in menu())
        until(lambda: get("IconName") != disconnected_icon)
        connected_icon = image()
        assert not Path(disconnected_icon).exists(), "Old icon was not cleaned up"
        if host:
            host.color_scheme = 2
            time.sleep(3)
            assert get('IconName') == connected_icon, 'Theme changed the colored connected icon'
        click("Disconnect")
        until(lambda: "Connect" in menu())
        until(lambda: get("IconName") != connected_icon)
        last_icon = image()
        if host:
            with Image.open(last_icon) as bitmap:
                assert bitmap.getpixel((bitmap.width // 3, bitmap.height // 2)) == (96, 96, 96, 255)
        click("Exit")
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 0, (child.returncode, stdout, stderr)
        assert not any(Path(filename).exists() for filename in icon_paths), "Icon leaked after exit"
        print("PASS: native tray registration, full menu, Connect/Disconnect dispatch, "
              "64px icons, updates, Exit, and temporary-file cleanup")
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
        if child.returncode and not executable:
            print(child.communicate()[1], file=sys.stderr)
        if host:
            host.loop.quit()
            host.thread.join(timeout=5)


if __name__ == "__main__":
    if sys.argv[1:] == ["--child"]:
        run_child()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--virtual-host', action='store_true', help='Use only in an isolated D-Bus session')
        parser.add_argument('--executable', help='Check frozen startup without clicking controls or saving settings')
        args = parser.parse_args()
        run_parent(args.executable, args.virtual_host)
