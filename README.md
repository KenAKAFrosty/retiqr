# retiqr — Reticulum QR Interface

Some places have internet but won't give it to you. Hotel lobbies, library terminals, car dashboards, airport kiosks — a browser is right there, but there's no open WiFi, no ethernet port, no way to get your device online.

retiqr fixes that. Point a camera at the screen and plug in your virtual keyboard to the USB port. The kiosk becomes a Reticulum relay.

**Downlink (kiosk → you):** the browser renders animated QR codes; your camera reads them  
**Uplink (you → kiosk):** your device types HID keystrokes into a hidden input on the page

No drivers. No network join. Just a USB port and a screen.

## Components

| Directory | Description |
|-----------|-------------|
| `gateway/` | Server-side: aiohttp app that serves the kiosk page and splices WebSocket ↔ Reticulum TCP |
| `client/` | Your-side: desktop app (Mac/Linux/Pi Zero) — webcam QR decode + BLE/HID uplink + Reticulum TCP bridge |
| `firmware/` | ESP32-S3 (M5Stack AtomS3 Lite) BLE → USB HID keyboard dongle for the laptop uplink path |
| `shared/` | `framing.py` — HDLC, HID, and QR wire format shared by gateway and client |

See each component's `README.md` for setup and usage details.

## How it works

```
Reticulum network
  ↕ TCP/HDLC
gateway/            ← your server, reachable from the public internet
  ↕ WebSocket
kiosk browser       ← you navigate here on the kiosk
  ↕ QR codes (downlink) / HID keystrokes (uplink)
client/             ← running on your laptop or Pi Zero
  ↕ TCP/HDLC (localhost:4243)
Reticulum stack     ← your apps: Sideband, NomadNet, etc.
```

The gateway is protocol-blind — it splices bytes without knowing anything about Reticulum. All the intelligence is on your device.
