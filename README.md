# ACELink

Standalone local-network controller for Anycubic ACE Pro and ACE 2 Pro filament changers.

ACELink lets an ACE unit be controlled without a printer. A host computer stays connected to the ACE, runs ACELink, and serves a web UI on your local network.

> **Disclaimer:** You are responsible for your own hardware, wiring, and use of this project. I am not responsible for damage to your ACE, host computer, adapter, printer, or other equipment.

---

## Supported Models

| Model | Protocol | Baud Rate | Connection |
|---|---|---|---|
| Anycubic ACE Pro | JSON over serial | 115200 | USB cable → 6-pin connector |
| Anycubic ACE 2 Pro | Protobuf over serial | 230400 | USB-to-RS485 adapter → 6-pin connector |

Both models share the same 6-pin Micro-Fit 3.0 2x3P signal connector, but use different electrical paths. ACE 2 Pro tested and validated on real hardware.

---

## Hardware Connection

### Connector Pinout

![ACE 6-pin signal connector pinout](docs/images/ace-2-pro-6pin-pinout.png)

```
ACE-side 6-pin signal connector, front/mating side
Clip/latch side at the top

             clip/latch
                ||
      +-------------------+
      | [NC]  [D+]  [D-]  |
      | [NC]  [GND] [5V]  |
      +-------------------+
```

**Warning:** The `5V` pin is shown for identification only. Do not connect it. Connecting `5V` can damage the ACE, adapter, or host USB port.

### ACE Pro Wiring

ACE Pro uses a direct USB data path:

| USB cable wire | ACE Pro signal connector |
|---|---|
| USB `D-` | `D-` |
| USB `D+` | `D+` |
| USB `GND` | `GND` |
| USB `5V` | Do not connect |

### ACE 2 Pro Wiring

ACE 2 Pro requires a USB-to-RS485 adapter. Community-validated with CH340-based adapters:

| Adapter label | ACE 2 Pro signal | Notes |
|---|---|---|
| `GND` | Ground | Always required |
| `A` (`485+`) | `D+` or `D-` | Swap if commands time out |
| `B` (`485-`) | The other of `D+`/ `D-` | Swap if commands time out |
| `VCC` | Do not connect | Always leave disconnected |

**If the adapter enumerates but ACE commands time out:** keep `GND` connected and swap the `A`/`B` pair. A working link will show real temperature and status values.

---

## Run with Docker Compose on Linux

Compose pulls the published GHCR image. CI builds and smoke-tests the container in mock mode and validates the Compose configuration. These instructions assume your adapter, wiring, and host device permissions work; physical serial communication through Docker has not been tested in this release.

1. Find the serial adapter under `/dev/serial/by-id/` or check for a device such as `/dev/ttyUSB0`.
2. Run `stat -Lc '%g' /path/to/serial-device` to get its numeric group ID.
3. Create a `.env` file beside `compose.yaml` with your device path and group ID.

```dotenv
ACELINK_DEVICE=/dev/serial/by-id/replace-with-your-adapter
ACELINK_DEVICE_GID=20
```

Replace both example values. Run `docker compose up -d`, then open `http://localhost:8765`. Compose pulls `ghcr.io/tareku99/acelink:latest` and checks for updates each time the service starts. In **Settings**, set the serial path to `/dev/ttyACELink`, the path mapped by Compose. Compose persists the settings in the `acelink-data` volume. Use `docker compose logs -f` for troubleshooting.

### Migrating native settings

Before starting the service, you can copy the native `acelink.config.json` into the persistent volume. Keep an untouched backup; the copy in the volume is used by Docker and updated by the web UI.

```bash
docker compose run --rm --no-deps \
  -v "$PWD/acelink.config.json:/tmp/native-settings.json:ro" \
  --entrypoint sh acelink -c \
  'cp /tmp/native-settings.json /data/acelink.config.json'
docker compose up -d
```

Set `.env` first, as shown above. This copies the file into the named volume as the container's non-root user. Confirm the serial path in **Settings** because Compose maps the host device to `/dev/ttyACELink`.

To reach the UI from another computer on your local network, set `ACELINK_BIND_ADDRESS` to the Docker host's LAN IP and recreate the service. Use `ACELINK_HOST_PORT` to change the host port.

### Published GHCR image

The production image is `ghcr.io/tareku99/acelink:latest`. Pushes to `main` update the `main` and `latest` tags; version tags also publish a matching tag and `latest`. Beta builds are published as `beta` and `beta-<12-character-commit>`. The `beta` tag may change with each beta release. Set `ACELINK_IMAGE=ghcr.io/tareku99/acelink:beta` in `.env` to try it. The image targets `linux/amd64`.

## Native install scripts

The existing scripts remain available for Windows, macOS, and direct hardware testing. Install Python 3.11+ and Node.js. On Linux or macOS use `scripts/install.sh` or `scripts/run.sh`. On Windows use `scripts/install.ps1` or `scripts/run.ps1`.

## Configuration

Native runs store settings in `acelink.config.json` next to the app. The container stores settings in `/data/acelink.config.json`. The web UI Settings tab provides a form for all options.

| Field | Default | Description |
|---|---|---|
| `port` | `8765` | Web UI port (restart required) |
| `device_model` | `auto` | `auto`, `ace_pro`, or `ace_2_pro` |
| `serial_port` | *(auto-detected)* | Serial device path |
| `baudrate` | `230400` | Baud rate hint for auto-detect |
| `scan_interval` | `15` | Polling interval in seconds |
| `protocol_debug` | `false` | Show raw serial bytes in logs |
| `load_length` | `2100` | Global load feed length (mm) |
| `retract_length` | `1950` | Global retract length (mm) |
| `feed_speed` | `80` | Global feed speed (mm/s) |
| `retract_speed` | `30` | Global retract speed (mm/s) |
| `slot_tuning` | *(array)* | Per-slot override for the above |

Dryer temperature limits are hard-coded per model:
- **ACE Pro**: 35–55°C
- **ACE 2 Pro**: 35–65°C

---

## Commands

All commands operate on the connected ACE device.

| Command | Slot | Description |
|---|---|---|
| Feed | per-slot | Push filament forward through the slot |
| Retract | per-slot | Pull filament back through the slot |
| Dryer Start | n/a | Start drying at specified temp/duration |
| Dryer Stop | n/a | Stop the dryer |
| Load Spool (manual) | per-slot | Manually mark a non-RFID spool as loaded |

The ACE 2 Pro RFID reader detects filament after a brief feed, populating type, color, and brand automatically. Manual "Load spool" is available for non-RFID filament.

---

## UI

![Device tab](docs/images/device-tab.png)

Three tabs:

- **Device** — Slot status, filament info, feed/retract controls, dryer controls, presets
- **Settings** — App port, movement defaults, slot tuning
- **Diagnostics** — Hardware probe results and event log

### Dryer Presets

Save and recall temperature/duration profiles. The preset name is its identity — editing and saving with the same name updates the preset, a new name creates a new one.

---

## Local development

```bash
python -m venv .venv
source .venv/bin/activate  # PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm --prefix webui ci
npm --prefix webui run build
python -m unittest discover -s tests
python main.py --debug
```

Open `http://localhost:8765`. Mock mode starts the same web UI without an ACE. For native hardware testing, run `python main.py` after setting up the serial adapter.

## Support

[Support](https://github.com/Tareku99/.github/blob/main/SUPPORT.md) · [Security reporting](https://github.com/Tareku99/.github/blob/main/SECURITY.md) · [License](LICENSE)

## Credits

ACELink protocol and connectivity knowledge is derived from:
- [BlackFrogKok/SnapAce](https://github.com/BlackFrogKok/SnapAce)
- [hakimio/U1-Ace](https://github.com/hakimio/U1-Ace)
- [DnG-Crafts/U1-Ace](https://github.com/DnG-Crafts/U1-Ace)
- [decay71/multiACE](https://github.com/decay71/multiACE)
