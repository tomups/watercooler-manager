#!/usr/bin/env python3
"""Utility to manage LCT21001 / LCT22002 laptop water coolers"""

import argparse
import logging
import sys

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        # Parse --help before importing the GUI, including on headless machines.
        from watercooler_manager import WaterCoolerManager, __version__

        app = WaterCoolerManager(version=__version__)
        app.run()
    except (ImportError, RuntimeError) as error:
        hint = (" On Linux, use the distro Python with GTK/AppIndicator packages "
                "and run inside your desktop session. See README.md."
                if sys.platform == "linux" else "")
        parser.exit(1, f"Watercooler Manager could not start: {error}.{hint}\n")

if __name__ == "__main__":
    main()
