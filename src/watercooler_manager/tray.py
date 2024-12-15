import pystray
from PIL import Image, ImageDraw
from typing import Callable

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

    def create_icon_image(self, connected: bool = False):
        image = Image.new('RGBA', (64, 64), color=(0,0,0,0))
        draw = ImageDraw.Draw(image)
        
        points = [
            (32, 10),  # Top point
            (54, 40),  # Bottom right
            (32, 54),  # Bottom middle
            (10, 40),  # Bottom left
        ]
        color = '#00a0ff' if connected else '#000080'
        draw.polygon(points, fill=color)
        return image

    def setup(self):
        image = self.create_icon_image(connected=False)
        
        menu = (
            pystray.MenuItem('Connect', self.on_connect),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Pump Settings', self.on_pump_settings),
            pystray.MenuItem('Fan Settings', self.on_fan_settings),
            pystray.MenuItem('RGB Settings', self.on_rgb_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Exit', self.on_exit)
        )

        self.icon = pystray.Icon("WaterCooler", image, "Water Cooler Manager", menu)

    def run(self):
        if self.icon:
            self.icon.run()

    def stop(self):
        if self.icon:
            self.icon.stop()

    def update_connection_status(self, connected: bool):
        if self.icon:
            self.icon.icon = self.create_icon_image(connected=connected)

    def show_notification(self, message: str, title: str = "WaterCooler"):
        if self.icon:
            self.icon.notify(message, title) 