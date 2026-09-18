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
- Separate, opt-in fan lighting controls for LCT22002 (Mk2)
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

On Mk2 devices, open **Fan RGB (Mk2)** and enable experimental fan lighting control.
Its color, mode, and off state are saved independently from **Head RGB**. This uses
the OEM host's mode encoding; behavior may differ across firmware versions.
Disabling control stops sending fan lighting commands and leaves the current
lighting in place. Mk1 devices never receive these commands.

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

Use Python 3.11 or newer and install `requirements.txt`. On Windows, run:

```powershell
python -m unittest discover -s tests -v
```

Tests mock Bluetooth and settings storage; they do not connect to a cooler or
modify the user's preferences. They cover framing, handshake fallback, flow
status, command limits, saved-state restoration, Mk2 gating, and filling cleanup.

Before releasing, check on both cooler models: firmware reporting, flow status
with the pump on/off, connection loss and reconnect, all saved off states, and
filling completion/cancellation. Check Mk2 fan lighting modes separately. Line-off
behavior remains unverified and must be tested before changing the disconnect policy.

Protocol reference: [Chocapikk's Uniwill BLE reverse-engineering notes](https://gist.github.com/Chocapikk/0baa8e68b87f8ed0873c39504184ebc6).


## Thanks

Special thanks to [Tuxedo](https://tuxedocomputers.com/) for open sourcing their control center, where I could find the BT commands for the water coolers.

https://github.com/tuxedocomputers/tuxedo-control-center
