# Water Cooler Manager

Utility to manage LCT21001 / LCT22002 laptop water coolers

Control compatible laptop water coolers from your Windows or Linux system tray without having to use the original control panel software. 

![Water Cooler Manager system tray menu](https://github.com/user-attachments/assets/d9b69dd2-7aa6-4dce-97bc-4bb408dd60b8)
![Water Cooler Manager windows system tray menu](https://github.com/user-attachments/assets/606967b7-d3c1-4f1e-9d31-80ed5aebcd39
)

## Compatibility

Designed for coolers using the **LCT21001 (Mk1)** or **LCT22002 (Mk2)** controller, including compatible versions of:

- XMG OASIS Mk1 and Mk2
- PC Specialist Liquid Cooler 1.0 and 2.0
- Eluktronics Liquid Propulsion Package (LPP) G1 and G2
- TUXEDO Aquaris Gen5 and Gen6

## Installation and usage

1. Download the latest release for your platform from [GitHub Releases](https://github.com/tomups/watercooler-manager/releases/latest).
2. Enable Bluetooth on your computer. Prepare the cooler according to its manufacturer's instructions, then turn it on and wait for its blue pairing light to blink.
3. Run the executable. The app appears in the system tray, which may be inside the taskbar's hidden-icons menu.
4. Right-click the tray icon and choose **Connect**.

## Controls

| Menu | What it does |
| --- | --- |
| **Mode** | Apply Low, Med, or High cooling presets, or turn the outputs off. Presets keep RGB off if it was already off. |
| **Pump** | Select 7V, 8V, or 11V, or turn the pump off. |
| **Fan** | Select 25%, 50%, 75%, or 90% speed, or turn the fan off. |
| **RGB** | Choose a lighting mode and color, or turn the lights off. |
| **Standby / Resume** | Stop cooling and lighting while keeping Bluetooth connected, then restore your settings. |
| **Water filling** | Start or cancel a guided filling cycle with progress shown in the menu. Fill the reservoir and attach the hoses before starting. |
| **Settings** | Enable Windows/Linux startup and automatic connection on app startup, view the app version, or check for releases. |
| **Disconnect / Exit** | Disconnect the cooler, or close the app. Cooling stops on the tested Mk2 unit when it disconnects. |

## Troubleshooting

- **No window appeared:** look for the app in the system tray and right-click its icon.
- **Cooler not found:** check that Bluetooth is enabled, the cooler is powered on and in pairing mode, and another app is not already connected to it.
- **Firmware shows unknown:** the cooler did not provide a recognized firmware reply. Controls can still be used.
- **Flow shows starting or unknown:** allow a few seconds after starting the pump. Unknown is also expected when the pump is off or the device has not returned a reading.
- **Flow fault notification:** check the cooler, coolant level, and hose connections using the manufacturer's guidance.

For a persistent problem, [open an issue](https://github.com/tomups/watercooler-manager/issues) with your cooler model, firmware if available, operating system and desktop environment, app version, and steps to reproduce it. Include any error output.

## Run from source

Python 3.11–3.14 is supported. Python 3.10 lacks the task cancellation API used by the cooler controls.

### Windows

Install Git and [mise](https://mise.jdx.dev/getting-started.html), then run these commands in PowerShell:

```powershell
git clone https://github.com/tomups/watercooler-manager.git
cd watercooler-manager
mise trust
mise install
mise exec -- uv sync --locked
mise exec -- uv run --locked src/main.py
```

### Linux

Install Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), and the runtime packages for your distribution. These commands use distro-provided GTK bindings so you do not need to compile PyGObject or Cairo with pip.

**Arch / Manjaro / CachyOS / Omarchy:**

```bash
sudo pacman -S --needed python python-gobject python-cairo gtk3 libayatana-appindicator bluez bluez-utils
```

**Ubuntu 24.04+ / Debian 12+:**

```bash
sudo apt install python3-venv python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 bluez
```

**Fedora (with Python 3.11–3.14):**

```bash
sudo dnf install python3 python3-gobject python3-cairo gtk3 libayatana-appindicator-gtk3 bluez
```

Then create the environment with the **distribution's Python**, giving it access to the GTK bindings installed above:

```bash
git clone https://github.com/tomups/watercooler-manager.git
cd watercooler-manager
uv venv --python /usr/bin/python3 --system-site-packages
uv sync --locked --python /usr/bin/python3
.venv/bin/python src/main.py
```

The explicit Python path overrides the Windows development toolchain pin. Keep using `.venv/bin/python` when running the app or tests on Linux. Recreate the environment after a distro update changes Python's minor version. A regular isolated venv, or a mise/pyenv Python, will not see the distro's `gi` extension.

Run `./quick-test.sh` to check the Python backend, session tray host, and powered Bluetooth adapter. Enable your distribution's Bluetooth service and Bluetooth radio if the adapter check fails. Run the app as your normal desktop user, without `sudo`.

Desktop requirements:

- **KDE Plasma:** enable the System Tray widget and check hidden icons.
- **GNOME:** install and enable [AppIndicator and KStatusNotifierItem Support](https://extensions.gnome.org/extension/615/appindicator-support/). GNOME does not provide this tray support by default.
- **Mango / Sway / Hyprland and other Wayland compositors:** use a panel or shell with StatusNotifier support, such as a tray-enabled Waybar or Quickshell panel.
- **XFCE and other X11 desktops:** enable a StatusNotifier/AppIndicator tray plugin. If the desktop only supports GTK's legacy tray, try `PYSTRAY_BACKEND=gtk .venv/bin/python src/main.py`. The `xorg` backend lacks the menus this app requires.

## Development

Run the tests from the repository directory. On Linux, use the headless backend for unit tests:

```bash
PYSTRAY_BACKEND=dummy .venv/bin/python -m unittest discover -s tests -v
```

On Windows:

```powershell
mise exec -- uv run --locked python -m unittest discover -s tests -v
```

Tests use simulated Bluetooth devices and temporary or mocked settings storage, so a physical cooler is not required.

On Linux, exercise the real tray in your desktop session:

```bash
.venv/bin/python tests/smoke_linux_tray.py
```

This test creates a temporary tray icon and clicks simulated Connect/Disconnect and Exit actions over D-Bus. It verifies native menus, icon updates, and file cleanup without accessing Bluetooth or your settings.

With `desktop-file-validate` installed (the `desktop-file-utils` package), check XDG autostart launch commands without changing your login configuration:

```bash
PYSTRAY_BACKEND=dummy .venv/bin/python tests/smoke_linux_autostart.py
# After building, also check the packaged launch command:
PYSTRAY_BACKEND=dummy .venv/bin/python tests/smoke_linux_autostart.py --executable dist/WaterCoolerManager
```

Build the native executable with the same helper used in CI:

```bash
# Linux: keep the system-site-packages environment created above.
uv sync --locked --group build --python /usr/bin/python3
.venv/bin/python scripts/build.py
dist/WaterCoolerManager --help
```

```powershell
# Windows
mise exec -- uv sync --locked --group build
.venv\Scripts\python scripts/build.py
```

The release workflow also checks frozen Linux startup against a virtual tray host in an isolated D-Bus session.

The development executable is written to `dist/WaterCoolerManager` on Linux or `dist/WaterCoolerManager.exe` on Windows. Linux builds include GTK/AppIndicator bindings but still depend on a compatible distribution, system services, and tray host. A build from a rolling distribution may not run on older glibc versions. 

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`. Use `mise exec -- uv add <package>` to add a dependency, and commit both files. Include tests with behavior changes and describe any hardware validation in your pull request.

## Thanks

- [TUXEDO Control Center](https://github.com/tuxedocomputers/tuxedo-control-center) for its open-source cooler control implementation.
- [Chocapikk's Uniwill BLE protocol notes](https://gist.github.com/Chocapikk/0baa8e68b87f8ed0873c39504184ebc6) for protocol research.
