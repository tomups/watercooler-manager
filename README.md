# Water Cooler Manager

Control compatible laptop water coolers over Bluetooth from your Windows system tray. Adjust cooling, choose RGB effects, and save your preferred settings without opening a separate control window.

![Water Cooler Manager system tray menu](https://github.com/user-attachments/assets/d9b69dd2-7aa6-4dce-97bc-4bb408dd60b8)

## Compatibility

Designed for coolers using the **LCT21001 (Mk1)** or **LCT22002 (Mk2)** controller, including compatible versions of:

- XMG OASIS Mk1 and Mk2
- PC Specialist Liquid Cooler 1.0 and 2.0
- Eluktronics Liquid Propulsion Package (LPP) G1 and G2
- TUXEDO Aquaris Gen5 and Gen6

Windows 11 is the tested platform. Other operating systems are unverified. Hardware verification covers LCT22002 firmware 2.0.0.4; behavior may vary with other controllers or firmware versions.

## Download and connect

1. Download **WaterCoolerManager.exe** from [GitHub Releases](https://github.com/tomups/watercooler-manager/releases/latest). The executable does not require a separate Python installation.
2. Enable Bluetooth on your computer. Prepare the cooler according to its manufacturer's instructions, then turn it on and wait for its blue pairing light to blink.
3. Run the executable. The app appears in the system tray, which may be inside the taskbar's hidden-icons menu.
4. Right-click the tray icon and choose **Connect**.

Your saved pump, fan, and lighting settings are applied when the cooler connects. Run only one copy of the app at a time.

## Controls

| Menu | What it does |
| --- | --- |
| **Mode** | Apply Low, Med, or High cooling presets, or turn the outputs off. |
| **Pump** | Select 7V, 8V, or 11V, or turn the pump off. |
| **Fan** | Select 25%, 50%, 75%, or 90% speed, or turn the fan off. |
| **RGB** | Choose a lighting mode and color, or turn the lights off. |
| **Standby / Resume** | Stop cooling and lighting while keeping Bluetooth connected, then restore your settings. |
| **Water filling** | Start or cancel a guided filling cycle with progress shown in the menu. Fill the reservoir and attach the hoses before starting. |
| **Settings** | Enable Windows startup and automatic connection on app startup, view the app version, or check for releases. |
| **Disconnect / Exit** | Disconnect the cooler, or close the app. Cooling stops on the tested Mk2 unit when it disconnects. |

Firmware and coolant-flow status are shown in the tray menu. Flow status reports whether the device detects normal flow; it is not a numeric flow-rate measurement.

All lighting controls are in **RGB**. Available modes are **Static**, **Breathe**, **Rainbow**, and **Breathe Rainbow**, plus **Spiral**, **Rotating Rainbow**, and **Fast Color Wave** on Mk2. The three additional Mk2 effects choose their own colors, so the Color submenu is disabled while they are selected.

## Troubleshooting

- **No window appeared:** look for the app in the system tray and right-click its icon.
- **Cooler not found:** check that Bluetooth is enabled, the cooler is powered on and in pairing mode, and another app is not already connected to it.
- **Firmware shows unknown:** the cooler did not provide a recognized firmware reply. Controls can still be used.
- **Flow shows starting or unknown:** allow a few seconds after starting the pump. Unknown is also expected when the pump is off or the device has not returned a reading.
- **Flow fault notification:** check the cooler, coolant level, and hose connections using the manufacturer's guidance.

For a persistent problem, [open an issue](https://github.com/tomups/watercooler-manager/issues) with your cooler model, firmware if available, Windows version, app version, and steps to reproduce it. Include any error output.

## Run from source

Install Git and [mise](https://mise.jdx.dev/getting-started.html), then run these commands in PowerShell:

```powershell
git clone https://github.com/tomups/watercooler-manager.git
cd watercooler-manager
mise trust
mise install
mise exec -- uv sync --locked
mise exec -- uv run --locked src/main.py
```

Mise installs the Python and uv versions pinned in `mise.toml`. uv installs dependencies into the project's `.venv`; manual environment activation is not required.

## Development

Run the tests from the repository directory:

```powershell
mise exec -- uv run --locked python -m unittest discover -s tests -v
```

Tests use simulated Bluetooth devices and temporary or mocked settings storage, so a physical cooler is not required.

Build the Windows executable:

```powershell
mise exec -- uv run --locked --group build pyinstaller --noconfirm --onefile --windowed --noconsole --icon "src/icons/connected.png" --add-data "src/icons;icons" --add-data "src/watercooler_manager;watercooler_manager" --name "WaterCoolerManager" src/main.py
```

The executable is written to `dist/WaterCoolerManager.exe`.

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`. Use `mise exec -- uv add <package>` to add a dependency, and commit both files. Include tests with behavior changes and describe any hardware validation in your pull request.

## Credits

- [TUXEDO Control Center](https://github.com/tuxedocomputers/tuxedo-control-center) for its open-source cooler control implementation.
- [Chocapikk's Uniwill BLE protocol notes](https://gist.github.com/Chocapikk/0baa8e68b87f8ed0873c39504184ebc6) for protocol research.
