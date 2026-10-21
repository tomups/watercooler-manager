#!/usr/bin/env python3
"""Utility to manage LCT21001 / LCT22002 laptop water coolers"""

import argparse
import logging
import os
import sys


def prepare_system_helpers():
    """Let host executables use their own libraries after GUI imports finish."""
    if sys.platform != 'linux' or not getattr(sys, 'frozen', False):
        return
    # PyInstaller's loader keeps its original search path for this process.
    # Reset the inherited environment for Bleak's bluetoothctl and xdg-open;
    # this application has no bundled helper executables to launch.
    original = os.environ.get('LD_LIBRARY_PATH_ORIG')
    if original:
        os.environ['LD_LIBRARY_PATH'] = original
    else:
        os.environ.pop('LD_LIBRARY_PATH', None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        # Parse --help before importing the GUI, including on headless machines.
        from watercooler_manager import WaterCoolerManager, __version__

        prepare_system_helpers()
        app = WaterCoolerManager(version=__version__)
        app.run()
    except (ImportError, RuntimeError) as error:
        hint = (" On Linux, use the distro Python with GTK/AppIndicator packages "
                "and run inside your desktop session. See README.md."
                if sys.platform == "linux" else "")
        parser.exit(1, f"Watercooler Manager could not start: {error}.{hint}\n")

if __name__ == "__main__":
    main()
