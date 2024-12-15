import os
import json
import platform
from typing import Tuple
from .enums import PumpVoltage, RGBState

class Settings:
    REGISTRY_KEY = r"Software\WaterCooler"
    CONFIG_FILE = os.path.expanduser("~/.watercooler.json")

    def __init__(self):
        self.current_voltage = PumpVoltage.V7
        self.current_fan_speed = 50
        self.pump_is_off = False
        self.fan_is_off = False
        self.rgb_state = RGBState.STATIC
        self.rgb_is_off = False
        self.rgb_color = (255, 0, 0)  # Default red
        self.load()

    def load(self):
        if platform.system() == 'Windows':
            self._load_from_registry()
        else:
            self._load_from_file()

    def save(self):
        if platform.system() == 'Windows':
            self._save_to_registry()
        else:
            self._save_to_file()

    def _load_from_registry(self):
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
        except:
            pass

    def _save_to_registry(self):
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
        except:
            pass

    def _load_from_file(self):
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
        except:
            pass

    def _save_to_file(self):
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