"""Tests for rx/reassembler.py."""
import pytest
from rx.reassembler import Reassembler


class TestReassembler:
    def setup_method(self):
        self.r = Reassembler()

    def test_single_fragment_delivered_immediately(self):
        result = self.r.feed(1, b"\xAB\xCD", frag_idx=0, frag_total=1)
        assert result == b"\xAB\xCD"

    def test_empty_single_fragment(self):
        assert self.r.feed(0, b"", frag_idx=0, frag_total=1) == b""

    def test_two_fragments_in_order(self):
        assert self.r.feed(1, b"hello", frag_idx=0, frag_total=2) is None
        assert self.r.feed(1, b"world", frag_idx=1, frag_total=2) == b"helloworld"

    def test_two_fragments_out_of_order(self):
        assert self.r.feed(2, b"world", frag_idx=1, frag_total=2) is None
        assert self.r.feed(2, b"hello", frag_idx=0, frag_total=2) == b"helloworld"

    def test_three_fragments(self):
        assert self.r.feed(3, b"c", frag_idx=2, frag_total=3) is None
        assert self.r.feed(3, b"a", frag_idx=0, frag_total=3) is None
        assert self.r.feed(3, b"b", frag_idx=1, frag_total=3) == b"abc"

    def test_interleaved_sequences(self):
        assert self.r.feed(10, b"x", frag_idx=0, frag_total=2) is None
        assert self.r.feed(11, b"y", frag_idx=0, frag_total=2) is None
        assert self.r.feed(10, b"z", frag_idx=1, frag_total=2) == b"xz"
        assert self.r.feed(11, b"w", frag_idx=1, frag_total=2) == b"yw"

    def test_lost_fragment_never_delivers(self):
        self.r.feed(5, b"first", frag_idx=0, frag_total=2)
        assert self.r.feed(6, b"other", frag_idx=0, frag_total=1) == b"other"
        assert 5 in self.r._chunks

    def test_pending_eviction_on_overflow(self):
        from rx.reassembler import _MAX_PENDING_SEQS
        # fill up pending slots with incomplete 2-fragment packets
        for i in range(_MAX_PENDING_SEQS + 1):
            self.r.feed(i, b"x", frag_idx=0, frag_total=2)
        # oldest entry should have been evicted to cap memory
        assert len(self.r._chunks) <= _MAX_PENDING_SEQS

    def test_pending_cleared_after_complete(self):
        self.r.feed(7, b"a", frag_idx=0, frag_total=2)
        self.r.feed(7, b"b", frag_idx=1, frag_total=2)
        assert 7 not in self.r._chunks

    def test_single_fragment_not_delivered_twice(self):
        assert self.r.feed(20, b"data", frag_idx=0, frag_total=1) == b"data"
        assert self.r.feed(20, b"data", frag_idx=0, frag_total=1) is None

    def test_multi_fragment_not_delivered_twice(self):
        self.r.feed(30, b"a", frag_idx=0, frag_total=2)
        assert self.r.feed(30, b"b", frag_idx=1, frag_total=2) == b"ab"
        # repeated reads of frag 1 after delivery
        assert self.r.feed(30, b"b", frag_idx=1, frag_total=2) is None
        assert self.r.feed(30, b"a", frag_idx=0, frag_total=2) is None

    def test_large_packet_roundtrip(self):
        from framing import qr_fragments, qr_unpack
        pkt = bytes(range(200))
        frags = qr_fragments(99, pkt)
        result = None
        for f in frags:
            seq, chunk, frag_idx, frag_total = qr_unpack(f)
            result = self.r.feed(seq, chunk, frag_idx, frag_total)
        assert result == pkt
