#!/usr/bin/env python3


from watercooler_manager import WaterCoolerManager, __version__

def main():
    app = WaterCoolerManager(version=__version__)
    app.run()

if __name__ == "__main__":
    main()