import pystray
from PIL import Image
from typing import Callable
import os

class SystemTrayIcon:
    def __init__(self, on_connect: Callable, on_disconnect: Callable, 
                 on_pump_settings: Callable, on_fan_settings: Callable,
                 on_rgb_settings: Callable, on_exit: Callable):
        self.icon = None
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_pump_settings = on_pump_settings
        self.on_fan_settings = on_fan_settings
        self.on_rgb_settings = on_rgb_settings
        self.on_exit = on_exit
        self.connected = False

    def create_icon_image(self, connected: bool = False):        
        icon_dir = os.path.join(os.path.dirname(__file__), "..", "icons")
        if connected:
            return Image.open(os.path.join(icon_dir, "connected.png"))
        return Image.open(os.path.join(icon_dir, "disconnected.png"))

    def create_menu(self):
        return (
            pystray.MenuItem('Disconnect' if self.connected else 'Connect', 
                           self.on_disconnect if self.connected else self.on_connect),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Pump', self.on_pump_settings()),
            pystray.MenuItem('Fan', self.on_fan_settings()),
            pystray.MenuItem('RGB', self.on_rgb_settings()),
            pystray.Menu.SEPARATOR,
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