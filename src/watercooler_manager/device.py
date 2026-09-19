import asyncio
from contextlib import suppress
from typing import Optional, List

from bleak import BleakScanner, BleakClient
from .models import DeviceInfo, LCTDeviceModel
from .enums import PumpVoltage, RGBState, Commands, NordicUART


class WaterCoolingDevice:
    FIRMWARE_TIMEOUT = 3.0
    METER_TIMEOUT = 5.0
    METER_INTERVAL = 15.0

    def __init__(self, on_status=None, on_disconnect=None):
        self.client: Optional[BleakClient] = None
        self.connected_model: Optional[str] = None
        self.firmware_version = None
        self.flow_status = "unknown"
        self.pump_running = False
        self.on_status = on_status or (lambda: None)
        self.on_disconnect = on_disconnect or (lambda: None)
        self._firmware_received = asyncio.Event()
        self._meter_received = asyncio.Event()
        self._monitor_task = None
        self._write_lock = asyncio.Lock()
        self._loop = None
        self._closing = False

    @property
    def supports_fan_rgb(self):
        return self.connected_model == LCTDeviceModel.LCT22002

    def _set_flow(self, status):
        if self.flow_status != status:
            self.flow_status = status
            self.on_status()

    def _clear_status(self):
        self.connected_model = None
        self.firmware_version = None
        self.pump_running = False
        self.flow_status = "unknown"
        self.on_status()

    def _disconnected(self, client):
        # Bleak callbacks may originate outside our asyncio thread.
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._handle_disconnect, client)

    def _handle_disconnect(self, client):
        if client is not self.client:
            return
        if self._monitor_task:
            self._monitor_task.cancel()
        self._clear_status()
        if not self._closing:
            self.on_disconnect()

    def _notification(self, sender, data):
        if not data:
            return
        if data[0] == 0xFE:
            if (len(data) != 8 or data[-1] != 0xEF or
                    data[1] not in (Commands.METER_PUSH, Commands.QUERY_METER)):
                return
            self._meter_received.set()
            self._set_flow(("OK" if data[3] == 2 else "fault")
                           if self.pump_running else "unknown")
            return
        # Do not mistake unknown binary telemetry for a firmware version.
        try:
            version = bytes(data).decode("utf-8").strip("\x00\r\n ")
        except UnicodeDecodeError:
            return
        if not version.startswith("CoolingSystem FW V") or not version.isprintable():
            return
        if len(version) <= len("CoolingSystem FW V"):
            return
        self.firmware_version = version
        self._firmware_received.set()
        self.on_status()

    async def connect(self, device_uuid: str):
        if await self.is_connected():
            return
        self._loop = asyncio.get_running_loop()
        self._closing = False
        self._clear_status()
        self._firmware_received.clear()
        self._meter_received.clear()
        device = await BleakScanner.find_device_by_address(device_uuid)
        if not device:
            raise RuntimeError("Device not found")
        self.client = BleakClient(device, disconnected_callback=self._disconnected)
        client = self.client

        def receive(sender, data):
            # Ignore notifications queued by a previous connection.
            if client is self.client and client.is_connected:
                self._notification(sender, data)

        try:
            # Bleak 3 takes no connection options here; bound the whole operation.
            await asyncio.wait_for(self.client.connect(), timeout=5.0)
            self.connected_model = await self.device_model_from_name(device.name or "")
            await self.client.start_notify(NordicUART.CHAR_RX, receive)
            await self.write_buffer(b"sw")
            try:
                await asyncio.wait_for(self._firmware_received.wait(), self.FIRMWARE_TIMEOUT)
            except asyncio.TimeoutError:
                # Older firmware may still accept control commands without this reply.
                pass
            if not await self.is_connected():
                raise RuntimeError("Device disconnected during handshake")
            self.on_status()
        except BaseException:
            await self.disconnect(sleep=False)
            raise

    def start_monitoring(self):
        if not self._monitor_task or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_flow())

    async def _monitor_flow(self):
        while await self.is_connected():
            self._meter_received.clear()
            try:
                await self.query_meter()
                await asyncio.wait_for(self._meter_received.wait(), self.METER_TIMEOUT)
            except Exception:
                self._set_flow("unknown")
            await asyncio.sleep(self.METER_INTERVAL)

    async def disconnect(self, sleep=True):
        self._closing = True
        if self._monitor_task:
            self._monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None
        client = self.client
        try:
            if client and client.is_connected:
                if sleep:
                    with suppress(Exception):
                        await self.write_sleep()
                await client.disconnect()
        finally:
            self.client = None
            self._clear_status()

    async def device_model_from_name(self, name: str) -> Optional[str]:
        for model in (LCTDeviceModel.LCT21001, LCTDeviceModel.LCT22002):
            if model.lower() in name.lower():
                return model
        return None

    async def get_device_list(self) -> List[DeviceInfo]:
        devices = await BleakScanner.discover(return_adv=True)
        result = []
        for device, adv in devices.values():
            name = device.name or adv.local_name or ""
            if await self.device_model_from_name(name):
                info = DeviceInfo()
                info.uuid, info.name, info.rssi = device.address, name, adv.rssi or 0
                result.append(info)
        return result

    async def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    async def write_buffer(self, data):
        async with self._write_lock:
            if not await self.is_connected():
                raise RuntimeError("Not connected")
            await asyncio.wait_for(
                self.client.write_gatt_char(NordicUART.CHAR_TX, data), timeout=5.0)

    async def _command(self, command, enabled=0, p1=0, p2=0, p3=0, p4=0):
        await self.write_buffer(bytearray([0xFE, command, enabled, p1, p2, p3, p4, 0xEF]))

    async def write_rgb(self, red: int, green: int, blue: int, state: RGBState, fan=False):
        if fan and not self.supports_fan_rgb:
            raise ValueError("Fan lighting requires LCT22002")
        if not all(0 <= x <= 255 for x in (red, green, blue)) or not 0 <= state <= 3:
            raise ValueError("Parameters out of range")
        await self._command(Commands.FAN_RGB if fan else Commands.RGB,
                            1, red, green, blue, state)

    async def write_rgb_off(self, fan=False):
        if fan and not self.supports_fan_rgb:
            raise ValueError("Fan lighting requires LCT22002")
        await self._command(Commands.FAN_RGB if fan else Commands.RGB)

    async def write_fan_mode(self, duty_cycle_percent: int):
        if not 0 <= duty_cycle_percent <= 100:
            raise ValueError("Duty cycle must be between 0 and 100")
        await self._command(Commands.FAN, 1, duty_cycle_percent)

    async def write_fan_off(self):
        await self._command(Commands.FAN)

    async def write_pump_mode(self, pump_duty_cycle_percent: int = 60,
                              pump_voltage: PumpVoltage = PumpVoltage.V7):
        if not 0 <= pump_duty_cycle_percent <= 100 or not 0 <= pump_voltage <= 3:
            raise ValueError("Parameters out of range")
        await self._command(Commands.PUMP, 1, pump_duty_cycle_percent, pump_voltage)
        was_running = self.pump_running
        self.pump_running = pump_duty_cycle_percent > 0
        if not was_running or not self.pump_running:
            self._set_flow("unknown")

    async def write_pump_off(self):
        await self._command(Commands.PUMP)
        self.pump_running = False
        self._set_flow("unknown")

    async def write_sleep(self):
        await self._command(Commands.SYSTEM_MODE, 0, 1)
        self.pump_running = False
        self._set_flow("unknown")

    async def write_line_off(self):
        """OEM line-off command; intentionally not the default disconnect policy."""
        await self._command(Commands.LINE_OFF)

    async def query_meter(self):
        await self._command(Commands.QUERY_METER)

    async def write_priming(self, enabled):
        await self._command(Commands.SYSTEM_MODE, int(enabled), 4, 0x50 if enabled else 0)

    async def prime(self, restore, on_progress=None):
        """Run the OEM fill cycle; cancellation still stops priming and restores settings."""
        try:
            await self.write_priming(True)
            await self.write_fan_mode(50)
            for cycle in range(8):
                if on_progress:
                    on_progress(cycle + 1)
                await self.write_pump_off()
                await asyncio.sleep(0.5)
                await self.write_pump_mode(100, PumpVoltage.V8)
                await asyncio.sleep(5.5)
                await self.write_pump_off()
                await asyncio.sleep(2.5)
        finally:
            if await self.is_connected():
                # Restoration must also be attempted when the stop command fails.
                try:
                    await self.write_priming(False)
                finally:
                    await restore()
