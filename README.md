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
- Auto-start on boot (Windows only)
- Auto-connect to the water cooler on startup

## Installation

### Windows

1. Install Python 3.8 or higher
2. Clone the repository
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-windows.txt
   ```
4. Run the application:
   ```bash
   python src/main.py
   ```

### Linux

1. Install Python 3.8 or higher
2. Install system dependencies:
   
   **Arch/Manjaro/CachyOS:**
   ```bash
   sudo pacman -S python-gobject gtk3 libappindicator-gtk3
   ```
   
   **Ubuntu/Debian:**
   ```bash
   sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 libappindicator3-1
   ```
   
   **Fedora:**
   ```bash
   sudo dnf install python3-gobject gtk3 libappindicator-gtk3
   ```

3. Clone the repository
4. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-linux.txt
   ```
5. Run the application:
   ```bash
   python src/main.py
   ```

## Usage

Make sure your Bluetooth is ON.

Turn on the water cooler and wait until the blue light starts blinking.

The application runs in the system tray. Right click the tray icon to see the menu. 

Press `Connect` to connect to the water cooler.

### Platform Support

- **Windows**: Fully tested on Windows 11
- **Linux**: Tested on KDE Plasma (Wayland), GNOME, and XFCE
  - Arch Linux / CachyOS with KDE Plasma 6
  - Ubuntu 22.04+ with GNOME
  - Should work on most desktop environments with system tray support

## Known Issues

### Linux
- You may see a deprecation warning: `libayatana-appindicator-WARNING: libayatana-appindicator is deprecated`
  - This is a harmless warning from the underlying library and doesn't affect functionality
  - The application works normally despite this warning

### KDE Plasma
- On some KDE configurations, the system tray icon might be hidden by default
  - Click the arrow in the system tray to show hidden icons
  - Right-click the system tray and check settings to unhide the application

## Thanks

Special thanks to [Tuxedo](https://tuxedocomputers.com/) for open sourcing their control center, where I could find the BT commands for the water coolers.

https://github.com/tuxedocomputers/tuxedo-control-center
