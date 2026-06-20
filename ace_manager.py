"""
Unified ACE manager for ACE Pro (JSON) and ACE 2 Pro (protobuf).

Supports auto-detection, real hardware control, and mock simulation.
"""

import asyncio
import logging
import time
from copy import deepcopy
from typing import Any

import serial

from ace_protocol import ACE_PRO_BAUD, build_request as ace_pro_build, parse_response
from ace2_protocol import (
    ACE2_BAUD,
    ACE2Command,
    build_packet,
    decode_discover,
    decode_info,
    decode_status,
    decode_temp,
    decode_generic,
    decode_filament_info,
    parse_packet,
    pb_uint32,
    pb_bool,
    FEED_MODE_FEED,
    FEED_MODE_ROLLBACK,
)

logger = logging.getLogger("acelink")

ACE_PRO = "ace_pro"
ACE_2_PRO = "ace_2_pro"
ACE_AUTO = "auto"

MODEL_INFO = {
    ACE_PRO: {
        "display_name": "Anycubic ACE Pro",
        "protocol": "json",
        "baud": ACE_PRO_BAUD,
    },
    ACE_2_PRO: {
        "display_name": "Anycubic ACE 2 Pro",
        "protocol": "protobuf",
        "baud": ACE2_BAUD,
    },
}


class ACEManager:
    def __init__(self, config: dict):
        self.config = config
        self.device_model = config.get("device_model", ACE_AUTO)
        if self.device_model not in (ACE_AUTO, ACE_PRO, ACE_2_PRO):
            self.device_model = ACE_AUTO
        self._callbacks: list = []
        self._status = self._initial_status()
        self._serial: serial.Serial | None = None
        self._model: str | None = None
        self._read_buffer = bytearray()
        self._seq = 0
        self._request_id = 0
        self._poll_task: asyncio.Task | None = None
        self._running = False

    # ── Public API (matches MockACEManager) ──────────────────────────────────

    def add_event_callback(self, cb):
        self._callbacks.append(cb)

    async def start(self):
        await self._connect()
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._disconnect()

    def get_all_status(self) -> dict:
        if not self.config.get("serial_port") and not self._status.get("port"):
            return {}
        return {0: deepcopy(self._status)}

    async def load_slot(self, device_index: int, slot: int) -> dict:
        self._require_device(device_index)
        self._require_slot(slot)
        self._check_connected()
        length = self._slot_config(slot, "load_length", 2100)
        speed = self._slot_config(slot, "feed_speed", 80)
        payload = (
            pb_uint32(1, slot)
            + pb_uint32(2, speed)
            + pb_uint32(3, length)
            + pb_uint32(4, FEED_MODE_FEED)
        )
        result = await asyncio.to_thread(self._send_recv_sync, ACE2Command.FEED_OR_ROLLBACK, payload)
        self._status["slots"][slot]["status"] = "LOADING"
        await self._emit("status_update")
        return {"ok": True, "action": "load_slot", "slot": slot, "response": result}

    async def unload_slot(self, device_index: int, slot: int) -> dict:
        self._require_device(device_index)
        self._require_slot(slot)
        self._check_connected()
        length = self._slot_config(slot, "retract_length", 1950)
        speed = self._slot_config(slot, "retract_speed", 30)
        payload = (
            pb_uint32(1, slot)
            + pb_uint32(2, speed)
            + pb_uint32(3, length)
            + pb_uint32(4, FEED_MODE_ROLLBACK)
        )
        result = await asyncio.to_thread(self._send_recv_sync, ACE2Command.FEED_OR_ROLLBACK, payload)
        self._status["slots"][slot]["status"] = "UNLOADING"
        await self._emit("status_update")
        return {"ok": True, "action": "unload_slot", "slot": slot, "response": result}

    async def load_all(self, device_index: int) -> dict:
        self._require_device(device_index)
        results = {}
        for slot in range(4):
            results[slot] = await self.load_slot(device_index, slot)
        return {"ok": True, "action": "load_all", "results": results}

    async def unload_all(self, device_index: int) -> dict:
        self._require_device(device_index)
        results = {}
        for slot in range(4):
            results[slot] = await self.unload_slot(device_index, slot)
        return {"ok": True, "action": "unload_all", "results": results}

    async def feed(self, device_index: int, slot: int, speed: int | None = None) -> dict:
        self._require_device(device_index)
        self._require_slot(slot)
        self._check_connected()
        effective_speed = speed or self._slot_config(slot, "feed_speed", 80)
        length = self._slot_config(slot, "load_length", 2100)
        payload = (
            pb_uint32(1, slot)
            + pb_uint32(2, effective_speed)
            + pb_uint32(3, length)
            + pb_uint32(4, FEED_MODE_FEED)
        )
        result = await asyncio.to_thread(self._send_recv_sync, ACE2Command.FEED_OR_ROLLBACK, payload)
        self._status["slots"][slot]["status"] = "FEEDING"
        await self._emit("status_update")
        return {"ok": True, "action": "feed", "slot": slot, "speed": effective_speed, "response": result}

    async def retract(self, device_index: int, slot: int, speed: int | None = None) -> dict:
        self._require_device(device_index)
        self._require_slot(slot)
        self._check_connected()
        effective_speed = speed or self._slot_config(slot, "retract_speed", 30)
        length = self._slot_config(slot, "retract_length", 1950)
        payload = (
            pb_uint32(1, slot)
            + pb_uint32(2, effective_speed)
            + pb_uint32(3, length)
            + pb_uint32(4, FEED_MODE_ROLLBACK)
        )
        result = await asyncio.to_thread(self._send_recv_sync, ACE2Command.FEED_OR_ROLLBACK, payload)
        self._status["slots"][slot]["status"] = "RETRACTING"
        await self._emit("status_update")
        return {"ok": True, "action": "retract", "slot": slot, "speed": effective_speed, "response": result}

    async def start_dryer(self, device_index: int, temp_c: int, duration_min: int) -> dict:
        self._require_device(device_index)
        self._check_connected()
        payload = (
            pb_uint32(1, temp_c)
            + pb_uint32(2, duration_min)
            + pb_bool(3, True)
        )
        result = await asyncio.to_thread(self._send_recv_sync, ACE2Command.DRYING, payload)
        await self._emit("status_update")
        return {"ok": True, "action": "dryer_start", "temp_c": temp_c, "duration_min": duration_min, "response": result}

    async def stop_dryer(self, device_index: int) -> dict:
        self._require_device(device_index)
        self._check_connected()
        payload = pb_uint32(1, 0) + pb_uint32(2, 0)
        result = await asyncio.to_thread(self._send_recv_sync, ACE2Command.DRYING, payload)
        await self._emit("status_update")
        return {"ok": True, "action": "dryer_stop", "response": result}

    async def get_rfid(self, device_index: int, slot: int) -> dict:
        self._require_device(device_index)
        self._require_slot(slot)
        self._check_connected()
        payload = pb_uint32(1, slot)
        result = await asyncio.to_thread(self._send_recv_sync, ACE2Command.GET_FILAMENT_INFO, payload)
        if result:
            fw = result.get("firmware_version", "")
            if fw:
                self._status["firmware_version"] = fw
            slot_info = result.get("slot") or result.get("slots", [{}])[0] if result.get("slots") else {}
            if slot_info:
                s = self._status["slots"][slot]
                s["filament_type"] = slot_info.get("type", s["filament_type"])
                s["brand"] = slot_info.get("brand", s["brand"])
                color = slot_info.get("color")
                if isinstance(color, (list, tuple)) and len(color) >= 3:
                    s["color_hex"] = "#{:02x}{:02x}{:02x}".format(*color[:3])
                s["rfid_data"] = result
            await self._emit("status_update")
        return {"ok": True, "action": "rfid", "slot": slot, "rfid_present": True, "rfid_data": result or {}}

    async def release_serial(self):
        self._disconnect()

    async def reconnect(self):
        import asyncio as _asyncio
        for _ in range(3):
            try:
                await self._connect()
                return
            except Exception:
                await _asyncio.sleep(0.3)
        await self._connect()

    # ── Connection ───────────────────────────────────────────────────────────

    async def _connect(self):
        port = self.config.get("serial_port", "")
        if not port:
            port = await self._find_ace_port()
        if not port:
            return

        baudrate = self._initial_baudrate()
        try:
            self._serial = await asyncio.to_thread(self._open_serial, port, baudrate)
        except Exception:
            detected = await self._find_ace_port()
            if detected and detected != port:
                logger.info("ACE: configured port %s not available, using detected %s", port, detected)
                port = detected
                self._serial = await asyncio.to_thread(self._open_serial, port, baudrate)
                self._status["port"] = port
                self.config["serial_port"] = port
                self._save_config_port(port)
            else:
                raise

        try:
            self._model = await self._detect_model()
            if self._model:
                if self._model != self.device_model and self.device_model not in (ACE_AUTO, ""):
                    logger.info("ACE: configured %s but detected %s", self.device_model, self._model)
                self.device_model = self._model
                info = MODEL_INFO[self._model]
                self._status["connected"] = True
                self._status["model"] = info["display_name"]
                self._status["protocol"] = info["protocol"]
                self._status["error"] = ""
                logger.info("ACE: connected to %s on %s @ %d baud (protocol %s)",
                            info["display_name"], port, baudrate, info["protocol"])
                if self._model == ACE_2_PRO:
                    check_payload = (
                        pb_uint32(1, self.config.get("feed_check_len", 254))
                        + pb_uint32(2, self.config.get("feed_check_error_len", 254))
                    )
                    await asyncio.to_thread(self._send_recv_sync, ACE2Command.SET_FEED_CHECK, check_payload)
                await self._emit("status_update")
            else:
                self._status["error"] = "Device detected but model unknown. Check baud rate and wiring."
                await self._emit("status_update")
        except Exception as exc:
            self._status["error"] = f"Connection failed: {exc}"
            await self._emit("status_update")

    def _save_config_port(self, port: str):
        try:
            import json
            from acelink_config import CONFIG_PATH
            if CONFIG_PATH and CONFIG_PATH.exists():
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                data["serial_port"] = port
                CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _open_serial(self, port: str, baudrate: int) -> serial.Serial:
        is_v2 = baudrate == ACE2_BAUD
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            exclusive=True,
            rtscts=not is_v2,
            timeout=0.1 if is_v2 else 0,
            write_timeout=1.0 if is_v2 else 0,
        )
        return ser

    async def _find_ace_port(self) -> str | None:
        import serial.tools.list_ports
        def _scan():
            for p in serial.tools.list_ports.comports():
                hwid = (p.hwid or '').lower()
                desc = (p.description or '').lower()
                mfr = (p.manufacturer or '').lower()
                if '1a86' in hwid or 'ch340' in desc or 'wch' in mfr:
                    return p.device
            return None
        return await asyncio.to_thread(_scan)

    async def _detect_model(self) -> str | None:
        baudrate = self._serial.baudrate

        def try_ace2():
            info = self._send_recv_sync(ACE2Command.GET_INFO, b"")
            if info:
                return ACE_2_PRO
            return None

        def try_ace_pro():
            response = self._send_json_sync("get_info")
            if response and "result" in response:
                return ACE_PRO
            return None

        async def try_with_retries(detect_fn, model_name, max_retries=1):
            import asyncio as _asyncio
            for attempt in range(max_retries):
                result = await _asyncio.to_thread(detect_fn)
                if result:
                    return result
                if attempt < max_retries - 1:
                    await _asyncio.sleep(0.5)
            return None

        if self.device_model == ACE_2_PRO:
            self._serial.baudrate = ACE2_BAUD
            result = await try_with_retries(try_ace2, "ACE 2 Pro")
            if result:
                return result
            logger.info("ACE: forced ACE 2 Pro probe failed, trying ACE Pro fallback")
            self._serial.baudrate = ACE_PRO_BAUD
            self._serial.rtscts = True
            return await try_with_retries(try_ace_pro, "ACE Pro")

        if self.device_model == ACE_PRO:
            self._serial.baudrate = ACE_PRO_BAUD
            result = await try_with_retries(try_ace_pro, "ACE Pro")
            if result:
                return result
            logger.info("ACE: forced ACE Pro probe failed, trying ACE 2 Pro fallback")
            self._serial.baudrate = ACE2_BAUD
            self._serial.rtscts = False
            self._serial.reset_input_buffer()
            return await try_with_retries(try_ace2, "ACE 2 Pro")

        if baudrate == ACE2_BAUD:
            result = await try_with_retries(try_ace2, "ACE 2 Pro")
            if result:
                return result
            logger.info("ACE: ACE 2 Pro probe failed, retrying as ACE Pro at %d baud", ACE_PRO_BAUD)
            self._serial.baudrate = ACE_PRO_BAUD
            self._serial.rtscts = True
            return await try_with_retries(try_ace_pro, "ACE Pro")

        if baudrate == ACE_PRO_BAUD:
            result = await try_with_retries(try_ace_pro, "ACE Pro")
            if result:
                return result
            logger.info("ACE: ACE Pro probe failed, retrying as ACE 2 Pro at %d baud", ACE2_BAUD)
            self._serial.baudrate = ACE2_BAUD
            self._serial.rtscts = False
            self._serial.reset_input_buffer()
            return await try_with_retries(try_ace2, "ACE 2 Pro")

        return None

    def _initial_baudrate(self) -> int:
        if self.device_model == ACE_PRO:
            return ACE_PRO_BAUD
        if self.device_model == ACE_2_PRO:
            return ACE2_BAUD
        configured = self.config.get("baudrate", ACE2_BAUD)
        return configured if configured in (ACE_PRO_BAUD, ACE2_BAUD) else ACE2_BAUD

    def _disconnect(self):
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None
        self._model = None
        self._status["connected"] = False
        self._status["model"] = ""
        self._status["protocol"] = ""

    # ── Polling ──────────────────────────────────────────────────────────────

    async def _poll_loop(self):
        while self._running:
            await asyncio.sleep(1)
            if not self._serial or not self._serial.is_open or not self._model:
                continue
            try:
                await self._poll_status()
                self._status["last_seen"] = time.time()
                await self._emit("status_update")
            except Exception:
                logger.info("ACE: poll error, reconnecting", exc_info=True)
                self._disconnect()
                await self._connect()

    async def _poll_status(self):
        if self._model == ACE_2_PRO:
            response = await asyncio.to_thread(self._send_recv_sync, ACE2Command.GET_STATUS, b"")
            if response:
                self._apply_v2_status(response)
                await self._poll_filament_info()
        else:
            response = await asyncio.to_thread(self._send_json_sync, "get_status")
            if response:
                self._apply_pro_status(response)

    async def _poll_filament_info(self):
        for i in range(4):
            slot = self._status["slots"][i]
            if slot["rfid_present"]:
                try:
                    payload = pb_uint32(1, i)
                    result = await asyncio.to_thread(
                        self._send_recv_sync, ACE2Command.GET_FILAMENT_INFO, payload
                    )
                    if result:
                        self._apply_filament_info(i, result)
                except Exception:
                    pass

    def _apply_filament_info(self, slot_index: int, data: dict):
        result = data.get("result", data)
        if not result:
            return
        slot = self._status["slots"][slot_index]
        if result.get("type"):
            slot["filament_type"] = result["type"]
        if result.get("brand"):
            slot["brand"] = result["brand"]
        color = result.get("color")
        if isinstance(color, (list, tuple)) and len(color) >= 3:
            slot["color"] = ", ".join(str(c) for c in color)
            slot["color_hex"] = "{:02x}{:02x}{:02x}".format(int(color[0]), int(color[1]), int(color[2]))

    def _apply_v2_status(self, decoded: dict):
        result = decoded.get("result", {})
        if not result:
            return
        slots = result.get("slots", [])
        for i in range(min(4, len(slots))):
            slot = slots[i]
            status = slot.get("status", "empty")
            self._status["slots"][i]["status"] = status.upper() if status else "EMPTY"
            rfid_val = slot.get("rfid", 0)
            self._status["slots"][i]["rfid_present"] = rfid_val > 0
            if rfid_val == 0:
                self._status["slots"][i]["filament_type"] = ""
                self._status["slots"][i]["color"] = ""
                self._status["slots"][i]["color_hex"] = ""
                self._status["slots"][i]["brand"] = ""

        dryer = result.get("dryer_status") or {}
        self._status["dryer_temp"] = result.get("temp", 0)
        self._status["dryer_active"] = dryer.get("status", "free") in ("starting", "keeping")
        self._status["dryer_target_temp"] = dryer.get("target_temp", 0)
        self._status["dryer_duration_remaining"] = dryer.get("remain_time", 0)

    def _apply_pro_status(self, response: dict):
        result = response.get("result") or {}
        if isinstance(result, str):
            result = {}
        slots = result.get("slots", result.get("fan_slots", []))
        for i in range(min(4, len(slots))):
            s = slots[i]
            if isinstance(s, dict):
                self._status["slots"][i]["status"] = str(s.get("status", "READY")).upper()
                self._status["slots"][i]["rfid_present"] = bool(s.get("rfid", False))

    # ── ACE 2 Pro serial I/O ─────────────────────────────────────────────────

    def _send_recv_sync(self, cmd: ACE2Command | int, payload: bytes = b"") -> dict | None:
        seq = self._next_seq()
        packet = build_packet(int(cmd), payload, seq=seq)
        self._serial.write(packet)
        self._serial.flush()

        buffer = bytearray()
        deadline = time.time() + 2.0
        while time.time() < deadline:
            waiting = self._serial.in_waiting
            if waiting:
                data = self._serial.read(waiting)
                buffer.extend(data)
                frame, consumed = parse_packet(buffer)
                if consumed:
                    del buffer[:consumed]
                if frame and frame.cmd == int(cmd) and frame.is_response:
                    decoder = {
                        ACE2Command.GET_STATUS: decode_status,
                        ACE2Command.GET_INFO: decode_info,
                        ACE2Command.GET_TEMP: decode_temp,
                        ACE2Command.DISCOVER_DEVICE: lambda p: decode_discover(p),
                        ACE2Command.FEED_OR_ROLLBACK: decode_generic,
                        ACE2Command.STOP_FEED_OR_ROLLBACK: decode_generic,
                        ACE2Command.DRYING: decode_generic,
                        ACE2Command.GET_FILAMENT_INFO: decode_filament_info,
                    }.get(int(cmd))
                    if decoder:
                        try:
                            return decoder(frame.payload)
                        except Exception:
                            return None
                    return None
            else:
                time.sleep(0.01)
        return None

    # ── ACE Pro serial I/O ───────────────────────────────────────────────────

    def _send_json_sync(self, method: str, params: dict[str, Any] | None = None) -> dict | None:
        req_id = self._next_request_id()
        packet = ace_pro_build(method, req_id, params)
        self._serial.write(packet)
        self._serial.flush()

        buffer = bytearray()
        deadline = time.time() + 2.0
        while time.time() < deadline:
            waiting = self._serial.in_waiting
            if waiting:
                data = self._serial.read(waiting)
                buffer.extend(data)
                response, consumed = parse_response(buffer)
                if response is not None:
                    return response
            else:
                time.sleep(0.01)
        return None

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _next_seq(self) -> int:
        self._seq = (self._seq % 0xFFFF) + 1
        if self._seq == 0:
            self._seq = 1
        return self._seq

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _require_device(self, device_index: int):
        if device_index != 0:
            raise ValueError("ACELink currently supports one ACE at device index 0")

    def _require_slot(self, slot: int):
        if not (0 <= slot <= 3):
            raise ValueError(f"Slot must be 0-3, got {slot}")

    def _check_connected(self):
        if not self._serial or not self._serial.is_open or not self._model:
            raise RuntimeError("ACE is not connected")
        if self._model not in (ACE_PRO, ACE_2_PRO):
            raise RuntimeError("Unknown ACE model")

    def _slot_config(self, slot: int, key: str, default: int) -> int:
        tuning = self.config.get("slot_tuning", [])
        if isinstance(tuning, list) and slot < len(tuning):
            val = (tuning[slot] or {}).get(key)
            if val is not None:
                return int(val)
        return int(self.config.get(key, default))

    async def _emit(self, event: str):
        if not self.config.get("serial_port"):
            return
        payload = {"event": event, "device_index": 0, "data": deepcopy(self._status)}
        for cb in self._callbacks:
            try:
                await cb(payload)
            except Exception:
                pass

    def _initial_status(self) -> dict:
        return {
            "device_index": 0,
            "connected": False,
            "model": "",
            "device_model": self.device_model,
            "protocol": "",
            "port": self.config.get("serial_port", ""),
            "firmware_version": "",
            "slots": [
                {
                    "index": i,
                    "status": "EMPTY",
                    "filament_type": "",
                    "color": "",
                    "color_hex": "",
                    "brand": "",
                    "rfid_present": False,
                    "rfid_data": {},
                }
                for i in range(4)
            ],
            "dryer_active": False,
            "dryer_temp": 0,
            "dryer_target_temp": 0,
            "dryer_duration_remaining": 0,
            "feed_assist_active": False,
            "last_seen": 0,
            "error": "",
        }
