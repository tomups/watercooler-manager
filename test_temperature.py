import importlib.util
import unittest
from pathlib import Path

module_path = Path(__file__).parent / "src" / "watercooler_manager" / "temperature.py"
spec = importlib.util.spec_from_file_location("temperature", module_path)
temperature_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(temperature_module)
calculate_fan_speed = temperature_module.calculate_fan_speed


class FanCurveTests(unittest.TestCase):
    def test_minimum_speed_below_lower_threshold(self):
        self.assertEqual(calculate_fan_speed(30), 25)
        self.assertEqual(calculate_fan_speed(45), 25)

    def test_maximum_speed_above_upper_threshold(self):
        self.assertEqual(calculate_fan_speed(85), 90)
        self.assertEqual(calculate_fan_speed(100), 90)

    def test_speed_increases_smoothly_between_thresholds(self):
        speeds = [calculate_fan_speed(temperature) for temperature in range(45, 86)]
        self.assertEqual(speeds, sorted(speeds))
        self.assertEqual(calculate_fan_speed(65), 58)
        self.assertTrue(all(25 <= speed <= 90 for speed in speeds))


if __name__ == "__main__":
    unittest.main()
