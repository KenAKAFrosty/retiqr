"""
QR decode logic — pure, camera-agnostic, fully testable.

decode_frame(img) -> (fragments, n_raw)
  img       : BGR, RGB, or grayscale uint8 numpy array (a single video frame)
  fragments : list of (seq, chunk, frag_idx, frag_total) for every valid QR payload
  n_raw     : QR codes found by zxingcpp before qr_unpack filtering
              (> 0 but fragments empty → QR detected but not a Reticulum frame)

Uses zxing-cpp for decoding because it returns raw bytes for Byte-mode
QR codes regardless of system locale.  pyzbar/zbar performs charset
conversion (Big5 on some systems, Latin-1 on others), making it
unreliable for binary payloads.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)


def decode_frame(img: "np.ndarray") -> tuple[list[tuple[int, bytes, int, int]], int]:
    """Decode all QR codes in a frame.

    Returns (fragments, n_raw).  Each fragment is (seq, chunk, frag_idx, frag_total).
    n_raw is the raw zxingcpp hit count before qr_unpack filtering.
    """
    import zxingcpp  # type: ignore

    from framing import qr_unpack

    if img.ndim == 2:
        img = _to_rgb(img)

    hits = zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode)
    n_raw = len(hits)
    if n_raw:
        log.debug("zxingcpp: %d QR code(s) found in frame", n_raw)

    fragments: list[tuple[int, bytes, int, int]] = []
    for symbol in hits:
        payload: bytes = symbol.bytes
        try:
            seq, chunk, frag_idx, frag_total = qr_unpack(payload)
            fragments.append((seq, chunk, frag_idx, frag_total))
            log.debug("QR seq=0x%04x frag=%d/%d chunk=%d bytes",
                      seq, frag_idx + 1, frag_total, len(chunk))
        except Exception as exc:
            log.warning("QR found but unpack failed (%d bytes): %s", len(payload), exc)

    return fragments, n_raw


def _to_rgb(img: "np.ndarray") -> "np.ndarray":
    import numpy as np

    if img.ndim == 2:
        return np.stack([img, img, img], axis=-1)
    if img.ndim == 3 and img.shape[2] == 3:
        return img
    return img
