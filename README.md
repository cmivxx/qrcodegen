```
 ██████╗ ██████╗      ██████╗ ██████╗ ██████╗ ███████╗
██╔═══██╗██╔══██╗    ██╔════╝██╔═══██╗██╔══██╗██╔════╝
██║   ██║██████╔╝    ██║     ██║   ██║██║  ██║█████╗
██║▄▄ ██║██╔══██╗    ██║     ██║   ██║██║  ██║██╔══╝
╚██████╔╝██║  ██║    ╚██████╗╚██████╔╝██████╔╝███████╗
 ╚══▀▀═╝ ╚═╝  ╚═╝     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝

 ██████╗ ███████╗███╗   ██╗███████╗██████╗  █████╗ ████████╗ ██████╗ ██████╗
██╔════╝ ██╔════╝████╗  ██║██╔════╝██╔══██╗██╔══██╗╚══██╔══╝██╔═══██╗██╔══██╗
██║  ███╗█████╗  ██╔██╗ ██║█████╗  ██████╔╝███████║   ██║   ██║   ██║██████╔╝
██║   ██║██╔══╝  ██║╚██╗██║██╔══╝  ██╔══██╗██╔══██║   ██║   ██║   ██║██╔══██╗
╚██████╔╝███████╗██║ ╚████║███████╗██║  ██║██║  ██║   ██║   ╚██████╔╝██║  ██║
 ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
```

<div align="center">

**A beautiful, self-hosted QR code & barcode generator — built for speed, security, and style.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-qrcode.chrisrmiller.com-6c63ff?style=for-the-badge&logo=firefox)](https://qrcode.chrisrmiller.com)
[![Python](https://img.shields.io/badge/Python-3.9+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ed?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Cloudflare](https://img.shields.io/badge/Cloudflare-Tunnel-f38020?style=for-the-badge&logo=cloudflare&logoColor=white)](https://www.cloudflare.com/products/tunnel/)
[![License](https://img.shields.io/badge/License-MIT-00d4aa?style=for-the-badge)](LICENSE)

</div>

---

## ✨ Features

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   📱  QR Codes          📊  1D Barcodes       🎨  Customization │
│   ─────────────         ────────────────       ─────────────── │
│   Plain Text            Code 128               Foreground color │
│   URL / Bookmark        Code 39                Background color │
│   Email                 EAN-13 / EAN-8         Size (100–2000px)│
│   Phone Number          UPC-A                  Margin control   │
│   SMS Message           ITF                    Error correction │
│   Wi-Fi Network         Codabar                PNG or SVG output│
│   Contact (MECARD)                                              │
│   Geo Location          🌙  Dark & Light theme                  │
│   Calendar Event        ⚡  Live preview                        │
│                         💾  One-click download                  │
│                         🔗  Shareable API URLs                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/)

### Deploy in 60 seconds

```bash
# 1. Clone the repo
git clone git@github.com:cmivxx/qrcodegen.git
cd qrcodegen

# 2. Start the stack
docker compose up -d

# 3. Open your browser
open http://localhost
```

> **Production?** Front it with Cloudflare (or your reverse proxy of choice) for TLS, WAF, and rate limiting.

---

## 🏗️ Architecture

```
                       ┌────────────────────────────────┐
   Browser / Client ──►│  Cloudflare (or proxy of       │
                       │  choice)                       │
                       │                                │
                       │  • TLS termination             │
                       │  • WAF & rate limiting         │
                       │  • DDoS protection             │
                       │  • Gzip / HTTP/2               │
                       └────────────────┬───────────────┘
                                        │
                       ┌────────────────▼───────────────┐
                       │  Python 3.9 + Gunicorn         │
                       │  (4 workers · non-root user)   │
                       │                                │
                       │  /generator   → UI             │
                       │  /api/generate → PNG/SVG       │
                       │  /api/generate/download        │
                       │                                │
                       │  Adds CSP + security headers   │
                       │  via Flask after_request hook  │
                       └────────────────────────────────┘
```

The app is intentionally a **single container** — it relies on an upstream proxy (Cloudflare, Traefik, etc.) for TLS, rate limiting, and edge concerns. This keeps the deployment small, the moving parts few, and the responsibilities clean.

### Project structure

```
qrcodegen/
├── qr_generator.py          # Flask Blueprint — all generation logic
├── preview_app.py           # WSGI entry point (gunicorn target)
├── gunicorn_config.py       # 4 workers, 30s timeout, stdout logs
├── Dockerfile               # python:3.9-slim, non-root appuser
├── docker-compose.yml       # single-service stack
├── requirements.txt
├── tests/                   # pytest suite (helpers + routes)
├── docs/
│   └── INTEGRATIONS.md      # URL shortener integration contract
└── templates/
    └── qr_generator.html    # Single-page UI (no JS framework needed)
```

---

## 🔌 API Reference

All generation is available via a simple `POST` request — useful for integrations and automation.

### Generate (preview)

```
POST /api/generate
Content-Type: application/x-www-form-urlencoded
```

Returns `{ "image": "data:<mime>;base64,...", "mime": "image/png" }`.

### Download

```
POST /api/generate/download
```

Returns the file directly as a binary attachment.

### Common parameters

| Parameter | Values | Default | Description |
|---|---|---|---|
| `format` | `qrcode`, `code128`, `code39`, `ean13`, `ean8`, `upca`, `itf`, `codabar` | `qrcode` | Barcode format |
| `output_format` | `png`, `svg` | `png` | Output format |
| `size` | `100`–`2000` | `300` | Image size in pixels |
| `margin` | `0`–`10` | `4` | Quiet zone (modules) |
| `ec_level` | `L`, `M`, `Q`, `H` | `M` | QR error correction |
| `fg_color` | `#rrggbb` | `#000000` | Foreground color |
| `bg_color` | `#rrggbb` | `#ffffff` | Background color |

### QR content parameters

<details>
<summary><strong>Plain Text</strong></summary>

```
content_type=text&text=Hello+World
```
</details>

<details>
<summary><strong>URL</strong></summary>

```
content_type=url&url=https://example.com
```
</details>

<details>
<summary><strong>Email</strong></summary>

```
content_type=email&email_addr=user@example.com&email_subject=Hello&email_body=Hi+there
```
</details>

<details>
<summary><strong>Phone</strong></summary>

```
content_type=phone&phone=%2B15550001234
```
</details>

<details>
<summary><strong>SMS</strong></summary>

```
content_type=sms&sms_number=%2B15550001234&sms_body=Hello
```
</details>

<details>
<summary><strong>Wi-Fi</strong></summary>

```
content_type=wifi&wifi_ssid=MyNetwork&wifi_password=secret&wifi_auth=WPA
```

`wifi_auth` accepts: `WPA`, `WEP`, `nopass`
</details>

<details>
<summary><strong>Contact (MECARD)</strong></summary>

```
content_type=contact&contact_name=Jane+Doe&contact_phone=%2B15550001234&contact_email=jane@example.com&contact_org=Acme
```
</details>

<details>
<summary><strong>Geo Location</strong></summary>

```
content_type=geo&geo_lat=37.7749&geo_lng=-122.4194&geo_query=San+Francisco
```
</details>

<details>
<summary><strong>Calendar Event</strong></summary>

```
content_type=calendar&cal_summary=Team+Meeting&cal_start=2026-06-01T09:00&cal_end=2026-06-01T10:00&cal_location=Room+4B
```
</details>

### Example curl

```bash
curl -s -X POST https://qrcode.chrisrmiller.com/api/generate \
  -d "format=qrcode&content_type=url&url=https://chrisrmiller.com&size=400&ec_level=H&output_format=png" \
  | python3 -c "import sys,json,base64; d=json.load(sys.stdin); open('qr.png','wb').write(base64.b64decode(d['image'].split(',')[1]))"
```

---

## 🔒 Security

```
┌─ Input Validation ───────────────────────────────────────────┐
│  ✓ Colors validated against #rrggbb regex before PIL         │
│  ✓ Size clamped 100–2000px server-side (prevents OOM)        │
│  ✓ All string inputs length-limited                          │
│  ✓ format / content_type / wifi_auth use strict allowlists   │
│  ✓ Errors never leak exception details to clients            │
├─ HTTP Headers (set by Flask after_request) ──────────────────┤
│  ✓ Content-Security-Policy (script/img/connect locked down)  │
│  ✓ X-Frame-Options: SAMEORIGIN                               │
│  ✓ X-Content-Type-Options: nosniff                           │
│  ✓ Referrer-Policy: strict-origin-when-cross-origin          │
│  ✓ Permissions-Policy (geo/mic/camera blocked)               │
├─ Container ──────────────────────────────────────────────────┤
│  ✓ Runs as non-root appuser (UID 1001)                       │
│  ✓ No database — zero persistent attack surface              │
│  ✓ Stateless — restart at will, no migrations                │
├─ Edge (delegated to Cloudflare or your reverse proxy) ───────┤
│  ✓ TLS termination                                           │
│  ✓ WAF & rate limiting                                       │
│  ✓ DDoS protection                                           │
└──────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Configuration

### gunicorn — `gunicorn_config.py`

| Setting | Default | Description |
|---|---|---|
| `workers` | `4` | Gunicorn worker processes |
| `timeout` | `30` | Worker timeout (seconds) |

---

## 🛠️ Local Development

```bash
# Install deps
pip install -r requirements.txt

# Run dev server (auto-reload, port 5050)
python3 preview_app.py
```

Open [http://localhost:5050/generator](http://localhost:5050/generator).

---

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.9 |
| Web framework | Flask 3.x |
| QR generation | [qrcode](https://github.com/lincolnloop/python-qrcode) + Pillow |
| 1D barcodes | [python-barcode](https://github.com/WhyNotHugo/python-barcode) |
| WSGI server | Gunicorn |
| Containerization | Docker + Compose |
| Analytics | Google Analytics 4 |
| UI | Vanilla HTML/CSS/JS (zero JS framework) |

---

## 🔗 Integrations

The QR generator runs fully standalone, but has a documented seam for an
**optional URL shortener** that adds click analytics and editable
destinations for printed QR codes. Shortener is a separate, independently
deployable app — the QR generator stays stateless either way.

→ See [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) for the API contract,
env vars, and failure behavior.

---

## 📄 License

MIT © [ChrisRMiller.com](https://chrisrmiller.com)

---

<div align="center">

Built with ♥ by **[ChrisRMiller.com](https://chrisrmiller.com)**

</div>
