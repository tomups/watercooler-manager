import asyncio
from enum import IntEnum
from bleak import BleakScanner, BleakClient
from typing import Optional, List
import pystray
from PIL import Image, ImageDraw
import threading
import os
import json
import platform
import sys

class RGBState(IntEnum):
    STATIC = 0x00
    BREATHE = 0x01
    COLORFUL = 0x02
    BREATHE_COLOR = 0x03

class PumpVoltage(IntEnum):
    V11 = 0x00
    V12 = 0x01
    V7 = 0x02
    V8 = 0x03

class LCTDeviceModel:
    LCT21001 = 'LCT21001'
    LCT22002 = 'LCT22002'

class DeviceInfo:
    def __init__(self):
        self.uuid: str = ""
        self.name: str = ""
        self.rssi: int = 0

class LCT21001:
    NORDIC_UART_SERVICE_UUID = '6e400001-b5a3-f393-e0a9-e50e24dcca9e'
    NORDIC_UART_CHAR_TX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'
    NORDIC_UART_CHAR_RX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e'

    CMD_RESET = 0x19
    CMD_FAN = 0x1b
    CMD_PUMP = 0x1c
    CMD_RGB = 0x1e

    REGISTRY_KEY = r"Software\WaterCooler"
    CONFIG_FILE = os.path.expanduser("~/.watercooler.json")

    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.connected_model: Optional[str] = None
        self.loop = asyncio.new_event_loop()
        self.thread = None
        self.icon = None
        
        # Load saved settings or use defaults
        self.load_settings()
        self.setup_tray()
        
        # Auto connect on startup
        asyncio.run_coroutine_threadsafe(self.connect_and_run(), self.loop)

    def load_settings(self):
        if platform.system() == 'Windows':
            try:
                import winreg
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.REGISTRY_KEY)
                self.current_voltage = PumpVoltage(winreg.QueryValueEx(key, "current_voltage")[0])
                self.current_fan_speed = winreg.QueryValueEx(key, "current_fan_speed")[0]
                self.pump_is_off = bool(winreg.QueryValueEx(key, "pump_is_off")[0])
                self.fan_is_off = bool(winreg.QueryValueEx(key, "fan_is_off")[0])
                self.rgb_state = RGBState(winreg.QueryValueEx(key, "rgb_state")[0])
                self.rgb_is_off = bool(winreg.QueryValueEx(key, "rgb_is_off")[0])
                self.rgb_color = tuple(winreg.QueryValueEx(key, "rgb_color")[0])
                winreg.CloseKey(key)
                return
            except:
                pass
        else:
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.current_voltage = PumpVoltage(config['current_voltage'])
                    self.current_fan_speed = config['current_fan_speed']
                    self.pump_is_off = config['pump_is_off']
                    self.fan_is_off = config['fan_is_off']
                    self.rgb_state = RGBState(config['rgb_state'])
                    self.rgb_is_off = config['rgb_is_off']
                    self.rgb_color = tuple(config['rgb_color'])
                    return
            except:
                pass

        # If loading fails, use defaults
        self.current_voltage = PumpVoltage.V7
        self.current_fan_speed = 50
        self.pump_is_off = False
        self.fan_is_off = False
        self.rgb_state = RGBState.STATIC
        self.rgb_is_off = False
        self.rgb_color = (255, 0, 0)  # Default red
        self.status_message = "Not connected"

    def save_settings(self):
        if platform.system() == 'Windows':
            try:
                import winreg
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.REGISTRY_KEY)
                winreg.SetValueEx(key, "current_voltage", 0, winreg.REG_DWORD, self.current_voltage)
                winreg.SetValueEx(key, "current_fan_speed", 0, winreg.REG_DWORD, self.current_fan_speed)
                winreg.SetValueEx(key, "pump_is_off", 0, winreg.REG_DWORD, int(self.pump_is_off))
                winreg.SetValueEx(key, "fan_is_off", 0, winreg.REG_DWORD, int(self.fan_is_off))
                winreg.SetValueEx(key, "rgb_state", 0, winreg.REG_DWORD, self.rgb_state)
                winreg.SetValueEx(key, "rgb_is_off", 0, winreg.REG_DWORD, int(self.rgb_is_off))
                winreg.SetValueEx(key, "rgb_color", 0, winreg.REG_BINARY, bytes(self.rgb_color))
                winreg.CloseKey(key)
                return
            except:
                pass
        else:
            try:
                config = {
                    'current_voltage': self.current_voltage,
                    'current_fan_speed': self.current_fan_speed,
                    'pump_is_off': self.pump_is_off,
                    'fan_is_off': self.fan_is_off,
                    'rgb_state': self.rgb_state,
                    'rgb_is_off': self.rgb_is_off,
                    'rgb_color': self.rgb_color
                }
                with open(self.CONFIG_FILE, 'w') as f:
                    json.dump(config, f)
            except:
                pass

    def create_icon_image(self, connected: bool = False):
        image = Image.new('RGBA', (64, 64), color=(0,0,0,0))
        draw = ImageDraw.Draw(image)
        
        # Draw water drop shape
        points = [
            (32, 10),  # Top point
            (54, 40),  # Bottom right
            (32, 54),  # Bottom middle
            (10, 40),  # Bottom left
        ]
        color = '#00a0ff' if connected else '#000080'  # Light blue if connected, dark blue if not
        draw.polygon(points, fill=color)
        return image

    def setup_tray(self):
        # Create initial icon (disconnected state)
        image = self.create_icon_image(connected=False)
        
        menu = (
            pystray.MenuItem('Connect', self.connect_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Pump Settings', pystray.Menu(
                pystray.MenuItem('Turn Off', self.pump_off, checked=lambda item: self.pump_is_off),
                pystray.MenuItem('Voltage', pystray.Menu(
                    pystray.MenuItem('7V', lambda: self.set_pump_voltage(PumpVoltage.V7),
                                   checked=lambda item: not self.pump_is_off and self.current_voltage == PumpVoltage.V7),
                    pystray.MenuItem('8V', lambda: self.set_pump_voltage(PumpVoltage.V8),
                                   checked=lambda item: not self.pump_is_off and self.current_voltage == PumpVoltage.V8),
                    pystray.MenuItem('11V', lambda: self.set_pump_voltage(PumpVoltage.V11), 
                                   checked=lambda item: not self.pump_is_off and self.current_voltage == PumpVoltage.V11),
                    pystray.MenuItem('12V', lambda: self.set_pump_voltage(PumpVoltage.V12),
                                   checked=lambda item: not self.pump_is_off and self.current_voltage == PumpVoltage.V12)
                ))
            )),
            pystray.MenuItem('Fan Settings', pystray.Menu(
                pystray.MenuItem('Turn Off', self.fan_off, checked=lambda item: self.fan_is_off),
                pystray.MenuItem('Speed', pystray.Menu(
                    pystray.MenuItem('25%', lambda: self.set_fan_speed(25),
                                   checked=lambda item: not self.fan_is_off and self.current_fan_speed == 25),
                    pystray.MenuItem('50%', lambda: self.set_fan_speed(50),
                                   checked=lambda item: not self.fan_is_off and self.current_fan_speed == 50),
                    pystray.MenuItem('75%', lambda: self.set_fan_speed(75),
                                   checked=lambda item: not self.fan_is_off and self.current_fan_speed == 75),
                    pystray.MenuItem('100%', lambda: self.set_fan_speed(100),
                                   checked=lambda item: not self.fan_is_off and self.current_fan_speed == 100)
                ))
            )),
            pystray.MenuItem('RGB Settings', pystray.Menu(
                pystray.MenuItem('Turn Off', self.rgb_off, checked=lambda item: self.rgb_is_off),
                pystray.MenuItem('Mode', pystray.Menu(
                    pystray.MenuItem('Static', lambda: self.set_rgb_mode(RGBState.STATIC),
                                   checked=lambda item: not self.rgb_is_off and self.rgb_state == RGBState.STATIC),
                    pystray.MenuItem('Breathe', lambda: self.set_rgb_mode(RGBState.BREATHE),
                                   checked=lambda item: not self.rgb_is_off and self.rgb_state == RGBState.BREATHE),
                    pystray.MenuItem('Rainbow', lambda: self.set_rgb_mode(RGBState.COLORFUL),
                                   checked=lambda item: not self.rgb_is_off and self.rgb_state == RGBState.COLORFUL),
                    pystray.MenuItem('Breathe Rainbow', lambda: self.set_rgb_mode(RGBState.BREATHE_COLOR),
                                   checked=lambda item: not self.rgb_is_off and self.rgb_state == RGBState.BREATHE_COLOR)
                )),
                pystray.MenuItem('Color', pystray.Menu(
                    pystray.MenuItem('Red', lambda: self.set_rgb_color(255, 0, 0),
                                   checked=lambda item: not self.rgb_is_off and self.rgb_color == (255, 0, 0)),
                    pystray.MenuItem('Green', lambda: self.set_rgb_color(0, 255, 0),
                                   checked=lambda item: not self.rgb_is_off and self.rgb_color == (0, 255, 0)),
                    pystray.MenuItem('Blue', lambda: self.set_rgb_color(0, 0, 255),
                                   checked=lambda item: not self.rgb_is_off and self.rgb_color == (0, 0, 255)),
                    pystray.MenuItem('White', lambda: self.set_rgb_color(255, 255, 255),
                                   checked=lambda item: not self.rgb_is_off and self.rgb_color == (255, 255, 255))
                ))
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Exit', self.exit_app)
        )

        self.icon = pystray.Icon("WaterCooler", image, "Water Cooler manager", menu)
        

    def update_menu_status(self):
        # Create new menu with updated connect/disconnect status
        menu = list(self.icon.menu)
        is_connected = self.client and self.client.is_connected
        menu[0] = pystray.MenuItem(
            'Disconnect' if is_connected else 'Connect',
            self.disconnect_menu if is_connected else self.connect_menu
        )
        self.icon._menu = pystray.Menu(*menu)
        self.icon.update_menu()

    def show_notification(self, message: str):
        self.status_message = message
        self.icon.notify(message, title="WaterCooler")

    def run(self):
        self.thread = threading.Thread(target=self.icon.run, daemon=True)
        self.thread.start()

    def exit_app(self):
        # Stop the event loop
        self.loop.call_soon_threadsafe(self.loop.stop)
        
        # Disconnect BLE
        if self.client and self.client.is_connected:
            asyncio.run_coroutine_threadsafe(self.disconnect(), self.loop)
        
        # Save settings
        self.save_settings()
        
        # Stop the icon
        self.icon.stop()
        
        # Exit the program
        sys.exit(0)

    def connect_menu(self):
        asyncio.run_coroutine_threadsafe(self.connect_and_run(), self.loop)

    def disconnect_menu(self):
        asyncio.run_coroutine_threadsafe(self.disconnect(), self.loop)

    def pump_off(self):
        self.pump_is_off = not self.pump_is_off
        if self.pump_is_off:
            asyncio.run_coroutine_threadsafe(self.write_pump_off(), self.loop)
        else:
            asyncio.run_coroutine_threadsafe(self.write_pump_mode(pump_voltage=self.current_voltage), self.loop)
        self.icon.update_menu()
        self.save_settings()

    def set_pump_voltage(self, voltage: PumpVoltage):
        self.current_voltage = voltage
        self.pump_is_off = False
        asyncio.run_coroutine_threadsafe(self.write_pump_mode(pump_voltage=voltage), self.loop)
        self.icon.update_menu()
        self.update_menu_status()
        self.save_settings()

    def fan_off(self):
        self.fan_is_off = not self.fan_is_off
        if self.fan_is_off:
            asyncio.run_coroutine_threadsafe(self.write_fan_off(), self.loop)
        else:
            asyncio.run_coroutine_threadsafe(self.write_fan_mode(self.current_fan_speed), self.loop)
        self.icon.update_menu()
        self.save_settings()

    def set_fan_speed(self, speed: int):
        self.current_fan_speed = speed
        self.fan_is_off = False
        asyncio.run_coroutine_threadsafe(self.write_fan_mode(speed), self.loop)
        self.icon.update_menu()
        self.save_settings()

    def rgb_off(self):
        self.rgb_is_off = not self.rgb_is_off
        if self.rgb_is_off:
            asyncio.run_coroutine_threadsafe(self.write_rgb_off(), self.loop)
        else:
            asyncio.run_coroutine_threadsafe(self.write_rgb(*self.rgb_color, self.rgb_state), self.loop)
        self.icon.update_menu()
        self.save_settings()

    def set_rgb_mode(self, state: RGBState):
        self.rgb_state = state
        self.rgb_is_off = False
        asyncio.run_coroutine_threadsafe(self.write_rgb(*self.rgb_color, state), self.loop)
        self.icon.update_menu()
        self.save_settings()

    def set_rgb_color(self, red: int, green: int, blue: int):
        self.rgb_color = (red, green, blue)
        self.rgb_is_off = False
        asyncio.run_coroutine_threadsafe(self.write_rgb(red, green, blue, self.rgb_state), self.loop)
        self.icon.update_menu()
        self.save_settings()

    def get_connected_model(self) -> Optional[str]:
        return self.connected_model

    async def device_model_from_name(self, name: str) -> Optional[str]:
        for model in [LCTDeviceModel.LCT21001, LCTDeviceModel.LCT22002]:
            if model.lower() in name.lower():
                return model
        return None

    async def connect(self, device_uuid: str):
        device = await BleakScanner.find_device_by_address(device_uuid)
        if not device:
            raise Exception("Device not found")

        try:
            self.client = BleakClient(device_uuid)
            await self.client.connect(timeout=5.0)
            self.connected_model = await self.device_model_from_name(device.name or "")
            # Update icon to connected state
            self.icon.icon = self.create_icon_image(connected=True)
            self.update_menu_status()
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
            # Update icon to disconnected state
            self.icon.icon = self.create_icon_image(connected=False)
            self.update_menu_status()

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
        data = bytearray([0xfe, self.CMD_RGB, 0x01, red, green, blue, state, 0xef])
        await self.write_buffer(data)

    async def write_rgb_off(self):
        data = bytearray([0xfe, self.CMD_RGB, 0x00, 0x00, 0x00, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def write_fan_mode(self, duty_cycle_percent: int):
        if not 0 <= duty_cycle_percent <= 0xff:
            raise ValueError("Duty cycle out of range")
        data = bytearray([0xfe, self.CMD_FAN, 0x01, duty_cycle_percent, 0x00, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def write_fan_off(self):
        data = bytearray([0xfe, self.CMD_FAN, 0x00, 0x00, 0x00, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def write_pump_mode(self, pump_duty_cycle_percent: int = 60, pump_voltage: PumpVoltage = PumpVoltage.V7):
        if not 0 <= pump_duty_cycle_percent <= 100 or not 0 <= pump_voltage <= 0x03:
            raise ValueError("Parameters out of range")
        data = bytearray([0xfe, self.CMD_PUMP, 0x01, pump_duty_cycle_percent, pump_voltage, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def write_pump_off(self):
        data = bytearray([0xfe, self.CMD_PUMP, 0x00, 0x00, 0x00, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def read_fw_version(self) -> bytearray:
        if not await self.is_connected():
            raise Exception("Not connected")
        await self.write_buffer(bytearray([0x73, 0x77]))
        return await self.client.read_gatt_char(self.NORDIC_UART_CHAR_RX)

    async def write_reset(self):
        data = bytearray([0xfe, self.CMD_RESET, 0x00, 0x01, 0x00, 0x00, 0x00, 0xef])
        await self.write_buffer(data)

    async def connect_and_run(self):
        self.show_notification("Scanning for CoolingSystem device...")
        devices = await BleakScanner.discover()
        
        target_device = None
        for device in devices:
            if device.name and "CoolingSystem" in device.name:
                target_device = device
                break

        if not target_device:
            self.show_notification("CoolingSystem device not found")
            return

        self.show_notification(f"Found device at {target_device.address}")
        
        try:
            await self.connect(target_device.address)
            self.show_notification(f"Successfully connected to {target_device.name}")
            
            # Start with current settings
            await self.write_pump_mode(pump_voltage=self.current_voltage)
            await self.write_fan_mode(self.current_fan_speed)
            if not self.rgb_is_off:
                await self.write_rgb(*self.rgb_color, self.rgb_state)
            
        except Exception as e:
            self.show_notification(f"Error occurred: {str(e)}")
            if await self.is_connected():
                await self.disconnect()

if __name__ == "__main__":
    cooler = LCT21001()
    
    # Start the event loop in a separate thread
    def run_event_loop():
        asyncio.set_event_loop(cooler.loop)
        cooler.loop.run_forever()
    
    loop_thread = threading.Thread(target=run_event_loop)
    loop_thread.start()
    
    # Run the system tray icon in a background thread and return
    cooler.run()
