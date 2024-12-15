from enum import IntEnum

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

class DeviceCommands:
    RESET = 0x19
    FAN = 0x1b
    PUMP = 0x1c
    RGB = 0x1e 