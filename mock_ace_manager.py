"""
Mock ACE manager for UI development without hardware.

This intentionally mirrors the ACEManager public surface while keeping all
actions in memory. It is enabled only by the foreground run scripts.
"""

import asyncio
import time
from copy import deepcopy

ACE_PRO_MODEL = "ace_pro"
ACE_2_PRO_MODEL = "ace_2_pro"


class MockACEManager:
    def __init__(self, config: dict):
        self.config = config
        self._callbacks = []
        self._tick_task: asyncio.Task | None = None
        model = config.get("device_model", "auto")
        if model not in (ACE_PRO_MODEL, ACE_2_PRO_MODEL):
            model = ACE_2_PRO_MODEL
        self._model = model
        self._status = self._initial_status()

    def add_event_callback(self, cb):
        self._callbacks.append(cb)

    async def start(self):
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def stop(self):
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass

    def get_all_status(self) -> dict:
        return {0: deepcopy(self._status)}

    async def load_slot(self, device_index: int, slot: int) -> dict:
        self._require_device(device_index)
        self._require_slot(slot)
        self._status["slots"][slot]["status"] = "LOADED"
        await self._emit("status_update")
        return {"ok": True, "mock": True, "action": "load_slot", "slot": slot}

    async def unload_slot(self, device_index: int, slot: int) -> dict:
        self._require_device(device_index)
        self._require_slot(slot)
        self._status["slots"][slot]["status"] = "EMPTY"
        await self._emit("status_update")
        return {"ok": True, "mock": True, "action": "unload_slot", "slot": slot}

    async def load_all(self, device_index: int) -> dict:
        self._require_device(device_index)
        for slot in self._status["slots"]:
            if slot["filament_type"]:
                slot["status"] = "LOADED"
        await self._emit("status_update")
        return {"ok": True, "mock": True, "action": "load_all"}

    async def unload_all(self, device_index: int) -> dict:
        self._require_device(device_index)
        for slot in self._status["slots"]:
            slot["status"] = "EMPTY"
        await self._emit("status_update")
        return {"ok": True, "mock": True, "action": "unload_all"}

    async def feed(self, device_index: int, slot: int, speed: int | None = None) -> dict:
        self._require_device(device_index)
        self._require_slot(slot)
        self._status["slots"][slot]["status"] = "FEEDING"
        self._status["feed_assist_active"] = True
        await self._emit("status_update")
        return {"ok": True, "mock": True, "action": "feed", "slot": slot, "speed": speed}

    async def retract(self, device_index: int, slot: int, speed: int | None = None) -> dict:
        self._require_device(device_index)
        self._require_slot(slot)
        self._status["slots"][slot]["status"] = "RETRACTING"
        self._status["feed_assist_active"] = True
        await self._emit("status_update")
        return {"ok": True, "mock": True, "action": "retract", "slot": slot, "speed": speed}

    async def start_dryer(self, device_index: int, temp_c: int, duration_min: int) -> dict:
        self._require_device(device_index)
        self._status["dryer_active"] = True
        self._status["dryer_target_temp"] = temp_c
        self._status["dryer_temp"] = max(28, min(temp_c - 3, temp_c))
        self._status["dryer_duration_remaining"] = max(0, duration_min) * 60
        await self._emit("status_update")
        return {"ok": True, "mock": True, "action": "dryer_start", "temp_c": temp_c, "duration_min": duration_min}

    async def stop_dryer(self, device_index: int) -> dict:
        self._require_device(device_index)
        self._status["dryer_active"] = False
        self._status["dryer_target_temp"] = 0
        self._status["dryer_duration_remaining"] = 0
        await self._emit("status_update")
        return {"ok": True, "mock": True, "action": "dryer_stop"}

    async def get_rfid(self, device_index: int, slot: int) -> dict:
        self._require_device(device_index)
        self._require_slot(slot)
        slot_info = self._status["slots"][slot]
        return {
            "ok": True,
            "mock": True,
            "slot": slot,
            "rfid_present": slot_info["rfid_present"],
            "rfid_data": slot_info["rfid_data"],
        }

    async def release_serial(self):
        pass

    async def reconnect(self):
        pass

    async def _tick_loop(self):
        while True:
            await asyncio.sleep(3)
            self._status["last_seen"] = time.time()
            if self._status["dryer_active"]:
                target = self._status["dryer_target_temp"]
                if self._status["dryer_temp"] < target:
                    self._status["dryer_temp"] += 1
                if self._status["dryer_duration_remaining"] > 0:
                    self._status["dryer_duration_remaining"] -= 3
            for slot in self._status["slots"]:
                if slot["status"] in ("FEEDING", "RETRACTING"):
                    slot["status"] = "READY" if slot["filament_type"] else "EMPTY"
                    self._status["feed_assist_active"] = False
            await self._emit("status_update")

    async def _emit(self, event: str):
        payload = {"event": event, "device_index": 0, "data": deepcopy(self._status)}
        for cb in self._callbacks:
            await cb(payload)

    def _require_slot(self, slot: int):
        if slot < 0 or slot >= len(self._status["slots"]):
            raise ValueError(f"Slot {slot} not found")

    def _require_device(self, device_index: int):
        if device_index != 0:
            raise ValueError("Mock mode currently supports one ACE at device index 0")

    def _initial_status(self) -> dict:
        now = time.time()
        if self._model == ACE_PRO_MODEL:
            return self._ace_pro_status(now)
        return self._ace_2_pro_status(now)

    @staticmethod
    def _ace_pro_status(now: float) -> dict:
        return {
            "device_index": 0,
            "connected": True,
            "model": "Anycubic ACE Pro",
            "protocol": "json",
            "device_model": "ace_pro",
            "port": "MOCK-ACE1",
            "firmware_version": "V2.1.4-mock",
            "slots": [
                {
                    "index": 0,
                    "status": "READY",
                    "filament_type": "PLA+",
                    "color": "Army Green",
                    "color_hex": "4a5a3a",
                    "brand": "Anycubic",
                    "rfid_present": True,
                    "rfid_data": {"sku": "MOCK-GRN-PLA+", "diameter": 1.75, "remaining": 95},
                },
                {
                    "index": 1,
                    "status": "UNWINDING",
                    "filament_type": "PLA",
                    "color": "Sky Blue",
                    "color_hex": "5b9ecf",
                    "brand": "Anycubic",
                    "rfid_present": True,
                    "rfid_data": {"sku": "MOCK-BLU-PLA", "diameter": 1.75, "remaining": 44},
                },
                {
                    "index": 2,
                    "status": "TANGLED",
                    "filament_type": "",
                    "color": "",
                    "color_hex": "",
                    "brand": "",
                    "rfid_present": False,
                    "rfid_data": {},
                },
                {
                    "index": 3,
                    "status": "EMPTY",
                    "filament_type": "",
                    "color": "",
                    "color_hex": "",
                    "brand": "",
                    "rfid_present": False,
                    "rfid_data": {},
                },
            ],
            "dryer_active": False,
            "dryer_temp": 26,
            "dryer_target_temp": 0,
            "dryer_duration_remaining": 0,
            "feed_assist_active": False,
            "last_seen": now,
            "error": "",
        }

    @staticmethod
    def _ace_2_pro_status(now: float) -> dict:
        return {
            "device_index": 0,
            "connected": True,
            "model": "Anycubic ACE 2 Pro",
            "protocol": "protobuf",
            "device_model": "ace_2_pro",
            "port": "MOCK-ACE2",
            "firmware_version": "V1.1.31-mock",
            "slots": [
                {
                    "index": 0,
                    "status": "READY",
                    "filament_type": "PLA",
                    "color": "Obsidian Black",
                    "color_hex": "111111",
                    "brand": "Anycubic",
                    "rfid_present": True,
                    "rfid_data": {"sku": "MOCK-BLK-PLA", "diameter": 1.75, "remaining": 82},
                },
                {
                    "index": 1,
                    "status": "FEEDING",
                    "filament_type": "PETG",
                    "color": "Signal White",
                    "color_hex": "f2f0e8",
                    "brand": "Anycubic",
                    "rfid_present": True,
                    "rfid_data": {"sku": "MOCK-WHT-PETG", "diameter": 1.75, "remaining": 61},
                },
                {
                    "index": 2,
                    "status": "STUCK",
                    "filament_type": "",
                    "color": "",
                    "color_hex": "",
                    "brand": "",
                    "rfid_present": False,
                    "rfid_data": {},
                },
                {
                    "index": 3,
                    "status": "EMPTY",
                    "filament_type": "",
                    "color": "",
                    "color_hex": "",
                    "brand": "",
                    "rfid_present": False,
                    "rfid_data": {},
                },
            ],
            "dryer_active": False,
            "dryer_temp": 28,
            "dryer_target_temp": 0,
            "dryer_duration_remaining": 0,
            "feed_assist_active": False,
            "last_seen": now,
            "error": "",
        }
