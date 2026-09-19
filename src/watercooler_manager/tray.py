
APP_VERSION = "v1.3.0"

import pystray
from PIL import Image
from typing import Callable
import os
import webbrowser

class SystemTrayIcon:
    def __init__(self, on_connect: Callable, on_disconnect: Callable, on_mode_settings: Callable,
                 on_pump_settings: Callable, on_fan_settings: Callable,
                 on_rgb_settings: Callable, on_autostart_settings: Callable, on_autoconnect_settings: Callable, on_exit: Callable, settings, version: str = APP_VERSION,
                 on_priming=None, on_cancel_priming=None, on_standby=None):
        self.icon = None
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_mode_settings= on_mode_settings
        self.on_pump_settings = on_pump_settings
        self.on_fan_settings = on_fan_settings
        self.on_rgb_settings = on_rgb_settings
        self.on_autostart_settings = on_autostart_settings
        self.on_autoconnect_settings = on_autoconnect_settings
        self.on_exit = on_exit
        self.connected = False
        self.settings = settings
        self.version = version
        self.on_priming = on_priming
        self.on_cancel_priming = on_cancel_priming
        self.on_standby = on_standby
        self.standby = False
        self.busy = False
        self.priming = False
        self.priming_cycle = 0
        self.firmware_version = None
        self.flow_status = "unknown"

    def create_icon_image(self, connected: bool = False):
        icon_dir = os.path.join(os.path.dirname(__file__), "..", "icons")
        if connected:
            return Image.open(os.path.join(icon_dir, "connected.png"))
        return Image.open(os.path.join(icon_dir, "disconnected.png"))

    def create_menu(self):
        def open_releases(icon, item):
            webbrowser.open("https://github.com/tomups/watercooler-manager/releases/")

        return pystray.Menu(
            pystray.MenuItem('Disconnect' if self.connected else 'Connect',
                           self.on_disconnect if self.connected else self.on_connect,
                           enabled=lambda _: not self.busy),
            pystray.MenuItem('Resume' if self.standby else 'Standby', self.on_standby,
                            enabled=lambda _: self.connected and not self.busy and not self.priming),
            pystray.MenuItem(f'Flow: {self.flow_status}', None, enabled=False),
            pystray.MenuItem('Firmware: ' + (self.firmware_version or
                            ('unknown (unverified)' if self.connected else 'unknown')),
                            None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Mode', self.on_mode_settings(), enabled=lambda _: not self.priming and not self.busy and not self.standby),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Pump', self.on_pump_settings(), enabled=lambda _: not self.priming and not self.busy and not self.standby),
            pystray.MenuItem('Fan', self.on_fan_settings(), enabled=lambda _: not self.priming and not self.busy and not self.standby),
            pystray.MenuItem('RGB', self.on_rgb_settings(), enabled=lambda _: not self.priming and not self.busy and not self.standby),
            pystray.MenuItem('Water filling', pystray.Menu(
                pystray.MenuItem('Fill reservoir and attach hoses before starting', None, enabled=False),
                pystray.MenuItem('Start filling (~68 seconds)', self.on_priming,
                                enabled=lambda _: self.connected and not self.priming and not self.busy and not self.standby),
                pystray.MenuItem(f'Cancel filling (cycle {self.priming_cycle}/8)', self.on_cancel_priming,
                                enabled=lambda _: self.priming))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Settings', pystray.Menu(
                pystray.MenuItem(f"Version: {self.version}", None, enabled=False),
                pystray.MenuItem('Check for new versions', open_releases),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('Start on boot', self.on_autostart_settings, checked=lambda _: self.settings.auto_start),
                pystray.MenuItem('Auto-connect on startup', self.on_autoconnect_settings, checked=lambda _: self.settings.auto_connect),
            )),
            pystray.MenuItem('Exit', self.on_exit)
        )

    def setup(self):
        image = self.create_icon_image(connected=False)
        self.icon = pystray.Icon("WaterCooler", image, "Water Cooler Manager", self.create_menu())

    def run(self):
        if self.icon:
            self.icon.run()

    def stop(self):
        if self.icon:
            self.icon.stop()

    def update_connection_status(self, connected: bool):
        self.connected = connected
        if not connected:
            self.standby = False
        if self.icon:
            self.icon.icon = self.create_icon_image(connected=connected)
        self.refresh()

    def refresh(self):
        if self.icon:
            self.icon.menu = self.create_menu()
            self.icon.title = ("Water Cooler Manager - Standby" if self.standby else
                               f"Water Cooler Manager - Flow: {self.flow_status}")
            self.icon.update_menu()

    def update_device_status(self, firmware_version, flow_status):
        self.firmware_version = firmware_version
        self.flow_status = flow_status
        self.refresh()

    def update_priming_progress(self, cycle):
        self.priming_cycle = cycle
        self.refresh()

    def show_notification(self, message: str, title: str = "WaterCooler"):
        if self.icon:
            self.icon.notify(message, title)
