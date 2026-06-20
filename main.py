"""
ACELink - controller for Anycubic ACE Pro and ACE 2 Pro.
Serves the web UI and handles ACE hardware on the local network.
Intended for use on your local network only.
"""

from pathlib import Path

import argparse
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from acelink_config import AcelinkSettings, AcelinkSettingsPatch, load_settings, save_settings
from ace2_protocol import ACE2_BAUD, ACE2ReadOnlyProbe
from ace_protocol import ACEProReadOnlyProbe
from ace_manager import ACEManager
from mock_ace_manager import MockACEManager
import serial.tools.list_ports

ROOT = Path(__file__).resolve().parent
WEBUI_DIR = ROOT / "webui" / "dist"
WEBUI_INDEX = WEBUI_DIR / "index.html"

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("acelink")

SETTINGS = load_settings()
CONFIG = SETTINGS.model_dump()
DEVICE_AUTO = "auto"
DEVICE_ACE_PRO = "ace_pro"
DEVICE_ACE_2_PRO = "ace_2_pro"

MAX_DRYER_TEMP = {
    DEVICE_ACE_PRO: 55,
    DEVICE_ACE_2_PRO: 65,
}

MIN_DRYER_TEMP = {
    DEVICE_ACE_PRO: 35,
    DEVICE_ACE_2_PRO: 35,
}

def _dryer_max_temp() -> int:
    if ace and hasattr(ace, '_model') and ace._model:
        return MAX_DRYER_TEMP.get(ace._model, 55)
    model = CONFIG.get("device_model", DEVICE_AUTO)
    return MAX_DRYER_TEMP.get(model, 55)

def _dryer_min_temp() -> int:
    if ace and hasattr(ace, '_model') and ace._model:
        return MIN_DRYER_TEMP.get(ace._model, 35)
    model = CONFIG.get("device_model", DEVICE_AUTO)
    return MIN_DRYER_TEMP.get(model, 35)

# ── WebSocket connection manager ──────────────────────────────────────────────
class WSManager:
    def __init__(self):
        self.clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)
        logger.info(f"WS client connected ({len(self.clients)} total)")

    def disconnect(self, ws: WebSocket):
        if ws in self.clients:
            self.clients.remove(ws)
        logger.info(f"WS client disconnected ({len(self.clients)} remaining)")

    async def broadcast(self, data: dict):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.clients:
                self.clients.remove(ws)

ws_manager = WSManager()
ace: ACEManager | MockACEManager | None = None

# ── App lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI, mock_mode: bool = False):
    global ace
    if not WEBUI_INDEX.exists():
        raise RuntimeError(
            "Web UI build not found. Run the installer script first "
            "so the frontend assets are built into webui/dist/."
        )
    ace = MockACEManager(CONFIG) if mock_mode else ACEManager(CONFIG)
    ace.add_event_callback(ws_manager.broadcast)
    await ace.start()
    debug_tag = " [debug] " if getattr(app, 'debug_enabled', False) else " "
    logger.info("ACE Manager started%s(%s mode)",
                debug_tag,
                "mock" if isinstance(ace, MockACEManager) else "real")
    yield
    await ace.stop()
    logger.info("ACE Manager stopped")

app = FastAPI(
    title="ACELink",
    description="Web controller for Anycubic ACE filament changers",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# ── Pydantic models ───────────────────────────────────────────────────────────
class DryerStartRequest(BaseModel):
    temp_c: int = 55
    duration_min: int = 240

class LoadRequest(BaseModel):
    slot: int

class FeedRequest(BaseModel):
    slot: int
    speed: int = 80

# ── Control endpoints (used by the web UI) ────────────────────────────────────

@app.get("/devices")
async def get_devices():
    return ace.get_all_status()

@app.get("/devices/{device_index}")
async def get_device(device_index: int):
    status = ace.get_all_status()
    if device_index not in status:
        raise HTTPException(404, f"Device {device_index} not found")
    return status[device_index]

@app.post("/devices/{device_index}/load_slot")
async def load_slot(device_index: int, req: LoadRequest):
    try:
        return await ace.load_slot(device_index, req.slot)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/devices/{device_index}/unload_slot")
async def unload_slot(device_index: int, req: LoadRequest):
    try:
        return await ace.unload_slot(device_index, req.slot)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/devices/{device_index}/load_all")
async def load_all(device_index: int):
    try:
        return await ace.load_all(device_index)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/devices/{device_index}/unload_all")
async def unload_all(device_index: int):
    try:
        return await ace.unload_all(device_index)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/devices/{device_index}/feed")
async def feed(device_index: int, req: FeedRequest):
    try:
        return await ace.feed(device_index, req.slot, req.speed)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/devices/{device_index}/retract")
async def retract(device_index: int, req: FeedRequest):
    try:
        return await ace.retract(device_index, req.slot, req.speed)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/devices/{device_index}/dryer/start")
async def start_dryer(device_index: int, req: DryerStartRequest):
    if req.temp_c > _dryer_max_temp():
        raise HTTPException(400, f"Temperature exceeds max ({_dryer_max_temp()}°C)")
    try:
        return await ace.start_dryer(device_index, req.temp_c, req.duration_min)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/devices/{device_index}/dryer/stop")
async def stop_dryer(device_index: int):
    try:
        return await ace.stop_dryer(device_index)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/devices/{device_index}/rfid/{slot}")
async def get_rfid(device_index: int, slot: int):
    try:
        return await ace.get_rfid(device_index, slot)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/config")
async def get_config():
    return {
        **CONFIG,
        "mock_mode": isinstance(ace, MockACEManager),
        "max_dryer_temp": _dryer_max_temp(),
        "min_dryer_temp": _dryer_min_temp(),
    }

@app.get("/serial/ports")
async def get_serial_ports():
    return [
        {
            "device": port.device,
            "description": port.description,
            "hwid": port.hwid,
            "vid": port.vid,
            "pid": port.pid,
            "manufacturer": port.manufacturer,
        }
        for port in serial.tools.list_ports.comports()
    ]

@app.post("/hardware/probe")
async def probe_hardware():
    port = CONFIG.get("serial_port", "")
    baudrate = CONFIG.get("baudrate", ACE2_BAUD)
    debug = CONFIG.get("protocol_debug", False)
    device_model = CONFIG.get("device_model", DEVICE_AUTO)
    result = await _run_read_only_probe(port, baudrate, device_model, debug)
    return result.to_dict()


async def _run_read_only_probe(port: str, baudrate: int, device_model: str, debug: bool):
    await ace.release_serial()
    try:
        if device_model == DEVICE_ACE_PRO:
            return await asyncio.to_thread(ACEProReadOnlyProbe(port, 115200, debug=debug).probe)
        if device_model == DEVICE_ACE_2_PRO:
            return await asyncio.to_thread(ACE2ReadOnlyProbe(port, ACE2_BAUD, debug=debug).probe)

        if baudrate == 115200:
            first = await asyncio.to_thread(ACEProReadOnlyProbe(port, 115200, debug=debug).probe)
            if first.ok:
                return first
            return await asyncio.to_thread(ACE2ReadOnlyProbe(port, ACE2_BAUD, debug=debug).probe)

        first = await asyncio.to_thread(ACE2ReadOnlyProbe(port, ACE2_BAUD, debug=debug).probe)
        if first.ok:
            return first
        return await asyncio.to_thread(ACEProReadOnlyProbe(port, 115200, debug=debug).probe)
    finally:
        try:
            await ace.reconnect()
        except Exception:
            pass

@app.put("/config")
async def update_config(req: AcelinkSettingsPatch):
    global SETTINGS
    previous_port = SETTINGS.port
    patch = req.model_dump(exclude_unset=True, exclude_none=True)
    updated = AcelinkSettings.model_validate({
        **SETTINGS.model_dump(),
        **patch,
    })
    save_settings(updated)
    SETTINGS = updated
    CONFIG.clear()
    CONFIG.update(updated.model_dump())
    restart_required = updated.port != previous_port
    return {
        "config": {
            **CONFIG,
            "mock_mode": isinstance(ace, MockACEManager),
            "debug_mode": getattr(app, 'debug_enabled', False),
        },
        "restart_required": restart_required,
    }

# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    # Send current state on connect
    await websocket.send_text(json.dumps({
        "event": "initial_state",
        "data": ace.get_all_status(),
    }))
    try:
        while True:
            # Accept pings / commands over WS too
            msg = await websocket.receive_text()
            try:
                cmd = json.loads(msg)
                result = await _handle_ws_command(cmd)
                await websocket.send_text(json.dumps({"event": "command_result", "data": result}))
            except Exception as e:
                await websocket.send_text(json.dumps({"event": "error", "data": str(e)}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

async def _handle_ws_command(cmd: dict) -> Any:
    action = cmd.get("action")
    idx = cmd.get("device_index", 0)
    if action == "load_slot":
        return await ace.load_slot(idx, cmd["slot"])
    elif action == "unload_slot":
        return await ace.unload_slot(idx, cmd["slot"])
    elif action == "load_all":
        return await ace.load_all(idx)
    elif action == "unload_all":
        return await ace.unload_all(idx)
    elif action == "feed":
        return await ace.feed(idx, cmd["slot"], cmd.get("speed"))
    elif action == "retract":
        return await ace.retract(idx, cmd["slot"], cmd.get("speed"))
    elif action == "dryer_start":
        temp_c = cmd.get("temp_c", 55)
        if temp_c > _dryer_max_temp():
            raise ValueError(f"Temperature exceeds max ({_dryer_max_temp()}°C)")
        return await ace.start_dryer(idx, temp_c, cmd.get("duration_min", 240))
    elif action == "dryer_stop":
        return await ace.stop_dryer(idx)
    elif action == "rfid":
        return await ace.get_rfid(idx, cmd["slot"])
    elif action == "status":
        return ace.get_all_status()
    else:
        raise ValueError(f"Unknown action: {action}")

# ── Serve web UI ──────────────────────────────────────────────────────────────

def mount_webui():
    if not WEBUI_INDEX.exists():
        raise RuntimeError(
            "Web UI build not found. Run the installer script first "
            "so the frontend assets are built into webui/dist/."
        )
    assets_dir = WEBUI_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_webui(full_path: str):
        return FileResponse(WEBUI_DIR / "index.html")

# ── Entry point ───────────────────────────────────────────────────────────────
mount_webui()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ACELink — local ACE controller")
    parser.add_argument("--debug", action="store_true", help="Start in mock mode (no hardware needed)")
    args = parser.parse_args()

    app.router.lifespan_context = lambda app: lifespan(app, mock_mode=args.debug)

    port = CONFIG["port"]
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
