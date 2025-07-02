
APP_VERSION = "v1.2.0"

import pystray
from PIL import Image
from typing import Callable
import os
import webbrowser

class SystemTrayIcon:
    def __init__(self, on_connect: Callable, on_disconnect: Callable, 
                 on_pump_settings: Callable, on_fan_settings: Callable,
                 on_rgb_settings: Callable, on_autostart_settings: Callable, on_autoconnect_settings: Callable, on_exit: Callable, settings, version: str = APP_VERSION):
        self.icon = None
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_pump_settings = on_pump_settings
        self.on_fan_settings = on_fan_settings
        self.on_rgb_settings = on_rgb_settings
        self.on_autostart_settings = on_autostart_settings
        self.on_autoconnect_settings = on_autoconnect_settings
        self.on_exit = on_exit
        self.connected = False
        self.settings = settings
        self.version = version

    def create_icon_image(self, connected: bool = False):        
        icon_dir = os.path.join(os.path.dirname(__file__), "..", "icons")
        if connected:
            return Image.open(os.path.join(icon_dir, "connected.png"))
        return Image.open(os.path.join(icon_dir, "disconnected.png"))

    def create_menu(self):        
        def open_releases(icon, item):
            webbrowser.open("https://github.com/tomups/watercooler-manager/releases/")

        return (
            pystray.MenuItem('Disconnect' if self.connected else 'Connect', 
                           self.on_disconnect if self.connected else self.on_connect),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Pump', self.on_pump_settings()),
            pystray.MenuItem('Fan', self.on_fan_settings()),
            pystray.MenuItem('RGB', self.on_rgb_settings()),
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
        if self.icon:
            self.connected = connected
            self.icon.icon = self.create_icon_image(connected=connected)
            self.icon.menu = self.create_menu()

    def show_notification(self, message: str, title: str = "WaterCooler"):
        if self.icon:
            self.icon.notify(message, title)