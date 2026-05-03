# Integrations

This document describes optional external services the QR Code Generator
can integrate with. **None of these are required** — the app is designed
to run fully standalone and gracefully degrade when an integration is
unavailable.

---

## URL Shortener (planned)

When deployed, the shortener will be a **separate application** with its
own database. The QR generator will optionally route `URL` content type
through it to enable click analytics on physical QR codes — without ever
gaining its own persistent state.

### Status

🚧 **Not yet implemented.** This document defines the contract so the
two services can be built independently and integrated cleanly later.

### Why route through a shortener?

A printed QR code is immutable. Routing the encoded URL through a
shortener gives you:

- **Editable destinations** — fix typos, retire campaigns, or re-target
  a printed code without reprinting.
- **Click analytics** — scan counts, geographic distribution, device
  type, time-of-day patterns.
- **Smaller payloads** — short URLs produce denser, easier-to-scan QR
  codes than long tracking URLs with UTM parameters.

### Architecture

```
┌────────────────────┐         ┌────────────────────┐
│  QR Generator      │  HTTPS  │  URL Shortener     │
│  (this app)        │ ──────► │  (separate app)    │
│                    │         │                    │
│  Stateless         │         │  MySQL backed      │
│  No DB             │         │  Owns: links,      │
│  Talks via         │         │         clicks     │
│  HTTP only         │         │                    │
└────────────────────┘         └────────────────────┘
                                        │
                                        ▼
                               ┌────────────────────┐
                               │  Existing MySQL    │
                               │  host (shared)     │
                               │  Schema:           │
                               │   shortener_links  │
                               │   shortener_clicks │
                               └────────────────────┘
```

### Environment variables (QR generator side)

Set on the QR generator container. **All three must be set for the
feature to activate.** If any is unset, the toggle does not appear in
the UI and the generator behaves as it does today.

| Variable | Example | Description |
|---|---|---|
| `SHORTENER_API_URL` | `https://short.chrisrmiller.com/api` | Internal-facing API endpoint |
| `SHORTENER_API_KEY` | `sk_live_…` | Bearer token for service-to-service auth |
| `SHORTENER_PUBLIC_URL` | `https://qr.chrisrmiller.com` | Short domain shown in the UI and encoded in the QR |

### API contract

#### Create short link

```
POST {SHORTENER_API_URL}/links
Authorization: Bearer {SHORTENER_API_KEY}
Content-Type: application/json

{
  "url":      "https://example.com/some/long/path?utm_campaign=...",
  "source":   "qrgen",
  "metadata": {
    "content_type": "url",
    "user_agent":   "...",
    "ip_hash":      "..."
  }
}
```

Response **201 Created**:

```json
{
  "id":        "abc123",
  "short_url": "https://qr.chrisrmiller.com/abc123",
  "long_url":  "https://example.com/some/long/path?utm_campaign=...",
  "created":   "2026-05-03T12:34:56Z"
}
```

Response **4xx/5xx**: any non-2xx response, timeout, or connection
error → QR generator falls back to encoding the original long URL and
logs a warning. **The QR generator never errors out due to shortener
issues.**

#### Reserved fields

- `source` — always `"qrgen"` from this app. Lets the shortener
  attribute clicks back to "originated from QR code" vs other sources
  added later (manual UI, API clients, etc.).
- `metadata` — opaque object, stored as JSON on the link row. Future
  fields can be added without breaking the contract.

### Failure behavior (QR generator)

| Condition | Behavior |
|---|---|
| Env vars unset | Toggle hidden in UI; URL encoded as-is |
| Toggle off | URL encoded as-is (no API call) |
| API timeout (> 3s) | Fall back to long URL; log warning |
| API returns non-2xx | Fall back to long URL; log warning |
| Network error | Fall back to long URL; log warning |

The user always gets a working QR code. Tracking is best-effort.

### Implementation seams

Where the integration will plug into the QR generator:

| File | Change |
|---|---|
| `shortener_client.py` *(new)* | Thin HTTP client: `shorten(url, metadata) → short_url` with timeout + fallback |
| `qr_generator.py` | Read env vars at module load; pass `shortener_enabled` flag to template; call `shortener_client.shorten()` from `_build_qr_data()` URL branch when `track_scans=on` form field is present |
| `templates/qr_generator.html` | Conditional checkbox under URL content type when `shortener_enabled` is true |
| `requirements.txt` | Add `requests` (or stdlib `urllib`) |
| `nginx/nginx.conf` | No change — shortener has its own deployment |

### Schema notes (shortener side, for reference)

The shortener owns these tables. Listed here so the QR repo's docs are
the single source of truth for the integration:

```sql
CREATE TABLE shortener_links (
  id          VARCHAR(16)  PRIMARY KEY,         -- short slug
  long_url    TEXT         NOT NULL,
  source      VARCHAR(32)  NOT NULL,            -- 'qrgen', 'manual', etc.
  metadata    JSON,
  created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  expires_at  TIMESTAMP    NULL,
  active      BOOLEAN      DEFAULT TRUE,
  INDEX idx_source (source),
  INDEX idx_created (created_at)
);

CREATE TABLE shortener_clicks (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  link_id     VARCHAR(16)  NOT NULL,
  clicked_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  ip_hash     CHAR(64),                         -- SHA256, never raw IP (GDPR)
  user_agent  VARCHAR(500),
  referrer    VARCHAR(500),
  country     CHAR(2),                          -- ISO 3166-1 alpha-2
  FOREIGN KEY (link_id) REFERENCES shortener_links(id) ON DELETE CASCADE,
  INDEX idx_link_time (link_id, clicked_at)
);
```

### Open questions (resolve when building the shortener)

- [ ] Slug format: random base62 vs. content-addressable hash?
- [ ] Slug length: 6 chars (~57B combos) vs. 8 chars (~218T)?
- [ ] Rate limit on link creation per-IP and per-API-key?
- [ ] Safe Browsing API check on creation to block malware/phishing URLs?
- [ ] Soft-delete vs. hard-delete for retired links?
- [ ] Bulk export for analytics (CSV/JSON)?
