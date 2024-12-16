# Water Cooler Manager

A system tray utility to manage LCT21001 / LCT21002 laptop water coolers (typically for Tongfang laptops).

![Captura de pantalla 2024-12-16 014051](https://github.com/user-attachments/assets/d9b69dd2-7aa6-4dce-97bc-4bb408dd60b8)

Should work with:

- XMG Oasis mk1 and mk2
- PC Specialist Liquid Cooler 1.0 and 2.0
- Eluktronics Liquid Propulsion Package (LPP) G1 and G2
- TUXEDO Aquaris Gen5 and Gen6

## Features

- System tray interface with connection status indicator
- Control pump voltage (7V, 8V, 11V)
- Adjust fan speed (25%, 50%, 75%, 90%) 
- RGB lighting controls:
  - On/Off toggle
  - Multiple modes: Static, Breathe, Rainbow, Breathe Rainbow
  - Color presets: Red, Green, Blue, White
- Settings persist between sessions

## Usage

Make sure your Bluetooth is ON.

Turn on the water cooler and wait until the blue light starts blinking.

The application runs in the system tray. Right click the tray icon to see the menu. 

Press `Connect` to connect to the water cooler.

Only tested on Windows 11, but might work with Linux too.


## Thanks

Special thanks to [Tuxedo](https://tuxedocomputers.com/) for open sourcing their control center, where I could find the BT commands for the water coolers.

https://github.com/tuxedocomputers/tuxedo-control-center
