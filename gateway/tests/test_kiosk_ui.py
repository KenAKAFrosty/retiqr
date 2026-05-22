"""
Playwright browser tests for static/index.html.

Uses a local TCP echo server so tests are fully self-contained —
no live Reticulum node required.  The echo server bounces HDLC-framed
packets back through the gateway, triggering QR renders in the browser.
"""
import asyncio

import pytest
from playwright.async_api import async_playwright, Page

from gateway import build_app
from tests.conftest import echo_server, start_app, STATIC


# ─── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def gateway(event_loop):
    echo, tcp_port = await echo_server()
    runner, gw_port = await start_app(build_app("127.0.0.1", tcp_port, STATIC))
    yield f"http://127.0.0.1:{gw_port}"
    await runner.cleanup()
    echo.close()
    await echo.wait_closed()


@pytest.fixture
async def browser():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        yield b
        await b.close()


@pytest.fixture
async def page(gateway, browser):
    p = await browser.new_page(viewport={"width": 1280, "height": 800})
    await p.goto(gateway)
    await p.wait_for_timeout(800)  # allow WS handshake
    yield p
    await p.close()


# ─── helpers ─────────────────────────────────────────────────────────────────

_QR_CHECK_JS = """() => {
    const c = document.getElementById('qr-canvas');
    if (!c || c.width === 0) return false;
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let light = 0, dark = 0;
    for (let i = 0; i < d.length; i += 4) d[i] > 128 ? light++ : dark++;
    return light > 100 && dark > 100;
}"""

_INTERCEPT_WS_JS = """() => {
    window.__wsSent = [];
    const orig = WebSocket.prototype.send;
    WebSocket.prototype.send = function(d) {
        window.__wsSent.push(d);
        return orig.call(this, d);
    };
}"""


# ─── tests ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_page_loads(gateway):
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        p = await b.new_page()
        resp = await p.goto(gateway)
        assert resp.status == 200
        content = await p.content()
        assert "HdlcParser" in content
        assert "HidParser" in content
        await b.close()


@pytest.mark.asyncio
async def test_websocket_connects(page: Page):
    status = await page.inner_text("#ws-text")
    assert status == "connected"
    dot_class = await page.get_attribute("#ws-dot", "class")
    assert "on" in dot_class


@pytest.mark.asyncio
async def test_qr_renders_on_incoming_data(page: Page):
    # HID frame uplink bounces off echo server back as downlink → QR render
    await page.type("#hid-input", ">01020300<", delay=10)
    await page.wait_for_function(_QR_CHECK_JS, timeout=5000)
    assert await page.evaluate(_QR_CHECK_JS)


@pytest.mark.asyncio
async def test_hid_input_stays_focused(page: Page):
    focused = await page.evaluate("() => document.activeElement?.id")
    assert focused == "hid-input"


@pytest.mark.asyncio
async def test_hid_input_refocuses_after_click(page: Page):
    await page.click("body")
    await page.wait_for_timeout(400)  # refocus interval is 250ms
    focused = await page.evaluate("() => document.activeElement?.id")
    assert focused == "hid-input"


@pytest.mark.asyncio
async def test_valid_hid_frame_forwarded_to_websocket(page: Page):
    await page.evaluate(_INTERCEPT_WS_JS)
    await page.type("#hid-input", ">01020300<", delay=10)
    await page.wait_for_timeout(200)
    count = await page.evaluate("() => window.__wsSent.length")
    assert count == 1


@pytest.mark.asyncio
async def test_bad_crc_hid_frame_dropped(page: Page):
    await page.evaluate(_INTERCEPT_WS_JS)
    await page.type("#hid-input", ">010203FF<", delay=10)  # CRC should be 00
    await page.wait_for_timeout(200)
    count = await page.evaluate("() => window.__wsSent.length")
    assert count == 0


@pytest.mark.asyncio
async def test_rx_counter_increments(page: Page):
    before = int(await page.inner_text("#rx-count"))
    await page.type("#hid-input", ">01020300<", delay=10)
    await page.wait_for_timeout(600)
    after = int(await page.inner_text("#rx-count"))
    assert after > before


@pytest.mark.asyncio
async def test_tx_counter_increments(page: Page):
    before = int(await page.inner_text("#tx-count"))
    await page.type("#hid-input", ">01020300<", delay=10)
    await page.wait_for_timeout(200)
    after = int(await page.inner_text("#tx-count"))
    assert after > before


@pytest.mark.asyncio
async def test_idle_message_shown_when_no_data(page: Page):
    await page.wait_for_timeout(500)  # let queue drain
    visible = await page.is_visible("#idle-msg")
    assert visible
