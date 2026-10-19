"""Request login startup through the desktop portal, without host file access."""

import uuid


def set_enabled(enabled):
    from gi.repository import Gio, GLib

    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    token = 'watercooler_' + uuid.uuid4().hex
    sender = connection.get_unique_name().lstrip(':').replace('.', '_')
    request_path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
    response = []
    loop = GLib.MainLoop()

    def received(bus, sender, path, interface, signal, parameters):
        if path == request_path:
            response.append(parameters.unpack())
            loop.quit()

    subscription = connection.signal_subscribe(
        'org.freedesktop.portal.Desktop', 'org.freedesktop.portal.Request',
        'Response', None, None, Gio.DBusSignalFlags.NONE, received)
    timed_out = False

    def timeout():
        nonlocal timed_out
        timed_out = True
        loop.quit()
        return GLib.SOURCE_REMOVE

    timer = GLib.timeout_add_seconds(120, timeout)
    try:
        options = {
            'handle_token': GLib.Variant('s', token),
            'reason': GLib.Variant('s', 'Keep water cooler controls available in the system tray'),
            'autostart': GLib.Variant('b', enabled),
            'commandline': GLib.Variant('as', ['watercooler-manager']),
            'dbus-activatable': GLib.Variant('b', False),
        }
        request_path = connection.call_sync(
            'org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
            'org.freedesktop.portal.Background', 'RequestBackground',
            GLib.Variant('(sa{sv})', ('', options)), GLib.VariantType.new('(o)'),
            Gio.DBusCallFlags.NONE, 10000, None).unpack()[0]
        if not response:
            loop.run()
        if not response:
            connection.call_sync('org.freedesktop.portal.Desktop', request_path,
                                 'org.freedesktop.portal.Request', 'Close', None,
                                 None, Gio.DBusCallFlags.NONE, 1000, None)
            raise OSError('The desktop did not answer the autostart permission request')
        code, result = response[0]
        if code != 0 or result.get('autostart', False) != enabled:
            raise OSError('The desktop did not grant the requested autostart setting')
    except GLib.Error as error:
        raise OSError('Autostart needs a working desktop Background portal: ' + str(error)) from error
    finally:
        connection.signal_unsubscribe(subscription)
        if not timed_out:
            GLib.source_remove(timer)
