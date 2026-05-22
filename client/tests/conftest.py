"""Shared fixtures for ret-kiosk tests."""
import asyncio
import pytest


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def reticulum_client(host: str, port: int):
    """Open a raw TCP connection to the bridge (simulates Reticulum)."""
    return await asyncio.open_connection(host, port)
