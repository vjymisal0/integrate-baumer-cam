# Integrate Baumer Cam

Captures images from an industrial camera (Baumer NeoAPI), webcam, or RTSP feed, submits them to a headless inspection API, and drives output indicators on a Mitsubishi FX5U PLC over Modbus TCP.

## Features

- **Three image sources** — Baumer industrial camera, USB/built-in webcam, or RTSP stream
- **Modbus TCP button trigger** — hardware button press on a Mitsubishi FX5U PLC starts a capture cycle
- **Modbus TCP output** — inspection result drives PLC output coils atomically:
  - `NA` → Y0 ON
  - `Pass` → Y1 ON
  - `Fail` → Y2 ON
- **Lossless WebP** — every capture is saved locally and uploaded at full quality
- **Auto-reconnect** — recovers from PLC connection drops without restarting

## Hardware

| Device | Role |
|---|---|
| Mitsubishi FX5U-32M PLC | Button input (X0 / IN 0) + result output (Y0–Y2) |
| Webcam / Baumer camera | Image capture |

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) for dependency management
- Baumer camera drivers (only required when `SOURCE_TYPE=baumer`)

## Setup

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env with your API credentials, source type, and Modbus settings
```

## Configuration

All configuration is via `.env`. Key variables:

### Image Source
| Variable | Default | Description |
|---|---|---|
| `SOURCE_TYPE` | `baumer` | `baumer`, `rtsp`, or `webcam` |
| `RTSP_URL` | — | RTSP stream URL (required when `SOURCE_TYPE=rtsp`) |
| `WEBCAM_ID` | `0` | Camera index (`0`, `1`) or name substring (`"Logitech"`) |

### API
| Variable | Description |
|---|---|
| `API_URL` | Inspection API endpoint |
| `API_KEY` | API authentication key |
| `WORKSPACE_ID` | Target workspace |
| `PRODUCT_NAME` | Product being inspected |
| `SESSION_NAME` | Inspection session name |
| `ARTICLE_NAME` | Article/variant name |

### Modbus (Mitsubishi FX5U)
| Variable | Default | Description |
|---|---|---|
| `MODBUS_TRIGGER` | `false` | Set `true` to enable hardware button trigger |
| `MODBUS_HOST` | `192.168.7.120` | PLC IP address |
| `MODBUS_PORT` | `502` | Modbus TCP port |
| `MODBUS_ADDRESS` | `0` | Input address for button (X0 = 0) |
| `MODBUS_USE_COIL` | `false` | `false` = discrete input (X), `true` = coil (M/Y) |
| `MODBUS_POLL_INTERVAL` | `0.1` | Button poll rate in seconds |
| `MODBUS_OUTPUT_ADDRESS` | `0` | First output coil address (Y0 = 0) |

## Usage

```bash
uv run python main.py
```

### Controls
| Input | Action |
|---|---|
| Hardware button (X0) | Capture + inspect (when `MODBUS_TRIGGER=true`) |
| `c` + Enter | Manual capture + inspect |
| `x` + Enter | Exit cleanly |

### Cycle flow
```
Button pressed (X0)
  → Capture image from source
  → Save locally as ./images/capture_YYYYMMDD-HHMMSS.webp
  → Upload to inspection API
  → Write result to PLC output coils (FC15):
      NA   → Y0=ON,  Y1=OFF, Y2=OFF
      Pass → Y0=OFF, Y1=ON,  Y2=OFF
      Fail → Y0=OFF, Y1=OFF, Y2=ON
```

## Project Structure

```
main.py            — Entry point and orchestration
modbus_button.py   — Modbus TCP button polling and result output
source_base.py     — Abstract ImageSource interface
source_baumer.py   — Baumer NeoAPI camera source
source_rtsp.py     — RTSP stream source
source_webcam.py   — USB/built-in webcam source
libs/              — Baumer NeoAPI wheel (offline install)
.env.example       — Environment variable template
```
