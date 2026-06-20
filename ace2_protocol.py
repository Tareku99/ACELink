"""
ACE 2 Pro serial protocol — binary frame format, protobuf decoding, and
read-only hardware probe.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import serial

ACE2_BAUD = 230400
PREAMBLE = b"\xff\xaa"
END_MARKER = 0xFE
FLAG_REQUEST = 0x00
FLAG_RESPONSE = 0x80
MAX_PAYLOAD_LEN = 100


class ACE2Command(IntEnum):
    DISCOVER_DEVICE = 0
    ASSIGN_DEVICE_ID = 1
    GET_STATUS = 6
    GET_INFO = 7
    FEED_OR_ROLLBACK = 8
    STOP_FEED_OR_ROLLBACK = 9
    UPDATE_SPEED = 10
    DRYING = 11
    GET_FILAMENT_INFO = 13
    SET_FEED_CHECK = 19
    GET_TEMP = 64


COMMAND_NAMES = {
    ACE2Command.DISCOVER_DEVICE: "DISCOVER_DEVICE",
    ACE2Command.ASSIGN_DEVICE_ID: "ASSIGN_DEVICE_ID",
    ACE2Command.GET_STATUS: "GET_STATUS",
    ACE2Command.GET_INFO: "GET_INFO",
    ACE2Command.FEED_OR_ROLLBACK: "FEED_OR_ROLLBACK",
    ACE2Command.STOP_FEED_OR_ROLLBACK: "STOP_FEED_OR_ROLLBACK",
    ACE2Command.UPDATE_SPEED: "UPDATE_SPEED",
    ACE2Command.DRYING: "DRYING",
    ACE2Command.GET_FILAMENT_INFO: "GET_FILAMENT_INFO",
    ACE2Command.SET_FEED_CHECK: "SET_FEED_CHECK",
    ACE2Command.GET_TEMP: "GET_TEMP",
}

# ── Feed modes ────────────────────────────────────────────────────────────────

FEED_MODE_FEED = 0
FEED_MODE_ROLLBACK = 1
FEED_MODE_FEED_ASSIST = 2
FEED_MODE_UNWIND_ASSIST = 3

# ── Slot states ───────────────────────────────────────────────────────────────

SLOT_READY = 0
SLOT_FEEDING = 1
SLOT_ROLLBACK = 2
SLOT_ASSISTING = 3
SLOT_ROLLBACK_ASSISTING = 4
SLOT_PRELOADING = 5
SLOT_UPGRADING = 6
SLOT_FEED_ERROR = 129

SLOT_ERROR_STATUS_BY_RAW = {
    SLOT_FEED_ERROR: "feed_error",
    130: "rollback_error",
    131: "assist_error",
    132: "preload_error",
    133: "stuck",
    134: "tangled",
    135: "motor_error",
}

FILAMENT_EMPTY = 0
FILAMENT_IDENTIFIED = 2

# ── Dryer states ──────────────────────────────────────────────────────────────

DRY_STATE_NAMES = {
    0: "free",
    1: "starting",
    2: "keeping",
    3: "stopping",
    4: "ptc_error",
    5: "ntc_error",
}


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class ACE2Frame:
    cmd: int
    payload: bytes
    seq: int
    flags: int

    @property
    def is_response(self) -> bool:
        return bool(self.flags & FLAG_RESPONSE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cmd": self.cmd,
            "cmd_name": COMMAND_NAMES.get(self.cmd, f"0x{self.cmd:02x}"),
            "seq": self.seq,
            "flags": self.flags,
            "is_response": self.is_response,
            "payload_hex": self.payload.hex(),
        }


@dataclass
class ProbeLog:
    direction: str
    cmd: int
    seq: int
    frame_hex: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "cmd": self.cmd,
            "cmd_name": COMMAND_NAMES.get(self.cmd, f"0x{self.cmd:02x}"),
            "seq": self.seq,
            "frame_hex": self.frame_hex,
            "note": self.note,
        }


@dataclass
class ProbeResult:
    ok: bool
    port: str
    baudrate: int
    model: str = "Anycubic ACE 2 Pro"
    protocol: str = "protobuf"
    uid: list[int] | None = None
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
            "uid": self.uid,
            "info": self.info,
            "status": self.status,
            "temp": self.temp,
            "logs": [entry.to_dict() for entry in self.logs],
            "error": self.error,
        }


# ── CRC and protobuf helpers ──────────────────────────────────────────────────


def crc16_kermit(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc & 0xFFFF


def pb_varint(value: int) -> bytes:
    out = bytearray()
    value = int(value)
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value & 0x7F)
    return bytes(out)


def pb_uint32(field: int, value: int) -> bytes:
    return pb_varint((field << 3) | 0) + pb_varint(int(value) & 0xFFFFFFFF)


def pb_bool(field: int, value: bool) -> bytes:
    return pb_varint((field << 3) | 0) + pb_varint(1 if value else 0)


def pb_decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, pos
        shift += 7
    return result, pos


def pb_decode(data: bytes) -> dict[int, list[tuple[int, Any]]]:
    fields: dict[int, list[tuple[int, Any]]] = {}
    pos = 0
    while pos < len(data):
        tag, pos = pb_decode_varint(data, pos)
        field_num = tag >> 3
        wire_type = tag & 7
        if wire_type == 0:
            value, pos = pb_decode_varint(data, pos)
        elif wire_type == 1:
            if pos + 8 > len(data):
                break
            value = struct.unpack_from("<d", data, pos)[0]
            pos += 8
        elif wire_type == 2:
            length, pos = pb_decode_varint(data, pos)
            if pos + length > len(data):
                break
            value = bytes(data[pos : pos + length])
            pos += length
        elif wire_type == 5:
            if pos + 4 > len(data):
                break
            value = struct.unpack_from("<f", data, pos)[0]
            pos += 4
        else:
            break
        fields.setdefault(field_num, []).append((wire_type, value))
    return fields


def _field_value(fields: dict[int, list[tuple[int, Any]]], field: int, default: Any = None) -> Any:
    if field not in fields:
        return default
    return fields[field][0][1]


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


# ── Packet framing ────────────────────────────────────────────────────────────


def build_packet(cmd: int, payload: bytes = b"", seq: int = 1, flags: int = FLAG_REQUEST) -> bytes:
    if len(payload) > MAX_PAYLOAD_LEN:
        raise ValueError(f"Payload exceeds {MAX_PAYLOAD_LEN} bytes")
    inner = bytearray([
        flags & 0xFF,
        seq & 0xFF,
        (seq >> 8) & 0xFF,
        cmd & 0xFF,
        len(payload) & 0xFF,
    ])
    inner.extend(payload)
    crc = crc16_kermit(bytes(inner))
    return PREAMBLE + bytes(inner) + bytes([crc & 0xFF, (crc >> 8) & 0xFF, END_MARKER])


def parse_packet(buffer: bytearray) -> tuple[ACE2Frame | None, int]:
    while len(buffer) >= 2:
        start = buffer.find(PREAMBLE)
        if start < 0:
            return None, max(0, len(buffer) - 1)
        if start > 0:
            return None, start
        if len(buffer) < 10:
            return None, 0

        flags = buffer[2]
        seq = buffer[3] | (buffer[4] << 8)
        cmd = buffer[5]
        payload_len = buffer[6]
        if payload_len > MAX_PAYLOAD_LEN:
            return None, 2
        frame_len = 2 + 5 + payload_len + 2 + 1
        if len(buffer) < frame_len:
            return None, 0
        if buffer[frame_len - 1] != END_MARKER:
            return None, 2

        inner = bytes(buffer[2 : 7 + payload_len])
        received_crc = buffer[7 + payload_len] | (buffer[8 + payload_len] << 8)
        if received_crc != crc16_kermit(inner):
            return None, frame_len

        payload = bytes(buffer[7 : 7 + payload_len])
        return ACE2Frame(cmd=cmd, payload=payload, seq=seq, flags=flags), frame_len

    return None, 0


# ── Decoders ──────────────────────────────────────────────────────────────────


def decode_discover(payload: bytes) -> list[int] | None:
    fields = pb_decode(payload)
    uid = [
        int(_field_value(fields, 1, 0)),
        int(_field_value(fields, 2, 0)),
        int(_field_value(fields, 3, 0)),
    ]
    return uid if any(uid) else None


def decode_info(payload: bytes) -> dict[str, Any]:
    fields = pb_decode(payload)
    return {
        "version": _decode_text(_field_value(fields, 1, b"")),
        "boot_version": _decode_text(_field_value(fields, 2, b"")),
        "first_request": bool(_field_value(fields, 3, 0)),
        "raw_fields": _format_fields(fields),
    }


def _slot_status_to_label(slot_state: int, filament_state: int) -> str:
    if filament_state == FILAMENT_EMPTY:
        return "empty"
    if slot_state == SLOT_FEEDING:
        return "feeding"
    if slot_state == SLOT_PRELOADING:
        return "preload"
    if slot_state == SLOT_ROLLBACK:
        return "unwinding"
    if slot_state in (SLOT_ASSISTING, SLOT_ROLLBACK_ASSISTING):
        return "assisting"
    err = SLOT_ERROR_STATUS_BY_RAW.get(slot_state)
    if err is not None:
        return err
    if slot_state >= SLOT_FEED_ERROR:
        return "error"
    return "ready"


def decode_status(payload: bytes) -> dict[str, Any]:
    fields = pb_decode(payload)
    result: dict[str, Any] = {
        "status": "ready",
        "temp": _field_value(fields, 3, 0),
        "humidity": _field_value(fields, 4, 0),
        "feed_assist_count": _field_value(fields, 7, 0),
    }

    slots = []
    for _, slot_data in fields.get(9, []):
        slot = pb_decode(slot_data) if isinstance(slot_data, bytes) else {}
        slot_state = int(_field_value(slot, 1, 0))
        filament_state = int(_field_value(slot, 2, 0))
        slots.append({
            "status": _slot_status_to_label(slot_state, filament_state),
            "rfid": 2 if filament_state == FILAMENT_IDENTIFIED else (
                0 if filament_state == FILAMENT_EMPTY else 1
            ),
        })
    result["slots"] = slots

    if 2 in fields:
        dryer_data = fields[2][0][1]
        dryer = pb_decode(dryer_data) if isinstance(dryer_data, bytes) else {}
        state = int(_field_value(dryer, 1, 0))
        result["dryer_status"] = {
            "status": DRY_STATE_NAMES.get(state, "free"),
            "target_temp": int(_field_value(dryer, 2, 0)),
            "duration": int(_field_value(dryer, 3, 0)),
            "remain_time": int(_field_value(dryer, 4, 0)),
        }

    return {"result": result}


def decode_temp(payload: bytes) -> dict[str, Any]:
    fields = pb_decode(payload)
    names = {
        1: "box1_temp",
        2: "box2_temp",
        3: "ptc1_temp",
        4: "ptc2_temp",
        5: "env_temp",
        6: "env_humidity",
    }
    decoded: dict[str, Any] = {}
    for field, values in fields.items():
        name = names.get(field, f"field_{field}")
        val = values[0][1]
        decoded[name] = float(val) if isinstance(val, (int, float)) else val
    decoded["raw_fields"] = _format_fields(fields)
    return decoded


def decode_filament_info(payload: bytes) -> dict[str, Any]:
    fields = pb_decode(payload)
    colors = []
    primary_rgb = [0, 0, 0]
    for i, (_, color_data) in enumerate(fields.get(5, [])):
        color = pb_decode(color_data) if isinstance(color_data, bytes) else {}
        rgba = int(_field_value(color, 1, 0)) & 0xFFFFFFFF
        rgb = [(rgba >> 24) & 0xFF, (rgba >> 16) & 0xFF, (rgba >> 8) & 0xFF]
        colors.append(rgb + [rgba & 0xFF])
        if i == 0:
            primary_rgb = rgb
    return {"result": {
        "index": int(_field_value(fields, 1, 0)),
        "sku": _decode_text(_field_value(fields, 3, b"")),
        "type": _decode_text(_field_value(fields, 4, b"")),
        "brand": "",
        "color": primary_rgb,
        "colors": colors,
        "diameter": float(_field_value(fields, 8, 175)) / 100.0,
        "total": int(_field_value(fields, 9, 0)),
        "remainder": int(_field_value(fields, 11, 0)),
        "code": int(_field_value(fields, 12, 0)),
        "rfid": 2,
    }}


def decode_generic(payload: bytes) -> dict[str, Any]:
    fields = pb_decode(payload)
    return {"code": int(_field_value(fields, 1, 0)), "msg": ""}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _format_fields(fields: dict[int, list[tuple[int, Any]]]) -> dict[str, list[Any]]:
    formatted: dict[str, list[Any]] = {}
    for field, values in fields.items():
        field_values = []
        for wire_type, value in values:
            if isinstance(value, bytes):
                try:
                    field_values.append(value.decode())
                except UnicodeDecodeError:
                    field_values.append(value.hex())
            else:
                field_values.append(value)
        formatted[str(field)] = field_values
    return formatted


# ── Read-only probe ───────────────────────────────────────────────────────────


class ACE2ReadOnlyProbe:
    def __init__(self, port: str, baudrate: int = ACE2_BAUD, timeout: float = 1.5, debug: bool = False):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.debug = debug
        self.seq = 0
        self.logs: list[ProbeLog] = []

    def probe(self) -> ProbeResult:
        if not self.port:
            return ProbeResult(False, self.port, self.baudrate, error="No serial port configured")

        result = ProbeResult(ok=False, port=self.port, baudrate=self.baudrate)
        try:
            with serial.Serial(self.port, self.baudrate, timeout=0.1, write_timeout=1.0) as ser:
                uid_frame = self._send_recv(ser, ACE2Command.DISCOVER_DEVICE)
                if uid_frame:
                    result.uid = decode_discover(uid_frame.payload)

                if result.uid:
                    assign_payload = (
                        pb_uint32(1, result.uid[0])
                        + pb_uint32(2, result.uid[1])
                        + pb_uint32(3, result.uid[2])
                        + pb_uint32(4, 1)
                    )
                    self._send_recv(ser, ACE2Command.ASSIGN_DEVICE_ID, assign_payload)
                    time.sleep(0.3)

                info_frame = self._send_recv(ser, ACE2Command.GET_INFO)
                if info_frame:
                    result.info = decode_info(info_frame.payload)

                status_frame = self._send_recv(ser, ACE2Command.GET_STATUS)
                if status_frame:
                    result.status = decode_status(status_frame.payload)

                temp_frame = self._send_recv(ser, ACE2Command.GET_TEMP)
                if temp_frame:
                    result.temp = decode_temp(temp_frame.payload)

            result.logs = self.logs
            result.ok = bool(result.uid or result.info or result.status or result.temp)
            if not result.ok:
                result.error = "No valid ACE 2 Pro response received"
            return result
        except Exception as exc:
            result.logs = self.logs
            result.error = str(exc)
            return result

    def _next_seq(self) -> int:
        self.seq = (self.seq % 0xFFFF) + 1
        return self.seq

    def _send_recv(self, ser: serial.Serial, cmd: int, payload: bytes = b"") -> ACE2Frame | None:
        import threading
        import queue
        seq = self._next_seq()
        packet = build_packet(cmd, payload, seq=seq)
        self.logs.append(ProbeLog("tx", int(cmd), seq, packet.hex()))
        ser.write(packet)
        ser.flush()

        response_buffer = bytearray()
        result_queue: queue.Queue[ACE2Frame | None] = queue.Queue()

        def reader():
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                try:
                    data = ser.read(128)
                except serial.SerialException:
                    break
                if data:
                    response_buffer.extend(data)
                    frame, consumed = parse_packet(response_buffer)
                    if consumed:
                        del response_buffer[:consumed]
                    if frame and frame.cmd == int(cmd) and frame.is_response:
                        result_queue.put(frame)
                        return
                else:
                    time.sleep(0.005)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        try:
            frame = result_queue.get(timeout=self.timeout + 0.5)
            self.logs.append(ProbeLog("rx", frame.cmd, frame.seq, packet.hex()))
            return frame
        except queue.Empty:
            self.logs.append(ProbeLog("rx", int(cmd), seq, "", "timeout"))
            return None
        finally:
            t.join(timeout=0.1)
