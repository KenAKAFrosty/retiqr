# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Gateway
```bash
cd gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium

python gateway.py --target-host <host> --target-port 4242

pytest                          # 45 tests, ~13s
pytest tests/test_framing.py    # framing unit tests only
pytest tests/test_kiosk_ui.py   # Playwright browser tests
pytest -k test_hdlc_round_trip  # single test by name
```

### Client
```bash
cd client
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

python main.py --uplink ble|gadget|none [--key-delay-ms 5] [--bridge-port 4243] [--camera 0]

pytest                          # 64 tests, ~1s, no hardware needed
pytest tests/test_bridge.py
pytest tests/test_decoder.py
pytest -k test_basic_round_trip
```

### Firmware
```bash
cd firmware
pio run               # build
pio run -t upload     # flash (device must be in ROM bootloader mode first)
```
To enter ROM bootloader: hold the side button, tap the recessed RST on the bottom, release both.

## Architecture

```
Reticulum network
  ↕ TCP/HDLC
gateway/gateway.py          aiohttp — serves static/, splices /ws ↔ TCP
  ↕ WebSocket (binary)      one TCP connection per browser session
gateway/static/index.html   HDLC parse/encode, QR render, HID capture
  ↕ QR codes (downlink) / HID keyboard (uplink)
client/                     webcam QR decode + BLE/HID uplink + TCP bridge
  ↕ TCP/HDLC (localhost:4243)
Reticulum stack (user machine)
```

### Gateway key files

**`gateway.py`** — `build_app()` wires three routes: `GET /` → `index.html`, `GET /ws` → `ws_handler`, `GET /static/*` → files. Each WebSocket opens a fresh TCP connection to the Reticulum node — sessions are fully isolated.

**`static/index.html`** — self-contained SPA. Key constants: `FRAME_MS = 200` (ms/QR frame), `MAX_QR_CHUNK = 80` (bytes of packet data per QR). QR codes rendered via `qrcode-generator` in Byte mode — `Array.from(data, b => String.fromCharCode(b)).join('')` avoids UTF-8 re-encoding. 4-module white quiet zone drawn around each code. Canvas dimensions reset only on resize, not per frame. `#hid-input` kept focused via `setInterval(refocus, 250)`. `blink()` takes an element reference, not a string ID.

### Client key files

**`bridge.py`** — `Bridge`: asyncio TCP server. Per-connection `_Connection` runs two tasks (read/write) cancelled together via `asyncio.wait(FIRST_COMPLETED)`. `put_rx()` and `close()` are thread-safe via `loop.call_soon_threadsafe` — `_Connection` captures the loop with `asyncio.get_running_loop()` at construction.

**`rx/camera.py`** — OpenCV VideoCapture background thread. `CAP_PROP_BUFFERSIZE=1` keeps the capture buffer minimal. `.copy()` after `[:,:,::-1]` is mandatory — non-contiguous arrays crash zxingcpp and QImage.

**`rx/decoder.py`** — `decode_frame(img) -> (fragments, n_raw)`. Always use zxing-cpp (`symbol.bytes`) — pyzbar/zbar does locale-dependent Big5 charset conversion on macOS that corrupts binary payloads.

**`rx/reassembler.py`** — `Reassembler.feed()`: dedup via `set`+`deque(maxlen=64)` (O(1) lookup, bounded eviction). Incomplete assemblies evicted at `_MAX_PENDING_SEQS=32`.

**`tx/ble.py`** — `BleUplink`: bleak BLE central, scans for `"KioskDongle"`, "Just Works" pairing. Frames split into 20-byte chunks before writing (works regardless of negotiated ATT MTU).

**`tx/gadget.py`** — `GadgetUplink`: writes 8-byte HID boot-protocol reports to `/dev/hidg0`. Typing runs in `loop.run_in_executor`. Only chars in HID frames have `_KEY_MAP` entries: `>` `<` `0–9` `A–F`. Modifier `0x02` = Left Shift.

**`gui/app.py`** — PySide6 window. macOS: `cv2.VideoCapture(device)` must be probed and released from the Qt main thread before the camera background thread starts (triggers the permission dialog).

### Firmware key details

Target: M5Stack AtomS3 Lite (ESP32-S3FN8). BLE GATT server → USB HID keyboard bridge.

**Pinout:** GPIO 35 = SK6812 LED, GPIO 41 = button (active-low), GPIO 5 = Serial1 TX (pad G5), GPIO 6 = Serial1 RX (pad G6), USB-C = native ESP32-S3 USB OTG (HID keyboard).

**GATT UUIDs** (must match `tx/ble.py` exactly):
```
Service:  4b696f73-6b55-0001-0000-000000000000
TX char:  4b696f73-6b55-0002-0000-000000000000  WRITE_NR  (20-byte chunks)
CFG char: 4b696f73-6b55-0003-0000-000000000000  WRITE     (2-byte big-endian ms delay)
```

Key behaviour:
- BLE TX char reassembled in NimBLE task; `>` resets buffer, `<` flushes to FreeRTOS queue (depth 4, drop-newest)
- Typing only in `loop()` — never in BLE callbacks — avoids BLE stack timeouts on long frames
- `keyDelayMs` clamped to [1, 100] ms; `ledState`/`bleConnected`/`keyDelayMs` are `volatile` (cross-core)
- `FRAME_MAX = 1024` — sized for max Reticulum packet (~500 bytes → ~1004-byte HID frame)
- Button long-press (3 s): `deleteAllBonds()` + reboot. LED: yellow pulse = scanning, blue = idle, green = typing
- `upload_protocol = dfu` is NOT available (PlatformIO's bundled tool missing). Use ROM bootloader + `pio run -t upload`.

## Wire formats

**Downlink QR payload:** `[seq_hi, seq_lo, frag_total, frag_idx, ...chunk]`
- `MAX_QR_CHUNK = 80` bytes of packet data per fragment. `enqueuePacket()` in `index.html` must mirror `qr_fragments()` in `shared/framing.py`.
- 4-module white quiet zone required — cameras can't find finder patterns against the dark (#0a0a0a) background without it.

**Uplink HID frame:** `>HEXHEX...CC<`
- Uppercase hex + 2-char XOR checksum of all payload bytes. Browser validates checksum before forwarding.

**HDLC framing:** flag `0x7E`, escape `0x7D`, escaped byte XOR `0x20`.

**`shared/framing.py`** is the single source of truth. `gateway/framing.py` and `client/framing.py` are thin shims that load it via `importlib.util`. The JS in `index.html` reimplements the same logic — keep `MAX_QR_CHUNK` in sync.
