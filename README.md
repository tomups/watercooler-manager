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
  - Color presets: Red, Green, Blue, White
- Auto-start on boot (Windows only)
- Auto-connect to the water cooler on startup
- Flow status (unknown / OK / fault), with fault notifications while the pump is running
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

## Diagnostics and maintenance

The tray menu displays firmware and flow status. A missing firmware reply leaves the
connection marked unverified, but controls remain available. Flow is **unknown**
until a valid meter response arrives, when the pump is off, or when a meter query
times out. The app accepts device pushes and also queries the meter periodically
(15 seconds after the previous query completes, with a 5-second response timeout).
Flow faults trigger a notification; the app does not change GPU settings or shut
down the computer. Reported flow is a device status, not a measured flow rate.

Use **RGB** to control the visible lighting. Tests on LCT22002 firmware 2.0.0.4
confirmed that `0x1E` controls the base lighting, while `0x33` activates effects
on those same lights: selector `1` breathes in one color, `2` smoothly cycles
colors, and `3` changes color between breaths. These are not independent zones.

For Mk2 updates, the app disables the active effect, sets the base color with
`0x1E`, and enables the requested animation with `0x33`. Static and OFF leave
`0x33` disabled so the base setting is visible. The same sequence is used when
restoring saved settings. Mk1 devices retain their `0x1E`-only lighting commands.

The experimental Fan RGB menu has been removed. Its old preferences are ignored
and removed when settings are saved; existing RGB color, effect, and off settings
are preserved.

For filling, attach the hoses and fill the reservoir first. Choose **Water filling →
Start filling**. The sequence takes about 68 seconds and shows the current cycle.
Normal controls are disabled during filling. **Cancel filling**, **Disconnect**, and
**Exit** cancel the cycle and attempt to stop filling and restore saved settings
before disconnecting. A lost Bluetooth link prevents restoration until reconnect;
errors are reported rather than silently discarded.

Disconnect and Exit continue to send the existing sleep command. It is now named
`write_sleep()` instead of `write_reset()`. The separate OEM `write_line_off()`
command is available at the device layer but is not used automatically pending
hardware validation. Undecoded telemetry and firmware-only configuration/storage
commands are not exposed.

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
filling completion/cancellation. Check Mk2 RGB changes and off after reconnect. Line-off
behavior remains unverified and must be tested before changing the disconnect policy.

Protocol reference: [Chocapikk's Uniwill BLE reverse-engineering notes](https://gist.github.com/Chocapikk/0baa8e68b87f8ed0873c39504184ebc6).

Live LCT22002 testing with firmware 2.0.0.4 showed two differences from the reference
examples: firmware replies use `MCU F/W Version: 2.0.0.4`, and meter notifications
use compact five-byte frames (for example, `FE 32 05 01 EF`). The parser accepts
these observed formats as well as the documented firmware prefix and padded
eight-byte meter frames. Regression tests include the captured responses.


## Thanks

Special thanks to [Tuxedo](https://tuxedocomputers.com/) for open sourcing their control center, where I could find the BT commands for the water coolers.

https://github.com/tuxedocomputers/tuxedo-control-center
