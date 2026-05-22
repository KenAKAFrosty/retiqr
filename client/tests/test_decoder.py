"""
Tests for rx/decoder.py — no camera, no display.

QR images are generated from known payloads using the `qrcode` library,
fed to decode_frame() as numpy arrays, and the output is verified.
"""
import numpy as np
import pytest

from framing import qr_pack, qr_unpack
from rx.decoder import decode_frame


def _make_qr_image(data: bytes) -> np.ndarray:
    """Render data as a QR code and return a grayscale numpy array.

    Uses segno so that binary payloads are stored as raw bytes (Byte mode)
    without UTF-8 re-encoding — matching what qrcode-generator produces in
    the kiosk browser.
    """
    import io
    import segno  # type: ignore
    from PIL import Image

    qr = segno.make_qr(data, mode="byte", error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=10, border=1)
    buf.seek(0)
    return np.array(Image.open(buf).convert("L"))


class TestDecodeFrame:
    def _unpack_single(self, results):
        """Helper: assert one single-fragment result, return (seq, packet)."""
        assert len(results) == 1
        seq, chunk, frag_idx, frag_total = results[0]
        assert frag_idx == 0
        assert frag_total == 1
        return seq, chunk

    def test_basic_round_trip(self):
        seq, pkt = 0x0001, b"\xAB\xCD\xEF"
        img = _make_qr_image(qr_pack(seq, pkt))
        fragments, n_raw = decode_frame(img)
        assert n_raw == 1
        assert self._unpack_single(fragments) == (seq, pkt)

    def test_seq_zero(self):
        img = _make_qr_image(qr_pack(0, b"\xFF"))
        fragments, _ = decode_frame(img)
        assert self._unpack_single(fragments) == (0, b"\xFF")

    def test_seq_max(self):
        img = _make_qr_image(qr_pack(0xFFFF, b"\x00"))
        fragments, _ = decode_frame(img)
        assert self._unpack_single(fragments) == (0xFFFF, b"\x00")

    def test_empty_packet(self):
        img = _make_qr_image(qr_pack(42, b""))
        fragments, _ = decode_frame(img)
        assert self._unpack_single(fragments) == (42, b"")

    def test_all_byte_values(self):
        pkt = bytes(range(256))
        img = _make_qr_image(qr_pack(0x1234, pkt))
        fragments, _ = decode_frame(img)
        seq, decoded = self._unpack_single(fragments)
        assert seq == 0x1234
        assert decoded == pkt

    def test_blank_image_returns_empty(self):
        img = np.full((200, 200), 255, dtype=np.uint8)
        fragments, n_raw = decode_frame(img)
        assert fragments == []
        assert n_raw == 0

    def test_black_image_returns_empty(self):
        img = np.zeros((200, 200), dtype=np.uint8)
        fragments, n_raw = decode_frame(img)
        assert fragments == []
        assert n_raw == 0

    def test_grayscale_image_accepted(self):
        img = _make_qr_image(qr_pack(1, b"\x01\x02"))
        assert img.ndim == 2  # confirm grayscale
        fragments, _ = decode_frame(img)
        assert fragments != []

    def test_rgb_3channel_accepted(self):
        """RGB 3-channel array (as produced after BGR→RGB flip) decodes correctly."""
        gray = _make_qr_image(qr_pack(2, b"\x03\x04"))
        rgb = np.stack([gray, gray, gray], axis=-1)
        fragments, _ = decode_frame(rgb)
        assert self._unpack_single(fragments) == (2, b"\x03\x04")

    def test_scaled_up_image(self):
        """Larger cell size should still decode."""
        img = _make_qr_image(qr_pack(3, b"\xDE\xAD"))
        big = np.kron(img, np.ones((3, 3), dtype=np.uint8))
        fragments, _ = decode_frame(big)
        assert self._unpack_single(fragments) == (3, b"\xDE\xAD")

    def test_reticulum_like_payload(self):
        """Simulate a realistic 64-byte Reticulum announce packet."""
        pkt = bytes(range(64))
        img = _make_qr_image(qr_pack(0xABCD, pkt))
        fragments, _ = decode_frame(img)
        assert self._unpack_single(fragments) == (0xABCD, pkt)

    def test_fragment_fields_present(self):
        img = _make_qr_image(qr_pack(5, b"\xAA", frag_idx=1, frag_total=3))
        fragments, _ = decode_frame(img)
        assert len(fragments) == 1
        seq, chunk, frag_idx, frag_total = fragments[0]
        assert seq == 5 and chunk == b"\xAA"
        assert frag_idx == 1 and frag_total == 3

    def test_returns_tuple(self):
        img = np.full((100, 100), 255, dtype=np.uint8)
        result = decode_frame(img)
        assert isinstance(result, tuple)
        fragments, n_raw = result
        assert isinstance(fragments, list)
        assert isinstance(n_raw, int)
