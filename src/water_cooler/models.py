class LCTDeviceModel:
    LCT21001 = 'LCT21001'
    LCT22002 = 'LCT22002'

class DeviceInfo:
    def __init__(self):
        self.uuid: str = ""
        self.name: str = ""
        self.rssi: int = 0 