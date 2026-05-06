# qrcodegen

QR code + barcode generator service at https://qrcode.chrisrmiller.com.
Single-container Flask app behind Cloudflare Tunnel.

**Stack:** Flask + qrcode + python-barcode + Pillow + Gunicorn.
**Tests:** pytest, run `python3 -m pytest`.
**Branch:** `master` (not `main`).

---

## Routes

All routes are defined in `qr_generator.py` on the `qr_bp` blueprint.

| Method | Path | Purpose | Response |
|---|---|---|---|
| GET | `/generator` | UI (form for the human-facing page) | HTML |
| POST | `/api/generate` | Form-encoded; full feature surface (QR + barcodes, all content types) | JSON envelope with base64 data URL |
| POST | `/api/generate/download` | Same as `/api/generate` but for downloads | Image bytes as attachment |
| **GET** | **`/api/qr`** | **Thin shim for `<img src>` embedding** | **Image bytes inline, `Cache-Control: public, max-age=86400, immutable`** |

The GET `/api/qr` endpoint is the one external services should use when
embedding a QR in an `<img>` tag — browsers can't `<img src>` a POST
endpoint, and the response is deterministic + cacheable so Cloudflare
serves repeats from the edge.

`/api/qr` query params: `data` (required), `size`, `format` (`png`|`svg`),
`margin`, `fg_color`, `bg_color`, `ec_level`. All other params have safe
defaults; invalid values fall back rather than 4xx (except missing `data`
which 400s).

## Conventions

- **Helpers in `qr_generator.py` are reusable.** Both POST handlers and
  the GET shim call the same `_build_qr_data`, `_make_qr_png`,
  `_make_qr_svg`, `_make_barcode_buf`. Don't fork the rendering paths;
  add params at the top of `_parse_common` if needed.
- **Input validation is whitelist-based.** `_safe_color`, `_safe_int`,
  `_safe_float` clamp/reject rather than trust. Any new query/form
  params should follow that pattern (see `_HEX_COLOR_RE`).
- **Security headers set globally** via `qr_bp.after_request`. Don't
  override per-route unless you really mean it.
- **Hard limits:** `MAX_DATA_LEN=2000`, `MIN_SIZE=100`, `MAX_SIZE=2000`.
  These bound rendering memory; raise carefully.

## Repo layout

```
qr_generator.py         # blueprint, routes, helpers
preview_app.py          # Flask app factory wiring the blueprint
gunicorn_config.py      # production WSGI config
templates/              # qr_generator.html (the /generator UI)
tests/                  # pytest suite — test_helpers.py + test_routes.py
docker-compose.yml      # single 'app' service
Dockerfile
docs/                   # INTEGRATIONS.md notes
```

## Deploy

```bash
git pull
docker compose up -d --build
```

Container port 8000, host port mapping in `docker-compose.yml`. Cloudflare
Tunnel ingress for `qrcode.chrisrmiller.com` points at the host port.

## Generic gotcha worth remembering

- **`docker compose restart` does NOT re-read `.env`** if/when env vars
  are added. Use `docker compose up -d --force-recreate app`.
- **Cloudflare can cache 4xx responses** — if a route looks broken from
  the public URL but works hitting the container directly, suspect edge
  cache before assuming a code bug.

## Consumers

- `lnklab.us` (URL shortener) embeds QRs via `GET /api/qr` with the
  short URL as `data`. Don't break the GET response shape (raw image
  bytes, image/* content type) without coordinating.
