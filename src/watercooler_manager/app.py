import asyncio
import threading
from contextlib import suppress

import pystray
from .device import WaterCoolingDevice
from .settings import Settings
from .tray import SystemTrayIcon
from .enums import PumpVoltage, RGBState


class WaterCoolerManager:
    def __init__(self, version=None):
        self.settings = Settings()
        self.loop = asyncio.new_event_loop()
        self._operation_lock = asyncio.Lock()
        self._priming_task = None
        self._closing = False
        self._disconnecting = False
        self._disconnect_done = asyncio.Event()
        self._disconnect_done.set()
        self._fault_reported = False
        self.device = WaterCoolingDevice(self._device_status, self._device_disconnected)
        self.tray = SystemTrayIcon(
            on_connect=self.connect_menu,
            on_disconnect=self.disconnect_menu,
            on_mode_settings=self.handle_on_mode_settings,
            on_pump_settings=self.handle_pump_settings,
            on_fan_settings=self.handle_fan_settings,
            on_rgb_settings=self.handle_rgb_settings,
            on_autostart_settings=self.handle_autostart_settings,
            on_autoconnect_settings=self.handle_autoconnect_settings,
            on_exit=self.exit_app,
            settings=self.settings,
            version=version if version is not None else "v1.0.0",
            on_fan_rgb_settings=lambda: self.handle_rgb_settings(fan=True),
            on_priming=lambda: self._submit(self.start_priming()),
            on_cancel_priming=lambda: self._submit(self.cancel_priming()),
        )

    def _submit(self, coroutine):
        async def report_errors():
            try:
                await coroutine
            except asyncio.CancelledError:
                pass
            except Exception as error:
                self.tray.show_notification(f"Error: {error}")
        return asyncio.run_coroutine_threadsafe(report_errors(), self.loop)

    def run(self):
        def run_event_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        threading.Thread(target=run_event_loop, daemon=True).start()
        self.tray.setup()
        if self.settings.auto_connect:
            self.connect_menu()
        self.tray.run()

    def exit_app(self):
        if self._closing:
            return
        self._closing = True
        # Keep the event loop alive until priming cleanup and disconnect finish.
        self._submit(self._exit())

    async def _exit(self):
        try:
            await self.disconnect()
        finally:
            self.settings.save()
            self.tray.stop()
            self.loop.call_soon(self.loop.stop)

    def connect_menu(self):
        self._submit(self.connect_and_run())

    def disconnect_menu(self):
        self._submit(self.disconnect())

    async def disconnect(self):
        if self._disconnecting:
            await self._disconnect_done.wait()
            return
        self._disconnecting = True
        self._disconnect_done.clear()
        try:
            await self.cancel_priming()
            async with self._operation_lock:
                try:
                    await self.device.disconnect()
                finally:
                    self.tray.update_connection_status(False)
        finally:
            self._disconnecting = False
            self._disconnect_done.set()

    def _device_status(self):
        self.tray.update_device_status(self.device.firmware_version,
                                     self.device.flow_status, self.device.supports_fan_rgb)
        if self.device.flow_status == "OK" or not self.device.pump_running:
            self._fault_reported = False
        if (self.device.flow_status == "fault" and not self._fault_reported
                and not self.tray.priming):
            self._fault_reported = True
            self.tray.show_notification("Coolant flow fault detected. Check the cooler and hoses.")

    def _device_disconnected(self):
        if (self._priming_task and not self._priming_task.done()
                and not self._priming_task.cancelling()):
            self._priming_task.cancel()
        self.tray.update_connection_status(False)
        self.tray.show_notification("Water cooler disconnected")

    async def connect_and_run(self):
        async with self._operation_lock:
            if self._closing or self._disconnecting or await self.device.is_connected():
                return
            await self.cancel_priming()
            self.tray.busy = True
            self.tray.refresh()
            try:
                self.tray.show_notification("Scanning for CoolingSystem device...")
                devices = await self.device.get_device_list()
                if not devices:
                    self.tray.show_notification("CoolingSystem device not found")
                    return
                target = devices[0]
                await self.device.connect(target.uuid)
                await self.apply_current_settings()
                self.tray.update_connection_status(True)
                self.device.start_monitoring()
                message = f"Connected to {target.name}"
                if not self.device.firmware_version:
                    message += "; firmware reply unavailable (connection unverified)"
                self.tray.show_notification(message)
            except BaseException:
                await self.device.disconnect()
                self.tray.update_connection_status(False)
                raise
            finally:
                self.tray.busy = False
                self.tray.refresh()

    async def apply_current_settings(self):
        # Attempt every output even if another write fails during restoration.
        operations = [
            self.device.write_pump_off if self.settings.pump_is_off else
                lambda: self.device.write_pump_mode(pump_voltage=self.settings.current_voltage),
            self.device.write_fan_off if self.settings.fan_is_off else
                lambda: self.device.write_fan_mode(self.settings.current_fan_speed),
            lambda: self._apply_rgb(False),
        ]
        if self.device.supports_fan_rgb and self.settings.fan_rgb_enabled:
            operations.append(lambda: self._apply_rgb(True))
        errors = []
        for operation in operations:
            try:
                await operation()
            except Exception as error:
                errors.append(error)
        if errors:
            raise RuntimeError(f"Could not restore all settings: {errors[0]}")

    async def _apply_rgb(self, fan):
        prefix = "fan_rgb" if fan else "rgb"
        if getattr(self.settings, prefix + "_is_off"):
            await self.device.write_rgb_off(fan=fan)
        else:
            await self.device.write_rgb(*getattr(self.settings, prefix + "_color"),
                                        getattr(self.settings, prefix + "_state"), fan=fan)

    def _change_settings(self, **changes):
        async def apply():
            async with self._operation_lock:
                if self._closing or self._disconnecting or self.tray.priming:
                    return
                for name, value in changes.items():
                    setattr(self.settings, name, value)
                self.settings.save()
                self.tray.refresh()
                if await self.device.is_connected():
                    await self.apply_current_settings()
        self._submit(apply())

    async def start_priming(self):
        async with self._operation_lock:
            if (self._closing or self._disconnecting or self.tray.priming
                    or not await self.device.is_connected()):
                return
            self.tray.priming = True
            self.tray.refresh()
            self._priming_task = asyncio.create_task(self._run_priming())

    async def _run_priming(self):
        try:
            await self.device.prime(self.apply_current_settings, self.tray.update_priming_progress)
            self.tray.show_notification("Water filling complete; saved settings restored")
        except asyncio.CancelledError:
            self.tray.show_notification("Water filling cancelled")
        except Exception as error:
            self.tray.show_notification(f"Water filling failed: {error}")
        finally:
            self.tray.priming = False
            self.tray.refresh()
            self._device_status()

    async def cancel_priming(self):
        task = self._priming_task
        if task and not task.done():
            # A second cancellation must not interrupt the restoration in finally.
            if not task.cancelling():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            self.tray.priming = False
            self.tray.refresh()

    def handle_on_mode_settings(self):
        def preset(voltage, speed, color):
            return lambda: self._change_settings(current_voltage=voltage, current_fan_speed=speed,
                pump_is_off=False, fan_is_off=False, rgb_is_off=False, rgb_color=color)
        def selected(voltage, speed, color):
            return lambda _: (not self.settings.pump_is_off and not self.settings.fan_is_off
                and not self.settings.rgb_is_off and self.settings.current_voltage == voltage
                and self.settings.current_fan_speed == speed and self.settings.rgb_color == color)
        return pystray.Menu(
            pystray.MenuItem('Turn on Low Mode', preset(PumpVoltage.V7, 25, (0, 255, 0)),
                             checked=selected(PumpVoltage.V7, 25, (0, 255, 0))),
            pystray.MenuItem('Turn on Med Mode', preset(PumpVoltage.V8, 50, (0, 0, 255)),
                             checked=selected(PumpVoltage.V8, 50, (0, 0, 255))),
            pystray.MenuItem('Turn on High Mode', preset(PumpVoltage.V11, 90, (255, 0, 0)),
                             checked=selected(PumpVoltage.V11, 90, (255, 0, 0))),
            pystray.MenuItem('Turn off Mode', lambda: self._change_settings(
                pump_is_off=True, fan_is_off=True, rgb_is_off=True, fan_rgb_is_off=True),
                checked=lambda _: self.settings.pump_is_off and self.settings.fan_is_off
                    and self.settings.rgb_is_off and (not self.settings.fan_rgb_enabled
                    or self.settings.fan_rgb_is_off)))

    def handle_pump_settings(self):
        def voltage_item(label, voltage):
            return pystray.MenuItem(label, lambda: self._change_settings(
                current_voltage=voltage, pump_is_off=False),
                checked=lambda _: not self.settings.pump_is_off
                    and self.settings.current_voltage == voltage)
        return pystray.Menu(
            pystray.MenuItem('Turn Off', lambda: self._change_settings(
                pump_is_off=not self.settings.pump_is_off), checked=lambda _: self.settings.pump_is_off),
            pystray.MenuItem('Voltage', pystray.Menu(
                voltage_item('7V', PumpVoltage.V7), voltage_item('8V', PumpVoltage.V8),
                voltage_item('11V', PumpVoltage.V11))))

    def handle_fan_settings(self):
        def speed_item(speed):
            return pystray.MenuItem(f'{speed}%', lambda: self._change_settings(
                current_fan_speed=speed, fan_is_off=False),
                checked=lambda _: not self.settings.fan_is_off and self.settings.current_fan_speed == speed)
        return pystray.Menu(
            pystray.MenuItem('Turn Off', lambda: self._change_settings(
                fan_is_off=not self.settings.fan_is_off), checked=lambda _: self.settings.fan_is_off),
            pystray.MenuItem('Speed', pystray.Menu(*(speed_item(s) for s in (25, 50, 75, 90)))))

    def handle_rgb_settings(self, fan=False):
        prefix = 'fan_rgb' if fan else 'rgb'
        def get(field):
            return getattr(self.settings, prefix + '_' + field)
        def change(**values):
            self._change_settings(**{prefix + '_' + key: value for key, value in values.items()})
        def mode_item(label, mode):
            return pystray.MenuItem(label, lambda: change(state=mode, is_off=False),
                checked=lambda _: not get('is_off') and get('state') == mode)
        def color_item(label, color):
            return pystray.MenuItem(label, lambda: change(color=color, is_off=False),
                checked=lambda _: not get('is_off') and get('color') == color)
        items = []
        if fan:
            items.append(pystray.MenuItem('Enable fan lighting control (experimental)',
                lambda: change(enabled=not get('enabled')), checked=lambda _: get('enabled')))
        items.extend([
            pystray.MenuItem('Turn Off', lambda: change(is_off=not get('is_off')),
                            checked=lambda _: get('is_off'),
                            enabled=lambda _: not fan or get('enabled')),
            pystray.MenuItem('Mode', pystray.Menu(
                mode_item('Static', RGBState.STATIC), mode_item('Breathe', RGBState.BREATHE),
                mode_item('Rainbow', RGBState.COLORFUL), mode_item('Breathe Rainbow', RGBState.BREATHE_COLOR)),
                enabled=lambda _: not fan or get('enabled')),
            pystray.MenuItem('Color', pystray.Menu(
                color_item('Red', (255, 0, 0)), color_item('Green', (0, 255, 0)),
                color_item('Blue', (0, 0, 255)), color_item('White', (255, 255, 255))),
                enabled=lambda _: not fan or get('enabled'))])
        return pystray.Menu(*items)

    def handle_autostart_settings(self):
        self.settings.set_autostart(not self.settings.auto_start)

    def handle_autoconnect_settings(self):
        self.settings.auto_connect = not self.settings.auto_connect
        self.settings.save()
