#!/usr/bin/env python3
"""
Watercooler Manager - System tray application for LCT water coolers

Note: On Linux, you may see a deprecation warning about libayatana-appindicator.
This is a harmless warning from the pystray library's use of the older API.
The application functions normally despite this warning.
"""

from watercooler_manager import WaterCoolerManager, __version__

def main():
    app = WaterCoolerManager(version=__version__)
    app.run()

if __name__ == "__main__":
    main()