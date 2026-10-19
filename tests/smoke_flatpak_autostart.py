"""Exercise the Background portal protocol on a private D-Bus session."""

from pathlib import Path
import sys
import threading

from gi.repository import Gio, GLib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from watercooler_manager.flatpak_autostart import set_enabled


def main():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    reply = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                         'org.freedesktop.DBus', 'RequestName',
                         GLib.Variant('(su)', ('org.freedesktop.portal.Desktop', 4)),
                         None, Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
    assert reply == 1, 'Run in an isolated dbus-run-session'
    xml = '''<node><interface name="org.freedesktop.portal.Background">
      <method name="RequestBackground">
        <arg type="s" direction="in"/><arg type="a{sv}" direction="in"/>
        <arg type="o" direction="out"/>
      </method></interface></node>'''
    state = {'denied': False, 'calls': []}

    def method(connection, sender, path, interface, name, parameters, invocation):
        parent, options = parameters.unpack()
        assert parent == ''
        assert options['commandline'] == ['watercooler-manager']
        assert options['dbus-activatable'] is False
        state['calls'].append(options['autostart'])
        path = ('/org/freedesktop/portal/desktop/request/'
                + sender.lstrip(':').replace('.', '_') + '/' + options['handle_token'])
        invocation.return_value(GLib.Variant('(o)', (path,)))

        def respond():
            connection.emit_signal(sender, path, 'org.freedesktop.portal.Request', 'Response',
                                   GLib.Variant('(ua{sv})', (1 if state['denied'] else 0, {
                                       'autostart': GLib.Variant('b', options['autostart']),
                                       'background': GLib.Variant('b', True),
                                   })))
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(25, respond)

    # Serve requests on a separate main context while the client runs its
    # nested main loop. This reproduces the real asynchronous portal reply.
    context = GLib.MainContext.new()
    context.push_thread_default()
    registration = bus.register_object('/org/freedesktop/portal/desktop',
                                      Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0],
                                      method, None, None)
    context.pop_thread_default()
    loop = GLib.MainLoop.new(context, False)
    thread = threading.Thread(target=loop.run, daemon=True)
    thread.start()
    try:
        set_enabled(True)
        set_enabled(False)
        state['denied'] = True
        try:
            set_enabled(True)
        except OSError:
            pass
        else:
            raise AssertionError('Denied request must fail')
        assert state['calls'] == [True, False, True], state
        print('Background portal enable, disable and permission denial passed')
    finally:
        bus.unregister_object(registration)
        loop.quit()
        thread.join(2)


if __name__ == '__main__':
    main()
