import os
import sys
from pathlib import Path
from typing import Optional


MIN_VALID_TEMPERATURE = 0.0
MAX_VALID_TEMPERATURE = 120.0


def calculate_fan_speed(temperature: float) -> int:
    if temperature <= 45.0:
        return 25
    if temperature >= 85.0:
        return 90
    return round(25 + (temperature - 45.0) * 65 / 40)


class LibreHardwareTemperatureMonitor:
    def __init__(self):
        self.computer = None
        self.sensor_type = None
        self.hardware_types = set()

    def open(self):
        if self.computer is not None:
            return

        assembly_dir = self._assembly_dir()
        if not assembly_dir.exists():
            raise RuntimeError("LibreHardwareMonitor is not installed in the application bundle")

        os.environ["PATH"] = f"{assembly_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        sys.path.insert(0, str(assembly_dir))

        import clr
        clr.AddReference(str(assembly_dir / "LibreHardwareMonitorLib.dll"))
        from LibreHardwareMonitor.Hardware import Computer, HardwareType, SensorType

        computer = Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = True
        computer.Open()
        self.computer = computer
        self.sensor_type = SensorType.Temperature
        self.hardware_types = {
            HardwareType.Cpu,
            HardwareType.GpuAmd,
            HardwareType.GpuIntel,
            HardwareType.GpuNvidia,
        }

    def close(self):
        if self.computer is not None:
            self.computer.Close()
            self.computer = None

    def get_control_temperature(self) -> Optional[float]:
        self.open()
        temperatures = []
        for hardware in self.computer.Hardware:
            temperatures.extend(self._read_hardware(hardware))
        return max(temperatures) if temperatures else None

    def _read_hardware(self, hardware):
        temperatures = []
        hardware.Update()
        if hardware.HardwareType in self.hardware_types:
            for sensor in hardware.Sensors:
                if sensor.SensorType == self.sensor_type and sensor.Value is not None:
                    value = float(sensor.Value)
                    if MIN_VALID_TEMPERATURE <= value <= MAX_VALID_TEMPERATURE:
                        temperatures.append(value)
        for subhardware in hardware.SubHardware:
            temperatures.extend(self._read_hardware(subhardware))
        return temperatures

    @staticmethod
    def _assembly_dir() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS) / "librehardwaremonitor"
        return Path(__file__).resolve().parents[2] / "vendor" / "librehardwaremonitor"
