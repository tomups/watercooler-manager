
APP_VERSION = "v2.0.1"

import logging
import os
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw
from .theme import is_dark_theme

# GTK's legacy tray and the X11 fallback can be invisible or lack menus on
# Wayland. AppIndicator works with StatusNotifier hosts on Wayland and X11.
# An explicit override still allows GTK on older X11 desktops and dummy in CI.
if sys.platform == "linux":
    os.environ.setdefault("PYSTRAY_BACKEND", "appindicator")

import pystray

class SystemTrayIcon:
    def __init__(self, on_connect: Callable, on_disconnect: Callable, on_mode_settings: Callable,
                 on_pump_settings: Callable, on_fan_settings: Callable,
                 on_rgb_settings: Callable, on_autostart_settings: Callable, on_autoconnect_settings: Callable, on_exit: Callable, settings, version: str = APP_VERSION,
                 on_priming=None, on_cancel_priming=None, on_standby=None):
        self.icon = None
        self._dark_theme = False
        self._icon_lock = threading.Lock()
        self._theme_stop = threading.Event()
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
        # In a frozen app, Python packages can live only in the archive. Build
        # the resource path without traversing a nonexistent package directory.
        icon_dir = Path(__file__).resolve().parent.parent / "icons"
        filename = "connected.png" if connected else "disconnected.png"
        with Image.open(icon_dir / filename) as image:
            result = image.copy()
        if not connected:
            color = '#a0a0a0' if self._dark_theme else '#606060'
            width, height = result.size
            slash = [(round(width * .16), round(height * .91)),
                     (round(width * .84), round(height * .23))]
            alpha = result.getchannel('A')
            # A transparent gap around the slash keeps it legible over the
            # droplet on any panel background. Draw before resizing so its
            # edges retain the original icon's antialiasing.
            ImageDraw.Draw(alpha).line(slash, fill=0, width=round(width * .15))
            result = Image.new('RGBA', result.size, color)
            result.putalpha(alpha)
            ImageDraw.Draw(result).line(slash, fill=color, width=round(width * .075))
        if sys.platform == "linux":
            result = result.resize((64, 64), Image.Resampling.LANCZOS)
        return result

    def refresh_theme(self):
        dark = is_dark_theme()
        with self._icon_lock:
            if self._theme_stop.is_set() or dark == self._dark_theme:
                return
            self._dark_theme = dark
            if self.icon and not self.connected:
                self.icon.icon = self.create_icon_image(connected=False)

    def _watch_theme(self):
        while not self._theme_stop.wait(2):
            self.refresh_theme()

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
                pystray.MenuItem('Start on boot', self.on_autostart_settings,
                                checked=lambda _: self.settings.auto_start,
                                enabled=sys.platform in ('win32', 'linux')),
                pystray.MenuItem('Auto-connect on startup', self.on_autoconnect_settings, checked=lambda _: self.settings.auto_connect),
            )),
            pystray.MenuItem('Exit', self.on_exit)
        )

    def setup(self):
        if not pystray.Icon.HAS_MENU:
            raise RuntimeError("The selected tray backend has no menus. Install GTK and "
                               "AppIndicator support; see the Linux instructions in README.md.")
        self._dark_theme = is_dark_theme()
        image = self.create_icon_image(connected=False)
        self.icon = pystray.Icon("WaterCooler", image, "Water Cooler Manager", self.create_menu())

    def run(self):
        if self.icon:
            self._theme_stop.clear()
            watcher = threading.Thread(target=self._watch_theme, name='tray-theme', daemon=True)
            watcher.start()
            try:
                self.icon.run()
            finally:
                self._theme_stop.set()
                watcher.join(timeout=2)

    def stop(self):
        self._theme_stop.set()
        if self.icon:
            self.icon.stop()

    def update_connection_status(self, connected: bool):
        with self._icon_lock:
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
        logging.getLogger(__name__).info("%s: %s", title, message)
        if self.icon and self.icon.HAS_NOTIFICATION:
            self.icon.notify(message, title)
