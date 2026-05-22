"""Async integration tests for gateway.py — WebSocket ↔ TCP relay."""
import asyncio

import pytest
import aiohttp
from aiohttp import WSMsgType

from gateway import build_app
from tests.conftest import echo_server, start_app, STATIC


@pytest.mark.asyncio
async def test_bytes_relay():
    echo, tcp_port = await echo_server()
    async with echo:
        runner, gw_port = await start_app(build_app("127.0.0.1", tcp_port, STATIC))
        try:
            async with aiohttp.ClientSession() as s:
                async with s.ws_connect(f"http://127.0.0.1:{gw_port}/ws") as ws:
                    await ws.send_bytes(b"\xDE\xAD\xBE\xEF")
                    msg = await asyncio.wait_for(ws.receive(), timeout=3)
                    assert msg.type == WSMsgType.BINARY
                    assert msg.data == b"\xDE\xAD\xBE\xEF"
        finally:
            await runner.cleanup()


@pytest.mark.asyncio
async def test_hdlc_framed_bytes_relay():
    """Gateway passes HDLC-framed bytes through unchanged."""
    from framing import hdlc_encode, hdlc_decode_stream
    echo, tcp_port = await echo_server()
    async with echo:
        runner, gw_port = await start_app(build_app("127.0.0.1", tcp_port, STATIC))
        try:
            packet = bytes([0x01, 0x7E, 0x7D, 0xFF])
            async with aiohttp.ClientSession() as s:
                async with s.ws_connect(f"http://127.0.0.1:{gw_port}/ws") as ws:
                    await ws.send_bytes(hdlc_encode(packet))
                    msg = await asyncio.wait_for(ws.receive(), timeout=3)
                    assert msg.type == WSMsgType.BINARY
                    assert hdlc_decode_stream(msg.data) == [packet]
        finally:
            await runner.cleanup()


@pytest.mark.asyncio
async def test_tcp_connect_failure():
    """WebSocket closes cleanly when TCP target is unreachable."""
    runner, gw_port = await start_app(build_app("127.0.0.1", 19998, STATIC))
    try:
        async with aiohttp.ClientSession() as s:
            async with s.ws_connect(f"http://127.0.0.1:{gw_port}/ws") as ws:
                msg = await asyncio.wait_for(ws.receive(), timeout=5)
                assert msg.type == WSMsgType.CLOSE
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_concurrent_connections():
    """Multiple simultaneous WebSocket connections each get their own TCP link."""
    echo, tcp_port = await echo_server()
    async with echo:
        runner, gw_port = await start_app(build_app("127.0.0.1", tcp_port, STATIC))
        try:
            async with aiohttp.ClientSession() as s:
                conns = [await s.ws_connect(f"http://127.0.0.1:{gw_port}/ws")
                         for _ in range(3)]
                payloads = [bytes([i, i + 1, i + 2]) for i in range(3)]
                for ws, pkt in zip(conns, payloads):
                    await ws.send_bytes(pkt)
                for ws, pkt in zip(conns, payloads):
                    msg = await asyncio.wait_for(ws.receive(), timeout=3)
                    assert msg.data == pkt
                for ws in conns:
                    await ws.close()
        finally:
            await runner.cleanup()


@pytest.mark.asyncio
async def test_ws_close_on_tcp_drop():
    """When the TCP side drops, the WebSocket is closed."""
    async def _close_immediately(r, w):
        w.close()

    srv = await asyncio.start_server(_close_immediately, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    async with srv:
        runner, gw_port = await start_app(build_app("127.0.0.1", port, STATIC))
        try:
            async with aiohttp.ClientSession() as s:
                async with s.ws_connect(f"http://127.0.0.1:{gw_port}/ws") as ws:
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    assert msg.type == WSMsgType.CLOSE
        finally:
            await runner.cleanup()


@pytest.mark.asyncio
async def test_index_html_served():
    runner, gw_port = await start_app(build_app("127.0.0.1", 19998, STATIC))
    try:
        async with aiohttp.ClientSession() as s:
            resp = await s.get(f"http://127.0.0.1:{gw_port}/")
            assert resp.status == 200
            text = await resp.text()
            assert "HdlcParser" in text
            assert "HidParser" in text
    finally:
        await runner.cleanup()
