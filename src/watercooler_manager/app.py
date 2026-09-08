import asyncio
import threading
from .device import WaterCoolingDevice
from .settings import Settings
from .tray import SystemTrayIcon
from .enums import PumpVoltage, RGBState
from .temperature import LibreHardwareTemperatureMonitor, calculate_fan_speed
import pystray

class WaterCoolerManager:
    def __init__(self, version=None):
        self.settings = Settings()
        self.device = WaterCoolingDevice()
        self.temperature_monitor = LibreHardwareTemperatureMonitor()
        self.automatic_fan_task = None
        self._watchdog_task = None
        self._connect_lock = asyncio.Lock()
        self.loop = asyncio.new_event_loop()
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
            version=version if version is not None else "v1.0.0"
        )

    async def _connection_watchdog_loop(self):
        try:
            while True:
                if self.settings.auto_connect:
                    try:
                        if not await self.device.is_connected():
                            async with self._connect_lock:
                                if not await self.device.is_connected():
                                    await self.connect_and_run()
                    except Exception:
                        pass
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise

    def run(self):
        # Setup and start the event loop in a separate thread
        def run_event_loop():
            asyncio.set_event_loop(self.loop)
            self._watchdog_task = self.loop.create_task(self._connection_watchdog_loop())
            self.loop.run_forever()
        loop_thread = threading.Thread(target=run_event_loop, daemon=True)
        loop_thread.start()

        # Setup and run the system tray
        self.tray.setup()
        self.tray.run()

    def exit_app(self):
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop)
        try:
            future.result(3)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.settings.save()
        self.tray.stop()

    async def _shutdown(self):
        self._stop_automatic_fan_control()
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
        await self.device.disconnect()
        await asyncio.to_thread(self.temperature_monitor.close)

    def connect_menu(self):
        asyncio.run_coroutine_threadsafe(self._safe_connect(), self.loop)

    async def _safe_connect(self):
        async with self._connect_lock:
            if not await self.device.is_connected():
                await self.connect_and_run()

    def disconnect_menu(self):
        asyncio.run_coroutine_threadsafe(self._safe_disconnect(), self.loop)

    async def _safe_disconnect(self):
        async with self._connect_lock:
            await self.device.disconnect()
        self.tray.update_connection_status(False)

    async def _execute_command(self, command_coro_factory):
        if not await self.device.is_connected():
            if self.settings.auto_connect:
                async with self._connect_lock:
                    if not await self.device.is_connected():
                        await self.connect_and_run()
            else:
                self.tray.show_notification("Device not connected")
                return
        if await self.device.is_connected():
            await command_coro_factory()
        else:
            self.tray.show_notification("Device not connected")

    async def connect_and_run(self):
        self.tray.show_notification("Scanning for CoolingSystem device...")
        devices = await self.device.get_device_list()
        
        if not devices:
            self.tray.show_notification("CoolingSystem device not found")
            return

        target_device = devices[0]
        self.tray.show_notification(f"Found device at {target_device.uuid}")
        
        try:
            await self.device.connect(target_device.uuid)
            self.tray.show_notification(f"Successfully connected to {target_device.name}")
            self.tray.update_connection_status(True)
            
            # Apply current settings
            await self.apply_current_settings()
            
        except Exception as e:
            self.tray.show_notification(f"Error occurred: {str(e)}")
            if await self.device.is_connected():
                await self.device.disconnect()
            self.tray.update_connection_status(False)

    async def apply_current_settings(self):
        if self.settings.pump_is_off:
            await self.device.write_pump_off()
        else:
            await self.device.write_pump_mode(pump_voltage=self.settings.current_voltage)
        if self.settings.fan_is_off:
            await self.device.write_fan_off()
        elif self.settings.automatic_fan_speed:
            await self.device.write_fan_mode(25)
            self.settings.current_fan_speed = 25
            self._start_automatic_fan_control()
        else:
            await self.device.write_fan_mode(self.settings.current_fan_speed)
        if self.settings.rgb_is_off:
            await self.device.write_rgb_off()
        else:
            await self.device.write_rgb(*self.settings.rgb_color, self.settings.rgb_state)

    def handle_on_mode_settings(self):
        def set_low():
            self._set_pump_voltage(PumpVoltage.V7)
            self._set_fan_speed(25)
            self._set_rgb_color(0, 255, 0)

        def set_med():
            self._set_pump_voltage(PumpVoltage.V8)
            self._set_fan_speed(50)
            self._set_rgb_color(0, 0, 255)

        def set_high():
            self._set_pump_voltage(PumpVoltage.V11)
            self._set_fan_speed(90)
            self._set_rgb_color(255, 0, 0)

        def set_off():
            # ensure we turn things off (don't just blindly toggle)
            if not self.settings.pump_is_off:
                self._toggle_pump()
            if not self.settings.fan_is_off:
                self._toggle_fan()
            if not self.settings.rgb_is_off:
                self._toggle_rgb()

        menu = pystray.Menu(
            pystray.MenuItem(
                'Turn on Low Mode',
                set_low,
                checked=lambda _: (
                    not self.settings.pump_is_off
                    and self.settings.current_voltage == PumpVoltage.V7
                    and not self.settings.fan_is_off
                    and self.settings.current_fan_speed == 25
                    and not self.settings.rgb_is_off
                    and self.settings.rgb_color == (0, 255, 0)
                )
            ),
            pystray.MenuItem(
                'Turn on Med Mode',
                set_med,
                checked=lambda _: (
                    not self.settings.pump_is_off
                    and self.settings.current_voltage == PumpVoltage.V8
                    and not self.settings.fan_is_off
                    and self.settings.current_fan_speed == 50
                    and not self.settings.rgb_is_off
                    and self.settings.rgb_color == (0, 0, 255)
                )
            ),
            pystray.MenuItem(
                'Turn on High Mode',
                set_high,
                checked=lambda _: (
                    not self.settings.pump_is_off
                    and self.settings.current_voltage == PumpVoltage.V11
                    and not self.settings.fan_is_off
                    and self.settings.current_fan_speed == 90
                    and not self.settings.rgb_is_off
                    and self.settings.rgb_color == (255, 0, 0)
                )
            ),
            pystray.MenuItem(
                'Turn off Mode',
                set_off,
                checked=lambda _: (
                    self.settings.pump_is_off and self.settings.fan_is_off and self.settings.rgb_is_off
                )
            )
        )
        return menu

    def handle_pump_settings(self):
        menu = pystray.Menu(
            pystray.MenuItem('Turn Off', self._toggle_pump,
                           checked=lambda _: self.settings.pump_is_off),
            pystray.MenuItem('Voltage', pystray.Menu(
                pystray.MenuItem('7V', lambda: self._set_pump_voltage(PumpVoltage.V7),
                               checked=lambda _: not self.settings.pump_is_off and self.settings.current_voltage == PumpVoltage.V7),
                pystray.MenuItem('8V', lambda: self._set_pump_voltage(PumpVoltage.V8),
                               checked=lambda _: not self.settings.pump_is_off and self.settings.current_voltage == PumpVoltage.V8),
                pystray.MenuItem('11V', lambda: self._set_pump_voltage(PumpVoltage.V11),
                               checked=lambda _: not self.settings.pump_is_off and self.settings.current_voltage == PumpVoltage.V11)                
            ))
        )
        return menu

    def handle_fan_settings(self):
        menu = pystray.Menu(
            pystray.MenuItem('Automatic Fan speed control', self._toggle_automatic_fan_control,
                           checked=lambda _: self.settings.automatic_fan_speed),
            pystray.MenuItem('Turn Off', self._toggle_fan,
                           checked=lambda _: self.settings.fan_is_off),
            pystray.MenuItem('Speed', pystray.Menu(
                pystray.MenuItem('25%', lambda: self._set_fan_speed(25),
                               checked=lambda _: not self.settings.fan_is_off and self.settings.current_fan_speed == 25),
                pystray.MenuItem('50%', lambda: self._set_fan_speed(50),
                               checked=lambda _: not self.settings.fan_is_off and self.settings.current_fan_speed == 50),
                pystray.MenuItem('75%', lambda: self._set_fan_speed(75),
                               checked=lambda _: not self.settings.fan_is_off and self.settings.current_fan_speed == 75),
                pystray.MenuItem('90%', lambda: self._set_fan_speed(90),
                               checked=lambda _: not self.settings.fan_is_off and self.settings.current_fan_speed == 90)
            ))
        )
        return menu

    def handle_rgb_settings(self):
        menu = pystray.Menu(
            pystray.MenuItem('Turn Off', self._toggle_rgb,
                           checked=lambda _: self.settings.rgb_is_off),
            pystray.MenuItem('Mode', pystray.Menu(
                pystray.MenuItem('Static', lambda: self._set_rgb_mode(RGBState.STATIC),
                               checked=lambda _: not self.settings.rgb_is_off and self.settings.rgb_state == RGBState.STATIC),
                pystray.MenuItem('Breathe', lambda: self._set_rgb_mode(RGBState.BREATHE),
                               checked=lambda _: not self.settings.rgb_is_off and self.settings.rgb_state == RGBState.BREATHE),
                pystray.MenuItem('Rainbow', lambda: self._set_rgb_mode(RGBState.COLORFUL),
                               checked=lambda _: not self.settings.rgb_is_off and self.settings.rgb_state == RGBState.COLORFUL),
                pystray.MenuItem('Breathe Rainbow', lambda: self._set_rgb_mode(RGBState.BREATHE_COLOR),
                               checked=lambda _: not self.settings.rgb_is_off and self.settings.rgb_state == RGBState.BREATHE_COLOR)
            )),
            pystray.MenuItem('Color', pystray.Menu(
                pystray.MenuItem('Red', lambda: self._set_rgb_color(255, 0, 0),
                               checked=lambda _: not self.settings.rgb_is_off and self.settings.rgb_color == (255, 0, 0)),
                pystray.MenuItem('Green', lambda: self._set_rgb_color(0, 255, 0),
                               checked=lambda _: not self.settings.rgb_is_off and self.settings.rgb_color == (0, 255, 0)),
                pystray.MenuItem('Blue', lambda: self._set_rgb_color(0, 0, 255),
                               checked=lambda _: not self.settings.rgb_is_off and self.settings.rgb_color == (0, 0, 255)),
                pystray.MenuItem('White', lambda: self._set_rgb_color(255, 255, 255),
                               checked=lambda _: not self.settings.rgb_is_off and self.settings.rgb_color == (255, 255, 255))
            ))
        )
        return menu

    def handle_autostart_settings(self):
        self.settings.set_autostart(not self.settings.auto_start)

    def handle_autoconnect_settings(self):
        self.settings.auto_connect = not self.settings.auto_connect
        self.settings.save()

    def _toggle_pump(self):
        self.settings.pump_is_off = not self.settings.pump_is_off
        if self.settings.pump_is_off:
            asyncio.run_coroutine_threadsafe(
                self._execute_command(lambda: self.device.write_pump_off()),
                self.loop
            )
        else:
            asyncio.run_coroutine_threadsafe(
                self._execute_command(lambda: self.device.write_pump_mode(pump_voltage=self.settings.current_voltage)),
                self.loop
            )
        self.settings.save()

    def _set_pump_voltage(self, voltage: PumpVoltage):
        self.settings.current_voltage = voltage
        self.settings.pump_is_off = False
        asyncio.run_coroutine_threadsafe(
            self._execute_command(lambda: self.device.write_pump_mode(pump_voltage=voltage)),
            self.loop
        )
        self.settings.save()

    def _toggle_automatic_fan_control(self):
        self.settings.automatic_fan_speed = not self.settings.automatic_fan_speed
        if self.settings.automatic_fan_speed:
            self.settings.fan_is_off = False
            self._start_automatic_fan_control()
        else:
            self.loop.call_soon_threadsafe(self._stop_automatic_fan_control)
        self.settings.save()

    def _start_automatic_fan_control(self):
        def start():
            if self.automatic_fan_task is None or self.automatic_fan_task.done():
                self.automatic_fan_task = self.loop.create_task(self._automatic_fan_control_loop())
        self.loop.call_soon_threadsafe(start)

    def _stop_automatic_fan_control(self):
        if self.automatic_fan_task is not None and not self.automatic_fan_task.done():
            self.automatic_fan_task.cancel()
        self.automatic_fan_task = None

    async def _automatic_fan_control_loop(self):
        smoothed_temperature = None
        missing_readings = 0
        failure_notified = False
        try:
            while self.settings.automatic_fan_speed:
                if not await self.device.is_connected():
                    await asyncio.sleep(5)
                    continue
                try:
                    temperature = await asyncio.to_thread(self.temperature_monitor.get_control_temperature)
                except Exception as e:
                    temperature = None
                    if not failure_notified:
                        self.tray.show_notification(f"Temperature sensor error: {str(e)}")
                        failure_notified = True
                if temperature is None:
                    missing_readings += 1
                    target_speed = 50 if missing_readings >= 5 else self.settings.current_fan_speed
                else:
                    missing_readings = 0
                    failure_notified = False
                    smoothed_temperature = temperature if smoothed_temperature is None else 0.25 * temperature + 0.75 * smoothed_temperature
                    target_speed = calculate_fan_speed(smoothed_temperature)

                current_speed = self.settings.current_fan_speed
                if target_speed > current_speed:
                    next_speed = min(current_speed + 7, target_speed)
                else:
                    next_speed = max(current_speed - 3, target_speed)
                if abs(next_speed - current_speed) >= 3:
                    await self.device.write_fan_mode(next_speed)
                    self.settings.current_fan_speed = next_speed
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.tray.show_notification(f"Automatic fan control stopped: {str(e)}")
        finally:
            if self.automatic_fan_task is asyncio.current_task():
                self.automatic_fan_task = None

    def _toggle_fan(self):
        self.settings.fan_is_off = not self.settings.fan_is_off
        if self.settings.fan_is_off:
            self.settings.automatic_fan_speed = False
            self.loop.call_soon_threadsafe(self._stop_automatic_fan_control)
            asyncio.run_coroutine_threadsafe(
                self._execute_command(lambda: self.device.write_fan_off()),
                self.loop
            )
        else:
            asyncio.run_coroutine_threadsafe(
                self._execute_command(lambda: self.device.write_fan_mode(self.settings.current_fan_speed)),
                self.loop
            )
        self.settings.save()

    def _set_fan_speed(self, speed: int):
        self.settings.current_fan_speed = speed
        self.settings.fan_is_off = False
        self.settings.automatic_fan_speed = False
        self.loop.call_soon_threadsafe(self._stop_automatic_fan_control)
        asyncio.run_coroutine_threadsafe(
            self._execute_command(lambda: self.device.write_fan_mode(speed)),
            self.loop
        )
        self.settings.save()

    def _toggle_rgb(self):
        self.settings.rgb_is_off = not self.settings.rgb_is_off
        if self.settings.rgb_is_off:
            asyncio.run_coroutine_threadsafe(
                self._execute_command(lambda: self.device.write_rgb_off()),
                self.loop
            )
        else:
            asyncio.run_coroutine_threadsafe(
                self._execute_command(lambda: self.device.write_rgb(*self.settings.rgb_color, self.settings.rgb_state)),
                self.loop
            )
        self.settings.save()

    def _set_rgb_mode(self, state: RGBState):
        self.settings.rgb_state = state
        self.settings.rgb_is_off = False
        asyncio.run_coroutine_threadsafe(
            self._execute_command(lambda: self.device.write_rgb(*self.settings.rgb_color, state)),
            self.loop
        )
        self.settings.save()

    def _set_rgb_color(self, red: int, green: int, blue: int):
        self.settings.rgb_color = (red, green, blue)
        self.settings.rgb_is_off = False
        asyncio.run_coroutine_threadsafe(
            self._execute_command(lambda: self.device.write_rgb(red, green, blue, self.settings.rgb_state)),
            self.loop
        )
        self.settings.save()