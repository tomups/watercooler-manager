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

class Commands:
    SYSTEM_MODE = 0x19
    FAN = 0x1b
    PUMP = 0x1c
    RGB = 0x1e
    METER_PUSH = 0x31
    QUERY_METER = 0x32
    MK2_RGB_EFFECT = 0x33
    LINE_OFF = 0x38

class NordicUART:
    SERVICE_UUID = '6e400001-b5a3-f393-e0a9-e50e24dcca9e'
    CHAR_TX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'
    CHAR_RX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e'
