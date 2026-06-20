"""
ACE Pro JSON serial protocol — CRC, framing, and read-only hardware probe.

Frame format: [FF AA][2-byte length][JSON payload][2-byte CRC][FE]
"""

from __future__ import annotations

import json
import struct
import time
from dataclasses import dataclass, field
from typing import Any

import serial

ACE_PRO_BAUD = 115200
PREAMBLE = b"\xff\xaa"
END_MARKER = 0xFE
DEFAULT_TIMEOUT = 1.5


@dataclass
class ProbeLog:
    direction: str
    method: str
    frame_hex: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "method": self.method,
            "frame_hex": self.frame_hex,
            "note": self.note,
        }


@dataclass
class ProbeResult:
    ok: bool
    port: str
    baudrate: int
    model: str = "Anycubic ACE Pro"
    protocol: str = "json"
    info: dict[str, Any] = field(default_factory=dict)
    status: dict[str, Any] = field(default_factory=dict)
    temp: dict[str, Any] = field(default_factory=dict)
    logs: list[ProbeLog] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "port": self.port,
            "baudrate": self.baudrate,
            "model": self.model,
            "protocol": self.protocol,
            "info": self.info,
            "status": self.status,
            "temp": self.temp,
            "logs": [entry.to_dict() for entry in self.logs],
            "error": self.error,
        }


def _calc_crc(buffer: bytes) -> int:
    crc = 0xFFFF
    for byte in buffer:
        data = byte
        data ^= crc & 0xFF
        data ^= (data & 0x0F) << 4
        crc = ((data << 8) | (crc >> 8)) ^ (data >> 4) ^ (data << 3)
    return crc & 0xFFFF


def build_request(method: str, request_id: int, params: dict[str, Any] | None = None) -> bytes:
    request = {"method": method, "id": request_id}
    if params:
        request["params"] = params
    payload = json.dumps(request).encode("utf-8")
    if len(payload) > 1024:
        raise ValueError("ACE Pro payload exceeds 1024 bytes")

    crc = _calc_crc(payload)
    attempts = 0
    while crc == 0xAAFF and attempts < 10:
        request_id += 1
        request["id"] = request_id
        payload = json.dumps(request).encode("utf-8")
        crc = _calc_crc(payload)
        attempts += 1

    return PREAMBLE + struct.pack("<H", len(payload)) + payload + struct.pack("<H", crc) + bytes([END_MARKER])


def parse_response(buffer: bytearray) -> tuple[dict[str, Any] | None, int]:
    while len(buffer) >= 7:
        start = buffer.find(PREAMBLE)
        if start < 0:
            del buffer[:-1]
            break
        if start > 0:
            del buffer[:start]
            continue

        if len(buffer) < 4:
            break
        payload_len = struct.unpack("<H", bytes(buffer[2:4]))[0]
        if payload_len > 2048:
            del buffer[:2]
            continue

        total_len = 4 + payload_len + 2 + 1
        if len(buffer) < total_len:
            break

        payload = bytes(buffer[4 : 4 + payload_len])
        received_crc = struct.unpack("<H", bytes(buffer[4 + payload_len : 6 + payload_len]))[0]
        if buffer[total_len - 1] != END_MARKER or received_crc != _calc_crc(payload):
            del buffer[:2]
            continue
        del buffer[:total_len]

        try:
            return json.loads(payload.decode("utf-8")), total_len
        except Exception:
            continue

    return None, 0


class ACEProReadOnlyProbe:
    def __init__(self, port: str, baudrate: int = ACE_PRO_BAUD, timeout: float = DEFAULT_TIMEOUT, debug: bool = False):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.debug = debug
        self._request_id = 0
        self.logs: list[ProbeLog] = []

    def probe(self) -> ProbeResult:
        if not self.port:
            return ProbeResult(False, self.port, self.baudrate, error="No serial port configured")

        result = ProbeResult(ok=False, port=self.port, baudrate=self.baudrate)
        try:
            with serial.Serial(self.port, self.baudrate, exclusive=True, rtscts=True, timeout=0.05, write_timeout=1.0) as ser:
                info_resp = self._send_recv(ser, "get_info")
                if info_resp:
                    result.info = info_resp.get("result", {})

                status_resp = self._send_recv(ser, "get_status")
                if status_resp:
                    result.status = status_resp.get("result", {})

                temp_resp = self._send_recv(ser, "get_temp")
                if temp_resp:
                    result.temp = temp_resp.get("result", {})

            result.logs = self.logs
            result.ok = bool(result.info or result.status or result.temp)
            if not result.ok:
                result.error = "No valid ACE Pro response received"
            return result
        except Exception as exc:
            result.logs = self.logs
            result.error = str(exc)
            return result

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send_recv(self, ser: serial.Serial, method: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        req_id = self._next_id()
        packet = build_request(method, req_id, params)
        self.logs.append(ProbeLog("tx", method, packet.hex()))
        ser.write(packet)
        ser.flush()

        buffer = bytearray()
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            waiting = ser.in_waiting
            if waiting:
                data = ser.read(waiting)
                buffer.extend(data)
                response, consumed = parse_response(buffer)
                if response is not None:
                    self.logs.append(ProbeLog("rx", method, data.hex()))
                    return response
                elif self.debug:
                    self.logs.append(ProbeLog("rx", method, data.hex(), "unparsed"))
            else:
                time.sleep(0.01)

        self.logs.append(ProbeLog("rx", method, "", "timeout"))
        return None
