import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from watercooler_manager.device import WaterCoolingDevice
from watercooler_manager.enums import NordicUART, PumpVoltage, RGBState
from watercooler_manager.app import WaterCoolerManager
from watercooler_manager.settings import Settings


class FakeClient:
    def __init__(self, device=None, disconnected_callback=None):
        self.is_connected = False
        self.disconnect_callback = disconnected_callback
        self.writes = []
        self.events = []
        self.firmware_reply = b'CoolingSystem FW V2.0.0.4'
        self.meter_reply = None

    async def connect(self, **kwargs):
        self.is_connected = True

    async def start_notify(self, uuid, callback):
        self.events.append(('notify', uuid))
        self.callback = callback

    async def write_gatt_char(self, uuid, data):
        self.events.append(('write', bytes(data)))
        self.writes.append(bytes(data))
        if data == b'sw' and self.firmware_reply:
            self.callback(None, self.firmware_reply)
        if len(data) == 8 and data[1] == 0x32 and self.meter_reply:
            self.callback(None, self.meter_reply)

    async def disconnect(self):
        self.is_connected = False
        if self.disconnect_callback:
            self.disconnect_callback(self)


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.device = WaterCoolingDevice()
        self.client = FakeClient()
        self.client.is_connected = True
        self.device.client = self.client
        self.device.connected_model = 'LCT22002'

    async def test_packets_and_validation(self):
        await self.device.write_fan_mode(100)
        await self.device.write_pump_mode(100, PumpVoltage.V8)
        await self.device.write_rgb(1, 2, 3, RGBState.BREATHE, fan=True)
        await self.device.write_rgb_off(fan=True)
        await self.device.query_meter()
        await self.device.write_sleep()
        await self.device.write_line_off()
        self.assertEqual(self.client.writes, [
            bytes.fromhex('FE 1B 01 64 00 00 00 EF'),
            bytes.fromhex('FE 1C 01 64 03 00 00 EF'),
            bytes.fromhex('FE 33 01 01 02 03 01 EF'),
            bytes.fromhex('FE 33 00 00 00 00 00 EF'),
            bytes.fromhex('FE 32 00 00 00 00 00 EF'),
            bytes.fromhex('FE 19 00 01 00 00 00 EF'),
            bytes.fromhex('FE 38 00 00 00 00 00 EF')])
        for value in (-1, 101, 255):
            with self.assertRaises(ValueError):
                await self.device.write_fan_mode(value)
        self.device.connected_model = 'LCT21001'
        with self.assertRaises(ValueError):
            await self.device.write_rgb_off(fan=True)

    async def test_flow_parsing_and_pump_off(self):
        notify = self.device._notification
        notify(None, bytes.fromhex('FE 31 00 01 00 00 00 EF'))
        self.assertEqual(self.device.flow_status, 'unknown')
        await self.device.write_pump_mode()
        for command in ('31', '32'):
            notify(None, bytes.fromhex(f'FE {command} 00 02 00 00 00 EF'))
            self.assertEqual(self.device.flow_status, 'OK')
        notify(None, bytes.fromhex('FE 31 00 03 00 00 00 EF'))
        self.assertEqual(self.device.flow_status, 'fault')
        await self.device.write_pump_off()
        self.assertEqual(self.device.flow_status, 'unknown')
        await self.device.write_pump_mode()
        self.assertEqual(self.device.flow_status, 'unknown')

    async def test_malformed_notifications_are_ignored(self):
        for data in (b'', b'\xfe', bytes.fromhex('FE 31 00 02'),
                     bytes.fromhex('FE 31 00 02 00 00 00 00'),
                     bytes.fromhex('FE 33 00 02 00 00 00 EF'), b'\xff\xfa',
                     b'arbitrary telemetry', b'CoolingSystem FW V'):
            self.device._notification(None, data)
        self.assertEqual(self.device.flow_status, 'unknown')
        self.assertIsNone(self.device.firmware_version)
        self.assertFalse(self.device._firmware_received.is_set())

    async def connect_fake(self, reply=b'CoolingSystem FW V2.0.0.4'):
        self.client.is_connected = False
        self.client.firmware_reply = reply
        self.device.FIRMWARE_TIMEOUT = 0.01
        discovered = SimpleNamespace(name='CoolingSystem LCT22002')
        with patch('watercooler_manager.device.BleakScanner.find_device_by_address',
                   AsyncMock(return_value=discovered)), patch(
                   'watercooler_manager.device.BleakClient', return_value=self.client):
            await self.device.connect('address')

    async def test_handshake_subscribes_before_query(self):
        await self.connect_fake()
        self.assertEqual(self.client.events[:2], [('notify', NordicUART.CHAR_RX), ('write', b'sw')])
        self.assertEqual(self.device.firmware_version, 'CoolingSystem FW V2.0.0.4')

    async def test_firmware_timeout_preserves_control(self):
        await self.connect_fake(None)
        self.assertIsNone(self.device.firmware_version)
        await self.device.write_fan_mode(50)
        self.assertTrue(await self.device.is_connected())

    async def test_subscription_failure_cleans_up(self):
        self.client.start_notify = AsyncMock(side_effect=RuntimeError('subscribe failed'))
        with self.assertRaisesRegex(RuntimeError, 'subscribe failed'):
            await self.connect_fake()
        self.assertIsNone(self.device.client)
        self.assertFalse(self.client.is_connected)

    async def test_late_notifications_from_old_connection_are_ignored(self):
        await self.connect_fake()
        old_callback = self.client.callback
        await self.device.disconnect()
        old_callback(None, b'CoolingSystem FW V9.9')
        self.assertIsNone(self.device.firmware_version)

    async def test_unexpected_disconnect_clears_status(self):
        self.device.on_disconnect = Mock()
        self.device.firmware_version = 'CoolingSystem FW V2'
        self.device.flow_status = 'OK'
        self.device.pump_running = True
        self.client.is_connected = False
        self.device._handle_disconnect(self.client)
        self.assertEqual(self.device.flow_status, 'unknown')
        self.assertIsNone(self.device.firmware_version)
        self.assertFalse(self.device.pump_running)
        self.device.on_disconnect.assert_called_once()

    async def test_monitor_timeout_marks_status_unknown(self):
        self.device.METER_TIMEOUT = 0.001
        self.device.METER_INTERVAL = 0.001
        self.device.flow_status = 'OK'
        self.device.start_monitoring()
        await asyncio.sleep(0.02)
        self.assertEqual(self.device.flow_status, 'unknown')
        task = self.device._monitor_task
        await self.device.disconnect()
        self.assertTrue(task.done())
        self.assertIsNone(self.device.firmware_version)
        self.assertEqual(self.client.writes[-1], bytes.fromhex('FE 19 00 01 00 00 00 EF'))

    async def test_priming_full_sequence(self):
        restore = AsyncMock()
        progress = Mock()
        with patch('watercooler_manager.device.asyncio.sleep', new_callable=AsyncMock) as sleep:
            await self.device.prime(restore, progress)
        self.assertEqual(self.client.writes[0], bytes.fromhex('FE 19 01 04 50 00 00 EF'))
        self.assertEqual(self.client.writes[1], bytes.fromhex('FE 1B 01 32 00 00 00 EF'))
        self.assertEqual(self.client.writes[-1], bytes.fromhex('FE 19 00 04 00 00 00 EF'))
        self.assertEqual(len(self.client.writes), 27)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.5, 5.5, 2.5] * 8)
        self.assertEqual(progress.call_count, 8)
        restore.assert_awaited_once()

    async def test_priming_cancellation_restores(self):
        restore = AsyncMock()
        started = asyncio.Event()
        task = asyncio.create_task(self.device.prime(restore, lambda _: started.set()))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        restore.assert_awaited_once()
        self.assertEqual(self.client.writes[-1], bytes.fromhex('FE 19 00 04 00 00 00 EF'))

    async def test_priming_write_failure_restores(self):
        restore = AsyncMock()
        self.device.write_fan_mode = AsyncMock(side_effect=RuntimeError('write failed'))
        with self.assertRaisesRegex(RuntimeError, 'write failed'):
            await self.device.prime(restore)
        restore.assert_awaited_once()
        self.assertEqual(self.client.writes[-1], bytes.fromhex('FE 19 00 04 00 00 00 EF'))

    async def test_stop_failure_still_restores(self):
        restore = AsyncMock()
        self.device.write_priming = AsyncMock(side_effect=[None, RuntimeError('stop failed')])
        with patch('watercooler_manager.device.asyncio.sleep', new_callable=AsyncMock):
            with self.assertRaisesRegex(RuntimeError, 'stop failed'):
                await self.device.prime(restore)
        restore.assert_awaited_once()


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Avoid reading/writing the user's settings or opening a tray icon.
        with patch.object(Settings, 'load'):
            self.app = WaterCoolerManager()
        self.app.settings.save = Mock()
        self.app.tray.show_notification = Mock()
        self.client = FakeClient()
        self.client.is_connected = True
        self.app.device.client = self.client
        self.app.device.connected_model = 'LCT22002'

    async def asyncTearDown(self):
        await self.app.cancel_priming()
        self.app.loop.close()

    async def test_restore_all_off_states(self):
        settings = self.app.settings
        settings.pump_is_off = settings.fan_is_off = settings.rgb_is_off = True
        settings.fan_rgb_enabled = settings.fan_rgb_is_off = True
        await self.app.apply_current_settings()
        self.assertEqual(self.client.writes, [bytes.fromhex(p) for p in (
            'FE 1C 00 00 00 00 00 EF', 'FE 1B 00 00 00 00 00 EF',
            'FE 1E 00 00 00 00 00 EF', 'FE 33 00 00 00 00 00 EF')])

    async def test_fan_rgb_is_opt_in_and_mk2_only(self):
        await self.app.apply_current_settings()
        self.assertNotIn(0x33, [p[1] for p in self.client.writes])
        self.app.settings.fan_rgb_enabled = True
        self.app.device.connected_model = 'LCT21001'
        await self.app.apply_current_settings()
        self.assertNotIn(0x33, [p[1] for p in self.client.writes])

    async def test_restore_attempts_other_outputs_after_failure(self):
        self.app.device.write_pump_mode = AsyncMock(side_effect=RuntimeError('pump failed'))
        with self.assertRaisesRegex(RuntimeError, 'Could not restore'):
            await self.app.apply_current_settings()
        self.assertEqual([p[1] for p in self.client.writes], [0x1B, 0x1E])

    async def test_fault_notifications_are_deduplicated(self):
        self.app.device.pump_running = True
        for state in ('fault', 'unknown', 'fault'):
            self.app.device.flow_status = state
            self.app._device_status()
        self.app.tray.show_notification.assert_called_once()
        self.app.device.flow_status = 'OK'
        self.app._device_status()
        self.app.device.flow_status = 'fault'
        self.app._device_status()
        self.assertEqual(self.app.tray.show_notification.call_count, 2)

    async def test_priming_cancel_before_task_starts_clears_ui(self):
        await self.app.start_priming()
        await self.app.cancel_priming()
        self.assertFalse(self.app.tray.priming)

    async def test_disconnect_waits_for_priming_cleanup(self):
        started = asyncio.Event()
        self.app.tray.update_priming_progress = lambda _: started.set()
        await self.app.start_priming()
        await started.wait()
        await self.app.disconnect()
        self.assertFalse(self.app.tray.priming)
        self.assertFalse(self.client.is_connected)
        commands = [p[1] for p in self.client.writes]
        self.assertEqual(commands[-4:], [0x1C, 0x1B, 0x1E, 0x19])

    async def test_menus_construct_with_real_pystray(self):
        items = self.app.tray.create_menu()
        self.assertIn('Fan RGB (Mk2)', [item.text for item in items])
        self.app.tray.update_device_status('CoolingSystem FW V2', 'OK', True)
        self.app.tray.update_connection_status(True)
        fan = next(item for item in self.app.tray.create_menu() if item.text == 'Fan RGB (Mk2)')
        self.assertTrue(fan.enabled)
        self.app.tray.priming = True
        self.assertFalse(fan.enabled)

    async def test_repeated_cancel_does_not_interrupt_restoration(self):
        started = asyncio.Event()
        restoring = asyncio.Event()
        release = asyncio.Event()
        self.app.tray.update_priming_progress = lambda _: started.set()
        async def restore():
            restoring.set()
            await release.wait()
        self.app.apply_current_settings = AsyncMock(side_effect=restore)
        await self.app.start_priming()
        await started.wait()
        first = asyncio.create_task(self.app.cancel_priming())
        await restoring.wait()
        second = asyncio.create_task(self.app.cancel_priming())
        await asyncio.sleep(0)
        self.assertFalse(self.app._priming_task.done())
        release.set()
        await asyncio.gather(first, second)
        self.app.apply_current_settings.assert_awaited_once()
        self.assertFalse(self.app.tray.priming)

    async def test_concurrent_disconnect_waits_for_existing_disconnect(self):
        started = asyncio.Event()
        release = asyncio.Event()
        async def disconnect():
            started.set()
            await release.wait()
        self.app.device.disconnect = AsyncMock(side_effect=disconnect)
        first = asyncio.create_task(self.app.disconnect())
        await started.wait()
        second = asyncio.create_task(self.app.disconnect())
        await asyncio.sleep(0)
        self.assertFalse(second.done())
        release.set()
        await asyncio.gather(first, second)
        self.app.device.disconnect.assert_awaited_once()


class SettingsTests(unittest.TestCase):
    def test_json_round_trip_and_old_config_defaults(self):
        with patch.object(Settings, 'load'):
            settings = Settings()
            restored = Settings()
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'settings.json')
            settings.CONFIG_FILE = restored.CONFIG_FILE = path
            settings.fan_rgb_enabled = True
            settings.fan_rgb_color = (1, 2, 3)
            settings.fan_rgb_state = RGBState.BREATHE
            settings._save_to_file()
            restored._load_from_file()
            self.assertEqual(restored._fan_rgb_config(), settings._fan_rgb_config())
            config = json.loads(Path(path).read_text())
            del config['fan_rgb']
            Path(path).write_text(json.dumps(config))
            with patch.object(Settings, 'load'):
                old = Settings()
            old.CONFIG_FILE = path
            old._load_from_file()
            self.assertFalse(old.fan_rgb_enabled)
            self.assertEqual(old.current_voltage, settings.current_voltage)

    def test_invalid_fan_settings_do_not_partially_apply(self):
        with patch.object(Settings, 'load'):
            settings = Settings()
        with self.assertRaises(ValueError):
            settings._load_fan_rgb(dict(enabled=True, color=[256, 0, 0]))
        self.assertFalse(settings.fan_rgb_enabled)


if __name__ == '__main__':
    unittest.main()
