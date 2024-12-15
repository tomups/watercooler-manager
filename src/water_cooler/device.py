from typing import Optional, List
from bleak import BleakScanner, BleakClient
from .models import DeviceInfo, LCTDeviceModel
from .enums import PumpVoltage, RGBState, DeviceCommands

class WaterCoolingDevice:
    NORDIC_UART_SERVICE_UUID = '6e400001-b5a3-f393-e0a9-e50e24dcca9e'
    NORDIC_UART_CHAR_TX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'
    NORDIC_UART_CHAR_RX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e'

    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.connected_model: Optional[str] = None

    async def connect(self, device_uuid: str):
        device = await BleakScanner.find_device_by_address(device_uuid)
        if not device:
            raise Exception("Device not found")

        try:
            self.client = BleakClient(device_uuid)
            await self.client.connect(timeout=5.0)
            self.connected_model = await self.device_model_from_name(device.name or "")
        except Exception as e:
            if self.client:
                await self.client.disconnect()
            raise Exception(f"Failed to connect: {str(e)}")

    async def disconnect(self):
        if self.client and self.client.is_connected:
            try:
                await self.write_reset()
            except:
                pass
            await self.client.disconnect()
            self.client = None
            self.connected_model = None

    async def device_model_from_name(self, name: str) -> Optional[str]:
        for model in [LCTDeviceModel.LCT21001, LCTDeviceModel.LCT22002]:
            if model.lower() in name.lower():
                return model
        return None

    async def get_device_list(self) -> List[DeviceInfo]:
        devices = await BleakScanner.discover()
        device_info_list = []

        for device in devices:
            if not device.name:
                continue

            model = await self.device_model_from_name(device.name)
            if model:
                info = DeviceInfo()
                info.uuid = device.address
                info.name = device.name
                info.rssi = device.rssi or 0
                device_info_list.append(info)

        return device_info_list

    async def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    async def write_buffer(self, data: bytearray):
        if not await self.is_connected():
            raise Exception("Not connected")
        await self.client.write_gatt_char(self.NORDIC_UART_CHAR_TX, data)

    async def write_rgb(self, red: int, green: int, blue: int, state: RGBState):
        if not all(0 <= x <= 0xff for x in (red, green, blue)) or not 0 <= state <= 0x03:
            raise ValueError("Parameters out of range")
        data = bytearray([0xfe, DeviceCommands.RGB, 0x01, red, green, blue, state, 0xef])
        await self.write_buffer(data)

    async def write_rgb_off(self):
        data = bytearray([0xfe, DeviceCommands.RGB, 0x00, 0x00, 0x00, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def write_fan_mode(self, duty_cycle_percent: int):
        if not 0 <= duty_cycle_percent <= 0xff:
            raise ValueError("Duty cycle out of range")
        data = bytearray([0xfe, DeviceCommands.FAN, 0x01, duty_cycle_percent, 0x00, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def write_fan_off(self):
        data = bytearray([0xfe, DeviceCommands.FAN, 0x00, 0x00, 0x00, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def write_pump_mode(self, pump_duty_cycle_percent: int = 60, pump_voltage: PumpVoltage = PumpVoltage.V7):
        if not 0 <= pump_duty_cycle_percent <= 100 or not 0 <= pump_voltage <= 0x03:
            raise ValueError("Parameters out of range")
        data = bytearray([0xfe, DeviceCommands.PUMP, 0x01, pump_duty_cycle_percent, pump_voltage, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def write_pump_off(self):
        data = bytearray([0xfe, DeviceCommands.PUMP, 0x00, 0x00, 0x00, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def write_reset(self):
        data = bytearray([0xfe, DeviceCommands.RESET, 0x00, 0x01, 0x00, 0x00, 0x00, 0xef])
        await self.write_buffer(data) 