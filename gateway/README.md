# gateway

aiohttp server that serves the kiosk web page and splices WebSocket ↔ Reticulum TCP. Protocol-blind — no Reticulum knowledge required.

## Running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python gateway.py --target-host <reticulum-node> --target-port 4242
# page served at http://0.0.0.0:8080/
```

| Flag | Default | Description |
|------|---------|-------------|
| `--target-host` | *(required)* | Reticulum TCP interface host |
| `--target-port` | *(required)* | Reticulum TCP interface port |
| `--host` | `0.0.0.0` | Listen address |
| `--port` | `8080` | Listen port |
| `--log-level` | `INFO` | `DEBUG`, `INFO`, `WARNING` |

## Docker

Build and run from the **repo root** (the build context needs access to `shared/framing.py`):

```bash
docker build -f gateway/Dockerfile -t retiqr-gateway .
docker run -p 8080:8080 retiqr-gateway --target-host <reticulum-node> --target-port 4242
```

Or with Docker Compose — edit `target-host` in `docker-compose.yml` first:

```bash
docker compose -f gateway/docker-compose.yml up
```

## Testing

```bash
pip install -r requirements-dev.txt && playwright install chromium
pytest                          # full suite (45 tests, ~13s)
pytest tests/test_framing.py    # framing unit tests, no I/O
pytest tests/test_gateway.py    # async WebSocket relay tests
pytest tests/test_kiosk_ui.py   # Playwright browser tests
```

No live Reticulum node needed — tests spin up internal echo servers.

## Structure

```
gateway.py          WebSocket ↔ TCP splice, serves static/
framing.py          Shim → shared/framing.py
static/index.html   Single-page kiosk UI
tests/
  conftest.py       Echo server + app runner fixtures
  test_framing.py
  test_gateway.py
  test_kiosk_ui.py
```
