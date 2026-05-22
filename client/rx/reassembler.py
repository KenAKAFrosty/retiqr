"""
Fragment reassembly for the QR downlink.

Each QR frame carries one fragment: (seq, chunk, frag_idx, frag_total).
Reassembler collects fragments by seq and emits the complete packet once
all frag_total fragments for that seq have arrived.

Duplicate reads (same QR frame decoded multiple times while it stays on screen)
are suppressed via a delivered-seq ring buffer. Lost fragments result in the
packet never being emitted — the upper Reticulum layer handles packet loss.
"""

from __future__ import annotations

import logging
from collections import deque

log = logging.getLogger(__name__)


_MAX_PENDING_SEQS = 32  # evict oldest incomplete assembly after this many pending seqs


class Reassembler:
    def __init__(self) -> None:
        self._chunks:    dict[int, dict[int, bytes]] = {}
        self._delivered: set[int] = set()
        self._delivered_order: deque[int] = deque(maxlen=64)

    def feed(self, seq: int, chunk: bytes, frag_idx: int, frag_total: int) -> bytes | None:
        """Feed one fragment. Returns the reassembled packet when complete, else None."""
        if seq in self._delivered:
            return None  # camera re-read of an already-delivered frame

        if frag_total == 1:
            self._mark_delivered(seq)
            return chunk

        if seq not in self._chunks:
            self._chunks[seq] = {}
            # evict oldest pending if too many are accumulating (lost fragments)
            if len(self._chunks) > _MAX_PENDING_SEQS:
                oldest = next(iter(self._chunks))
                del self._chunks[oldest]
                log.debug("evicted incomplete seq=0x%04x (lost fragment)", oldest)

        self._chunks[seq][frag_idx] = chunk

        if len(self._chunks[seq]) == frag_total:
            packet = b"".join(self._chunks[seq][i] for i in range(frag_total))
            del self._chunks[seq]
            self._mark_delivered(seq)
            log.debug("reassembled seq=0x%04x (%d frags, %d bytes)", seq, frag_total, len(packet))
            return packet

        log.debug("seq=0x%04x: %d/%d fragments", seq, len(self._chunks[seq]), frag_total)
        return None

    def _mark_delivered(self, seq: int) -> None:
        if len(self._delivered_order) == self._delivered_order.maxlen:
            self._delivered.discard(self._delivered_order[0])
        self._delivered_order.append(seq)
        self._delivered.add(seq)
