"""A private AT-SPI registry for the Linux tray smoke test."""

import os


class AccessibilityHost:
    def __init__(self, connection):
        from gi.repository import Gio, GLib

        self.requests = []
        self.objects = []
        root = '/org/a11y/atspi/accessible/root'
        xml = '''<node>
          <interface name="org.a11y.Bus">
            <method name="GetAddress"><arg type="s" direction="out"/></method>
          </interface>
          <interface name="org.a11y.atspi.Socket">
            <method name="Embed">
              <arg type="(so)" direction="in"/><arg type="(so)" direction="out"/>
            </method>
          </interface>
          <interface name="org.a11y.atspi.Registry">
            <method name="GetRegisteredEvents"><arg type="a(ss)" direction="out"/></method>
          </interface>
          <interface name="org.a11y.atspi.DeviceEventController">
            <method name="GetKeystrokeListeners">
              <arg type="a(souua(iisi)u(bbb))" direction="out"/>
            </method>
            <method name="GetDeviceEventListeners"/>
          </interface>
        </node>'''

        def method(connection, sender, path, interface, name, parameters, invocation):
            self.requests.append(name)
            if name == 'GetAddress':
                result = GLib.Variant('(s)', (os.environ['DBUS_SESSION_BUS_ADDRESS'],))
            elif name == 'Embed':
                result = GLib.Variant('((so))', (('org.a11y.atspi.Registry', root),))
            elif name == 'GetRegisteredEvents':
                result = GLib.Variant('(a(ss))', ([],))
            elif name == 'GetKeystrokeListeners':
                result = GLib.Variant('(a(souua(iisi)u(bbb)))', ([],))
            else:
                # Modern registries removed this API. Reply immediately so an
                # old bridge fails without waiting for the D-Bus timeout.
                invocation.return_dbus_error('org.freedesktop.DBus.Error.UnknownMethod',
                                             'GetDeviceEventListeners has been removed')
                return
            invocation.return_value(result)

        for name in ('org.a11y.Bus', 'org.a11y.atspi.Registry'):
            result = connection.call_sync(
                'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                'RequestName', GLib.Variant('(su)', (name, 4)),
                None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
            assert result == 1, 'Use accessibility tests inside an isolated D-Bus session'
        paths = ('/org/a11y/bus', root, '/org/a11y/atspi/registry',
                 '/org/a11y/atspi/registry/deviceeventcontroller')
        for interface, path in zip(Gio.DBusNodeInfo.new_for_xml(xml).interfaces, paths):
            self.objects.append(connection.register_object(path, interface, method, None, None))

    def check(self, stderr):
        assert 'Embed' in self.requests, 'Accessibility was disabled or failed to register'
        assert 'GetRegisteredEvents' in self.requests, self.requests
        assert 'GetKeystrokeListeners' in self.requests, self.requests
        assert 'GetDeviceEventListeners' not in self.requests, self.requests
        assert 'atk-bridge:' not in stderr, stderr
        print('PASS: accessibility stays enabled without querying the removed AT-SPI API')
