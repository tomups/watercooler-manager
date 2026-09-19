# Water Cooler Manager

A system tray utility to manage LCT21001 / LCT22002 laptop water coolers (typically for Tongfang laptops).

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
  - Additional Mk2 effects: Spiral, Rotating Rainbow, Fast Color Wave
  - Color presets: Red, Green, Blue, White
- Auto-start on boot (Windows only)
- Auto-connect to the water cooler on startup
- Flow status (unknown / starting / OK / fault), with a pump-start grace period
- Standby without disconnecting, and Resume using saved settings
- Firmware version diagnostics and explicit feedback when the firmware query times out
- Restore saved pump, fan, and lighting on/off states when connecting
- One RGB control for static colors and Mk2 lighting effects
- Cancellable water filling sequence, with progress and restoration of saved settings

## Usage

Make sure your Bluetooth is ON.

Turn on the water cooler and wait until the blue light starts blinking.

The application runs in the system tray. Right click the tray icon to see the menu. 

Press `Connect` to connect to the water cooler.

Only tested on Windows 11, but might work with Linux too.

## Development and verification

This project uses **mise for Python and uv management**, and **uv for dependencies
and the project virtual environment**. Python 3.14.7 and uv are pinned in
`mise.toml`; `.python-version` also tells uv which Python to select. Python downloads
through uv are disabled so that mise remains responsible for the interpreter.

From PowerShell in the repository directory, set up the project:

```powershell
mise trust
mise install
mise exec -- uv sync --locked
```

Start the app (it appears in the system tray):

```powershell
mise exec -- uv run src/main.py
```

If mise is already activated in your shell, `uv run src/main.py` is sufficient.
No manual environment activation is needed. uv creates and maintains `.venv`;
the old `.test-venv` is no longer used. Exit any other copy before local testing.

Run the tests:

```powershell
mise exec -- uv run --locked python -m unittest discover -s tests -v
```

Dependencies live in `pyproject.toml` and exact resolved versions in `uv.lock`.
Use `mise exec -- uv add <package>` to add a dependency. When upgrading Python,
update both `mise.toml` and `.python-version`, then run `mise install` and `uv sync`.

Build the Windows executable using the optional build dependency group:

```powershell
mise exec -- uv run --locked --group build pyinstaller --noconfirm --onefile --windowed --noconsole --icon "src/icons/connected.png" --add-data "src/icons;icons" --add-data "src/watercooler_manager;watercooler_manager" --name "WaterCoolerManager" src/main.py
```

Both CI workflows use mise and the same uv lockfile.

Tests mock Bluetooth and settings storage; they do not connect to a cooler or
modify the user's preferences. They cover framing, handshake fallback, flow
status, command limits, saved-state restoration, Mk2 gating, and filling cleanup.

Before releasing, check on both cooler models: firmware reporting, flow status
with the pump on/off, connection loss and reconnect, all saved off states, and
filling completion/cancellation. Check Mk2 RGB changes and off after reconnect,
Standby/Resume, and output shutdown on Disconnect. Plain disconnect and line-off
were both observed to stop outputs and return to pairing on LCT22002 2.0.0.4;
sleep stopped outputs while retaining the connection. Other firmware needs its
own validation before extending the plain-disconnect policy.

Protocol reference: [Chocapikk's Uniwill BLE reverse-engineering notes](https://gist.github.com/Chocapikk/0baa8e68b87f8ed0873c39504184ebc6).

Live LCT22002 testing with firmware 2.0.0.4 showed two differences from the reference
examples: firmware replies use `MCU F/W Version: 2.0.0.4`, and meter notifications
use compact five-byte frames (for example, `FE 32 05 01 EF`). The parser accepts
these observed formats as well as the documented firmware prefix and padded
eight-byte meter frames. Regression tests include the captured responses.


## Thanks

Special thanks to [Tuxedo](https://tuxedocomputers.com/) for open sourcing their control center, where I could find the BT commands for the water coolers.

https://github.com/tuxedocomputers/tuxedo-control-center
