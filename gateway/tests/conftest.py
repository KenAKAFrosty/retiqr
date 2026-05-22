import asyncio
from pathlib import Path

import pytest
from aiohttp import web

from gateway import build_app

STATIC = Path(__file__).parent.parent / "static"


async def echo_server(host: str = "127.0.0.1") -> tuple[asyncio.Server, int]:
    async def _echo(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        try:
            while chunk := await r.read(4096):
                w.write(chunk)
                await w.drain()
        finally:
            w.close()

    srv = await asyncio.start_server(_echo, host, 0)
    return srv, srv.sockets[0].getsockname()[1]


async def start_app(app: web.Application) -> tuple[web.AppRunner, int]:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    return runner, port
