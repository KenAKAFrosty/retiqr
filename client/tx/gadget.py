"""
USB HID gadget uplink for Pi Zero (and any Linux with USB gadget support).

Writes 8-byte USB HID keyboard boot-protocol reports to /dev/hidg0.
The Pi Zero must be configured with the dwc2 overlay and libcomposite
keyboard gadget before this module is used — see CLAUDE.md for setup.

HID frame characters and their USB HID (modifier, keycode) values:
  '>' shift+.   '<' shift+,   '0'-'9'  plain    'A'-'F' shift+a-f
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

# USB HID modifier byte: bit 1 = Left Shift
_NO_MOD  = 0x00
_SHIFT   = 0x02
_KEY_UP  = bytes(8)

# Characters that appear in a HID frame: > < 0-9 A-F
_KEY_MAP: dict[int, tuple[int, int]] = {
    ord('>'): (_SHIFT,  0x37),  # shift + .
    ord('<'): (_SHIFT,  0x36),  # shift + ,
    ord('0'): (_NO_MOD, 0x27),
    ord('1'): (_NO_MOD, 0x1E), ord('2'): (_NO_MOD, 0x1F),
    ord('3'): (_NO_MOD, 0x20), ord('4'): (_NO_MOD, 0x21),
    ord('5'): (_NO_MOD, 0x22), ord('6'): (_NO_MOD, 0x23),
    ord('7'): (_NO_MOD, 0x24), ord('8'): (_NO_MOD, 0x25),
    ord('9'): (_NO_MOD, 0x26),
    ord('A'): (_SHIFT,  0x04), ord('B'): (_SHIFT,  0x05),
    ord('C'): (_SHIFT,  0x06), ord('D'): (_SHIFT,  0x07),
    ord('E'): (_SHIFT,  0x08), ord('F'): (_SHIFT,  0x09),
}


def _type_frame_sync(hid, frame: bytes, key_delay: float) -> None:
    """Type one HID frame as keyboard reports. Runs in a thread-pool executor."""
    for b in frame:
        entry = _KEY_MAP.get(b)
        if entry is None:
            continue
        mod, kc = entry
        hid.write(bytes([mod, 0, kc, 0, 0, 0, 0, 0]))
        time.sleep(key_delay)
        hid.write(_KEY_UP)
        time.sleep(key_delay)


class GadgetUplink:
    """USB HID gadget keyboard — types HID frames directly via /dev/hidg0."""

    kind = "HID"

    def __init__(self, device: str = "/dev/hidg0", key_delay_ms: int = 5):
        self.on_connect    = None   # callable()
        self.on_disconnect = None   # callable()
        self._device       = device
        self._key_delay    = key_delay_ms / 1000.0
        self._connected    = False
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def send(self, frame: bytes) -> None:
        """Queue a HID frame. Called from within the event loop."""
        self._queue.put_nowait(frame)

    @property
    def connected(self) -> bool:
        return self._connected

    async def run(self) -> None:
        while True:
            if not Path(self._device).exists():
                log.debug("HID gadget: %s not present, waiting...", self._device)
                await asyncio.sleep(2)
                continue
            stop_requested = await self._run_once()
            if stop_requested:
                break
            await asyncio.sleep(1)

    async def stop(self) -> None:
        self._queue.put_nowait(None)

    async def _run_once(self) -> bool:
        """Open gadget and type frames until error or stop(). Returns True if stop()."""
        loop = asyncio.get_running_loop()
        try:
            with open(self._device, "wb", buffering=0) as hid:
                self._connected = True
                if self.on_connect:
                    self.on_connect()
                log.info("HID gadget: opened %s (key_delay=%dms)",
                         self._device, int(self._key_delay * 1000))

                while True:
                    frame = await self._queue.get()
                    if frame is None:
                        return True  # stop() requested
                    await loop.run_in_executor(
                        None, _type_frame_sync, hid, frame, self._key_delay
                    )

        except OSError as exc:
            log.warning("HID gadget: %s", exc)
        finally:
            if self._connected:
                self._connected = False
                if self.on_disconnect:
                    self.on_disconnect()

        return False
