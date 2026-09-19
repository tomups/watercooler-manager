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
        await self.device.write_rgb(1, 2, 3, RGBState.BREATHE)
        await self.device.write_rgb_off()
        await self.device.query_meter()
        await self.device.write_sleep()
        await self.device.write_line_off()
        self.assertEqual(self.client.writes, [
            bytes.fromhex('FE 1B 01 64 00 00 00 EF'),
            bytes.fromhex('FE 1C 01 64 03 00 00 EF'),
            bytes.fromhex('FE 33 00 00 00 00 00 EF'),
            bytes.fromhex('FE 1E 01 01 02 03 01 EF'),
            bytes.fromhex('FE 33 01 01 02 03 01 EF'),
            bytes.fromhex('FE 33 00 00 00 00 00 EF'),
            bytes.fromhex('FE 1E 00 00 00 00 00 EF'),
            bytes.fromhex('FE 32 00 00 00 00 00 EF'),
            bytes.fromhex('FE 19 00 01 00 00 00 EF'),
            bytes.fromhex('FE 38 00 00 00 00 00 EF')])
        for value in (-1, 101, 255):
            with self.assertRaises(ValueError):
                await self.device.write_fan_mode(value)

    async def test_mk1_lighting_does_not_send_mk2_command(self):
        self.device.connected_model = 'LCT21001'
        for state in list(RGBState)[:4]:
            await self.device.write_rgb(0, 255, 0, state)
        await self.device.write_rgb_off()
        self.assertEqual(self.client.writes, [bytes([0xFE, 0x1E, 1, 0, 255, 0, state, 0xEF])
                                             for state in list(RGBState)[:4]] +
                         [bytes.fromhex('FE 1E 00 00 00 00 00 EF')])

    async def test_unsupported_effects_are_rejected_before_writing(self):
        for model in ('LCT21001', None):
            self.device.connected_model = model
            for state in (4, 5, 6, 7, -1):
                with self.assertRaises(ValueError):
                    await self.device.write_rgb(0, 255, 0, state)
        self.assertEqual(self.client.writes, [])

    async def test_mk2_modes_use_hardware_verified_effect_commands(self):
        for state in RGBState:
            with self.subTest(state=state):
                self.client.writes.clear()
                await self.device.write_rgb(0, 255, 0, state)
                expected = [bytes.fromhex('FE 33 00 00 00 00 00 EF'),
                            bytes([0xFE, 0x1E, 1, 0, 255, 0,
                                   state if state <= 3 else 0, 0xEF])]
                if state != RGBState.STATIC:
                    expected.append(bytes([0xFE, 0x33, 1, 0, 255, 0, state, 0xEF]))
                self.assertEqual(self.client.writes, expected)

    async def test_mk2_effect_to_static_and_off_clears_animation(self):
        await self.device.write_rgb(0, 0, 255, RGBState.COLORFUL)
        self.client.writes.clear()
        await self.device.write_rgb(255, 0, 0, RGBState.STATIC)
        await self.device.write_rgb_off()
        self.assertEqual(self.client.writes, [bytes.fromhex(packet) for packet in (
            'FE 33 00 00 00 00 00 EF', 'FE 1E 01 FF 00 00 00 EF',
            'FE 33 00 00 00 00 00 EF', 'FE 1E 00 00 00 00 00 EF')])

    async def test_override_disable_failure_does_not_send_hidden_rgb_update(self):
        self.client.write_gatt_char = AsyncMock(side_effect=RuntimeError('write failed'))
        for operation in (lambda: self.device.write_rgb(255, 0, 0, RGBState.STATIC),
                          self.device.write_rgb_off):
            self.client.write_gatt_char.reset_mock()
            with self.assertRaisesRegex(RuntimeError, 'write failed'):
                await operation()
            self.client.write_gatt_char.assert_awaited_once_with(
                NordicUART.CHAR_TX, bytearray.fromhex('FE 33 00 00 00 00 00 EF'))

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
        self.assertEqual(self.device.flow_status, 'starting')

    async def test_startup_grace_delays_fault_and_expires_without_another_packet(self):
        await self.device.write_pump_mode()
        self.device._notification(None, bytes.fromhex('FE 31 05 01 EF'))
        self.assertEqual(self.device.flow_status, 'starting')
        self.device._finish_flow_startup()
        self.assertEqual(self.device.flow_status, 'fault')

    async def test_startup_success_ends_grace_immediately(self):
        await self.device.write_pump_mode()
        self.device._notification(None, bytes.fromhex('FE 31 05 02 EF'))
        self.assertEqual(self.device.flow_status, 'OK')
        self.assertIsNone(self.device._flow_start_timer)
        self.device._notification(None, bytes.fromhex('FE 31 05 03 EF'))
        self.assertEqual(self.device.flow_status, 'fault')

    async def test_startup_without_response_stays_unknown_after_grace(self):
        await self.device.write_pump_mode()
        self.device._finish_flow_startup()
        self.assertEqual(self.device.flow_status, 'unknown')

    async def test_repeated_pump_writes_do_not_extend_grace(self):
        await self.device.write_pump_mode()
        deadline = self.device._flow_start_deadline
        timer = self.device._flow_start_timer
        await self.device.write_pump_mode(pump_voltage=PumpVoltage.V8)
        self.assertEqual(self.device._flow_start_deadline, deadline)
        self.assertIs(self.device._flow_start_timer, timer)

    async def test_sleep_cancels_startup_grace(self):
        await self.device.write_pump_mode()
        timer = self.device._flow_start_timer
        await self.device.write_sleep()
        self.assertTrue(timer.cancelled())
        self.assertFalse(self.device.pump_running)
        self.assertEqual(self.device.flow_status, 'unknown')

    async def test_tested_mk2_disconnect_sends_no_sleep(self):
        self.device.firmware_version = 'MCU F/W Version: 2.0.0.4'
        await self.device.disconnect()
        self.assertEqual(self.client.writes, [])
        self.assertFalse(self.client.is_connected)

    async def test_unverified_devices_keep_sleep_before_disconnect(self):
        for model, firmware in (('LCT21001', 'MCU F/W Version: 2.0.0.4'),
                                ('LCT22002', None), ('LCT22002', 'MCU F/W Version: 2.0.0.5')):
            with self.subTest(model=model, firmware=firmware):
                client = FakeClient()
                client.is_connected = True
                device = WaterCoolingDevice()
                device.client = client
                device.connected_model = model
                device.firmware_version = firmware
                await device.disconnect()
                self.assertEqual(client.writes, [bytes.fromhex('FE 19 00 01 00 00 00 EF')])

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

    async def test_lct22002_captured_firmware_response(self):
        # Captured from an LCT22002 running firmware 2.0.0.4.
        await self.connect_fake(b'MCU F/W Version: 2.0.0.4')
        self.assertEqual(self.device.firmware_version, 'MCU F/W Version: 2.0.0.4')
        self.assertTrue(self.device._firmware_received.is_set())

    async def test_lct22002_captured_compact_meter_responses(self):
        await self.device.write_pump_mode()
        for packet, expected in (
            ('FE 31 05 02 EF', 'OK'),
            ('FE 31 05 01 EF', 'fault'),
            ('FE 32 05 02 EF', 'OK'),
            ('FE 32 05 01 EF', 'fault'),
        ):
            with self.subTest(packet=packet):
                self.device._meter_received.clear()
                self.device._notification(None, bytes.fromhex(packet))
                self.assertEqual(self.device.flow_status, expected)
                self.assertTrue(self.device._meter_received.is_set())
        await self.device.write_pump_off()
        self.device._notification(None, bytes.fromhex('FE 32 05 01 EF'))
        self.assertEqual(self.device.flow_status, 'unknown')

    async def test_malformed_compact_responses_and_firmware_are_ignored(self):
        self.device.pump_running = True
        for data in (
            bytes.fromhex('FE 31 05 02 00'),
            bytes.fromhex('FE 33 05 02 EF'),
            bytes.fromhex('FE 31 05 EF'),
            bytes.fromhex('FE 31 05 02 00 EF'),
            b'MCU F/W Version: ', b'MCU F/W Version: telemetry',
            b'MCU F/W Version: 2.0.0.4\x01',
        ):
            self.device._notification(None, data)
        self.assertEqual(self.device.flow_status, 'unknown')
        self.assertFalse(self.device._meter_received.is_set())
        self.assertIsNone(self.device.firmware_version)

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

    async def test_standby_preserves_settings_and_resume_restores_effects(self):
        self.app.settings.rgb_state = RGBState.COLORFUL
        self.app.settings.rgb_color = (0, 0, 255)
        self.app.settings.fan_is_off = True
        before = vars(self.app.settings).copy()
        self.app.tray.update_connection_status(True)
        await self.app.set_standby(True)
        self.assertTrue(self.app.tray.standby)
        self.assertTrue(self.client.is_connected)
        self.assertEqual(self.client.writes, [bytes.fromhex('FE 19 00 01 00 00 00 EF')])
        self.assertEqual(vars(self.app.settings), before)
        menu = {item.text: item for item in self.app.tray.create_menu()}
        self.assertTrue(menu['Resume'].enabled)
        self.assertFalse(menu['RGB'].enabled)
        self.assertFalse(menu['Pump'].enabled)
        self.client.writes.clear()
        await self.app.set_standby(False)
        self.assertFalse(self.app.tray.standby)
        self.assertEqual(self.client.writes, [bytes.fromhex(p) for p in (
            'FE 1C 01 3C 02 00 00 EF', 'FE 1B 00 00 00 00 00 EF',
            'FE 33 00 00 00 00 00 EF', 'FE 1E 01 00 00 FF 02 EF',
            'FE 33 01 00 00 FF 02 EF')])
        self.assertEqual(vars(self.app.settings), before)
        self.app.settings.save.assert_not_called()

    async def test_failed_standby_does_not_claim_outputs_are_off(self):
        self.app.device.write_sleep = AsyncMock(side_effect=RuntimeError('sleep failed'))
        with self.assertRaisesRegex(RuntimeError, 'sleep failed'):
            await self.app.set_standby(True)
        self.assertFalse(self.app.tray.standby)
        self.assertFalse(self.app.tray.busy)

    async def test_failed_resume_returns_to_sleep(self):
        await self.app.set_standby(True)
        self.app.device.write_fan_mode = AsyncMock(side_effect=RuntimeError('fan failed'))
        with self.assertRaisesRegex(RuntimeError, 'Could not restore'):
            await self.app.set_standby(False)
        self.assertTrue(self.app.tray.standby)
        self.assertFalse(self.app.tray.busy)
        self.assertFalse(self.app.device.pump_running)
        self.assertEqual(self.client.writes[-1], bytes.fromhex('FE 19 00 01 00 00 00 EF'))

    async def test_standby_blocks_priming_and_settings_changes(self):
        await self.app.set_standby(True)
        self.client.writes.clear()
        await self.app.start_priming()
        self.assertIsNone(self.app._priming_task)
        tasks = []
        self.app._submit = lambda coro: tasks.append(asyncio.create_task(coro))
        original_color = self.app.settings.rgb_color
        self.app._change_settings(rgb_color=(0, 255, 0))
        await asyncio.gather(*tasks)
        self.assertEqual(self.app.settings.rgb_color, original_color)
        self.assertEqual(self.client.writes, [])

    async def test_disconnect_clears_standby(self):
        self.app.device.firmware_version = 'MCU F/W Version: 2.0.0.4'
        await self.app.set_standby(True)
        self.client.writes.clear()
        await self.app.disconnect()
        self.assertFalse(self.app.tray.standby)
        self.assertFalse(self.app.tray.connected)
        self.assertEqual(self.client.writes, [])

    async def test_restore_all_off_states(self):
        settings = self.app.settings
        settings.pump_is_off = settings.fan_is_off = settings.rgb_is_off = True
        await self.app.apply_current_settings()
        self.assertEqual(self.client.writes, [bytes.fromhex(p) for p in (
            'FE 1C 00 00 00 00 00 EF', 'FE 1B 00 00 00 00 00 EF',
            'FE 33 00 00 00 00 00 EF', 'FE 1E 00 00 00 00 00 EF')])

    async def test_restore_disables_mk2_override_before_saved_rgb(self):
        await self.app.apply_current_settings()
        self.assertEqual(self.client.writes[-2:], [
            bytes.fromhex('FE 33 00 00 00 00 00 EF'),
            bytes.fromhex('FE 1E 01 FF 00 00 00 EF')])

    async def test_restore_reenables_saved_mk2_animation(self):
        for state in list(RGBState)[1:]:
            with self.subTest(state=state):
                self.client.writes.clear()
                self.app.settings.rgb_color = (0, 0, 255)
                self.app.settings.rgb_state = state
                await self.app.apply_current_settings()
                self.assertEqual(self.client.writes[-3:], [
                    bytes.fromhex('FE 33 00 00 00 00 00 EF'),
                    bytes([0xFE, 0x1E, 1, 0, 0, 255, state if state <= 3 else 0, 0xEF]),
                    bytes([0xFE, 0x33, 1, 0, 0, 255, state, 0xEF])])

    async def test_saved_mk2_effect_survives_mk1_fallback(self):
        for state in list(RGBState)[4:]:
            self.app.settings.rgb_state = state
            self.app.device.connected_model = 'LCT21001'
            self.client.writes.clear()
            await self.app.apply_current_settings()
            self.assertEqual(self.client.writes[-1], bytes.fromhex('FE 1E 01 FF 00 00 00 EF'))
            self.assertNotIn(0x33, [p[1] for p in self.client.writes])
            self.assertEqual(self.app.settings.rgb_state, state)
            self.app.device.connected_model = 'LCT22002'
            await self.app.apply_current_settings()
            self.assertEqual(self.client.writes[-1], bytes([0xFE, 0x33, 1, 255, 0, 0, state, 0xEF]))

    async def test_single_rgb_menu_effect_availability_and_color(self):
        rgb = {item.text: item for item in self.app.handle_rgb_settings()}
        modes = {item.text: item for item in rgb['Mode'].submenu}
        self.assertEqual(list(modes), ['Static', 'Breathe', 'Rainbow', 'Breathe Rainbow',
                                      'Spiral', 'Rotating Rainbow', 'Fast Color Wave'])
        for state, label in ((RGBState.SPIRAL, 'Spiral'),
                             (RGBState.ROTATING_RAINBOW, 'Rotating Rainbow'),
                             (RGBState.FAST_COLOR_WAVE, 'Fast Color Wave')):
            self.app.settings.rgb_state = state
            self.app.device.connected_model = 'LCT22002'
            self.assertTrue(modes[label].enabled)
            self.assertTrue(modes[label].checked)
            self.assertFalse(rgb['Color'].enabled)
            self.app.device.connected_model = 'LCT21001'
            self.assertFalse(modes[label].enabled)
            self.assertFalse(modes[label].checked)
            self.assertTrue(modes['Static'].checked)
            self.assertTrue(rgb['Color'].enabled)
        self.app.settings.rgb_state = RGBState.BREATHE
        self.assertTrue(rgb['Color'].enabled)

    async def test_restore_attempts_other_outputs_after_failure(self):
        self.app.device.write_pump_mode = AsyncMock(side_effect=RuntimeError('pump failed'))
        with self.assertRaisesRegex(RuntimeError, 'Could not restore'):
            await self.app.apply_current_settings()
        self.assertEqual([p[1] for p in self.client.writes], [0x1B, 0x33, 0x1E])

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
        self.assertEqual(commands[-5:], [0x1C, 0x1B, 0x33, 0x1E, 0x19])

    async def test_menus_construct_with_real_pystray(self):
        items = self.app.tray.create_menu()
        self.assertEqual([item.text for item in items if 'RGB' in item.text], ['RGB'])
        self.app.tray.update_device_status('CoolingSystem FW V2', 'OK')
        self.app.tray.update_connection_status(True)
        rgb = next(item for item in self.app.tray.create_menu() if item.text == 'RGB')
        self.assertTrue(rgb.enabled)
        self.app.tray.priming = True
        self.assertFalse(rgb.enabled)

    async def test_captured_firmware_response_reaches_tray_menu(self):
        self.app.device._notification(None, b'MCU F/W Version: 2.0.0.4')
        self.assertIn('Firmware: MCU F/W Version: 2.0.0.4',
                      [item.text for item in self.app.tray.create_menu()])

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
    def test_json_migrates_legacy_fan_rgb_without_changing_rgb(self):
        with patch.object(Settings, 'load'):
            settings = Settings()
            restored = Settings()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            settings.CONFIG_FILE = restored.CONFIG_FILE = str(path)
            settings.rgb_color = (1, 2, 3)
            settings.rgb_state = RGBState.BREATHE
            settings.rgb_is_off = True
            settings._save_to_file()
            config = json.loads(path.read_text())
            config['fan_rgb'] = dict(enabled=True, off=False, color=[255, 0, 0], state=1)
            path.write_text(json.dumps(config))
            restored._load_from_file()
            self.assertEqual(restored.rgb_color, (1, 2, 3))
            self.assertEqual(restored.rgb_state, RGBState.BREATHE)
            self.assertTrue(restored.rgb_is_off)
            self.assertFalse(hasattr(restored, 'fan_rgb_enabled'))
            restored._save_to_file()
            self.assertNotIn('fan_rgb', json.loads(path.read_text()))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows registry storage')
    def test_registry_removes_legacy_fan_rgb_when_saving(self):
        with patch.object(Settings, 'load'):
            settings = Settings()
        import winreg
        values = dict(current_voltage=2, current_fan_speed=50, pump_is_off=0,
                      fan_is_off=0, rgb_state=1, rgb_is_off=1, rgb_color=bytes([1, 2, 3]),
                      auto_start=0, auto_connect=0,
                      fan_rgb='{"enabled": true, "off": false, "state": 1}')
        def query(key, name):
            return values[name], 0
        def write(key, name, reserved, kind, value):
            values[name] = value
        def delete(key, name):
            if name not in values:
                raise FileNotFoundError(name)
            del values[name]
        with patch.object(winreg, 'CreateKey'), patch.object(winreg, 'CloseKey'), \
                patch.object(winreg, 'QueryValueEx', side_effect=query), \
                patch.object(winreg, 'SetValueEx', side_effect=write), \
                patch.object(winreg, 'DeleteValue', side_effect=delete):
            settings._load_from_registry()
            self.assertEqual(settings.rgb_color, (1, 2, 3))
            self.assertTrue(settings.rgb_is_off)
            self.assertFalse(hasattr(settings, 'fan_rgb_enabled'))
            settings._save_to_registry()
            self.assertNotIn('fan_rgb', values)
            self.assertEqual(values['rgb_color'], bytes([1, 2, 3]))
            self.assertEqual(values['rgb_state'], 1)
            self.assertEqual(values['rgb_is_off'], 1)
            settings._save_to_registry()  # Missing obsolete value is harmless.


if __name__ == '__main__':
    unittest.main()
