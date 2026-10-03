import io
import math
import re
import sys
import json as _json
import logging
import base64
import qrcode
import qrcode.image.svg
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
from PIL import Image, ImageDraw
import barcode
from barcode.writer import ImageWriter, SVGWriter
from flask import Blueprint, render_template, request, send_file, jsonify

qr_bp = Blueprint('qr', __name__)


class _JsonFormatter(logging.Formatter):
    def format(self, record):
        d = {'time': self.formatTime(record, '%Y-%m-%dT%H:%M:%S') + f'.{record.msecs:03.0f}'}
        d.update(record.msg if isinstance(record.msg, dict) else {'message': record.getMessage()})
        return _json.dumps(d)

_log = logging.getLogger('qrcodegen')
_log.propagate = False
_log.setLevel(logging.INFO)
_h = logging.StreamHandler(sys.stdout)
_h.setFormatter(_JsonFormatter())
_log.addHandler(_h)


def _req_source():
    ref = request.referrer or ''
    return 'ui' if '/generator' in ref else 'api'


def _log_event(**kwargs):
    _log.info(kwargs)


_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com; "
    "img-src 'self' data: https://www.google-analytics.com; "
    "connect-src 'self' https://www.google-analytics.com https://analytics.google.com; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)


@qr_bp.after_request
def _security_headers(resp):
    resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    resp.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    resp.headers.setdefault('Content-Security-Policy', _CSP)
    return resp


@qr_bp.app_errorhandler(413)
def _too_large(_e):
    return jsonify({'error': 'Upload too large. Logo must be 2 MB or smaller.'}), 413


ERROR_LEVELS = {'L': ERROR_CORRECT_L, 'M': ERROR_CORRECT_M, 'Q': ERROR_CORRECT_Q, 'H': ERROR_CORRECT_H}

BARCODE_FORMATS = {
    'code128': 'code128',
    'code39': 'code39',
    'ean13': 'ean13',
    'ean8': 'ean8',
    'upca': 'upca',
    'itf': 'itf',
    'codabar': 'codabar',
}

ALLOWED_CONTENT_TYPES = {'text', 'url', 'email', 'phone', 'sms', 'wifi', 'contact', 'geo', 'calendar'}
ALLOWED_OUTPUT_FMTS = {'png', 'svg'}
ALLOWED_WIFI_AUTH = {'WPA', 'WEP', 'nopass'}
MAX_DATA_LEN = 2000
MAX_LOGO_BYTES = 2 * 1024 * 1024          # 2 MB upload cap
MAX_LOGO_PIXELS = 4096 * 4096             # reject decompression bombs before decoding
ALLOWED_LOGO_FORMATS = {'PNG', 'JPEG', 'WEBP', 'GIF'}
LOGO_SIZE_MIN, LOGO_SIZE_MAX, LOGO_SIZE_DEFAULT = 10, 30, 20  # % of code width
MAX_SIZE = 2000
MIN_SIZE = 100
_HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')


def _safe_color(value, default):
    return value if _HEX_COLOR_RE.match(value or '') else default


def _safe_int(value, default, lo, hi):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _safe_float(value, default, lo, hi):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _build_qr_data(form):
    content_type = form.get('content_type', 'text')
    if content_type not in ALLOWED_CONTENT_TYPES:
        return ''

    if content_type == 'url':
        url = form.get('url', '')[:MAX_DATA_LEN]
        # ── Future: URL shortener integration ─────────────────────────────
        # When the shortener app is deployed, a "Track scans" toggle will
        # appear in the UI for this content type. If the toggle is on AND
        # the SHORTENER_API_URL env var is set, replace `url` here with the
        # short URL returned from the shortener service.
        #
        # Env vars (read at app startup, not here):
        #   SHORTENER_API_URL     e.g. https://short.chrisrmiller.com/api
        #   SHORTENER_API_KEY     bearer token for service-to-service auth
        #   SHORTENER_PUBLIC_URL  short domain shown in the UI / encoded in QR
        #
        # Contract & failure behavior: see docs/INTEGRATIONS.md
        # Implementation: shortener_client.py (to be added)
        # ──────────────────────────────────────────────────────────────────
        return url

    if content_type == 'text':
        return form.get('text', '')[:MAX_DATA_LEN]

    if content_type == 'email':
        addr = form.get('email_addr', '')[:200]
        subj = form.get('email_subject', '')[:200]
        body = form.get('email_body', '')[:500]
        parts = []
        if subj:
            parts.append(f'subject={subj}')
        if body:
            parts.append(f'body={body}')
        return f"mailto:{addr}{'?' + '&'.join(parts) if parts else ''}"

    if content_type == 'phone':
        return f"tel:{form.get('phone', '')[:30]}"

    if content_type == 'sms':
        num = form.get('sms_number', '')[:30]
        msg = form.get('sms_body', '')[:500]
        return f"smsto:{num}:{msg}" if msg else f"smsto:{num}"

    if content_type == 'wifi':
        ssid = form.get('wifi_ssid', '')[:64]
        pwd = form.get('wifi_password', '')[:64]
        auth = form.get('wifi_auth', 'WPA')
        if auth not in ALLOWED_WIFI_AUTH:
            auth = 'WPA'
        hidden = 'true' if form.get('wifi_hidden') else 'false'
        return f"WIFI:T:{auth};S:{ssid};P:{pwd};H:{hidden};;"

    if content_type == 'contact':
        name = form.get('contact_name', '')[:100]
        phone = form.get('contact_phone', '')[:30]
        email = form.get('contact_email', '')[:200]
        org = form.get('contact_org', '')[:100]
        url = form.get('contact_url', '')[:200]
        addr = form.get('contact_addr', '')[:200]
        lines = [f"MECARD:N:{name}"]
        if phone:
            lines.append(f"TEL:{phone}")
        if email:
            lines.append(f"EMAIL:{email}")
        if org:
            lines.append(f"ORG:{org}")
        if url:
            lines.append(f"URL:{url}")
        if addr:
            lines.append(f"ADR:{addr}")
        return ';'.join(lines) + ';;'

    if content_type == 'geo':
        lat = form.get('geo_lat', '')[:20]
        lng = form.get('geo_lng', '')[:20]
        query = form.get('geo_query', '')[:100]
        return f"geo:{lat},{lng}" + (f"?q={query}" if query else '')

    if content_type == 'calendar':
        summary = form.get('cal_summary', '')[:200]
        start = form.get('cal_start', '')[:20].replace('-', '').replace(':', '').replace('T', 'T')
        end = form.get('cal_end', '')[:20].replace('-', '').replace(':', '').replace('T', 'T')
        location = form.get('cal_location', '')[:200]
        desc = form.get('cal_desc', '')[:500]
        lines = ['BEGIN:VEVENT', f'SUMMARY:{summary}']
        if start:
            lines.append(f'DTSTART:{start}')
        if end:
            lines.append(f'DTEND:{end}')
        if location:
            lines.append(f'LOCATION:{location}')
        if desc:
            lines.append(f'DESCRIPTION:{desc}')
        lines.append('END:VEVENT')
        return '\n'.join(lines)

    return ''


def _parse_common(form):
    output_fmt = form.get('output_format', 'png').lower()
    if output_fmt not in ALLOWED_OUTPUT_FMTS:
        output_fmt = 'png'
    size = _safe_int(form.get('size', 300), 300, MIN_SIZE, MAX_SIZE)
    margin = _safe_int(form.get('margin', 4), 4, 0, 10)
    fg = _safe_color(form.get('fg_color'), '#000000')
    bg = _safe_color(form.get('bg_color'), '#ffffff')
    ec = ERROR_LEVELS.get(form.get('ec_level', 'M'), ERROR_CORRECT_M)
    return output_fmt, size, margin, fg, bg, ec


class LogoError(ValueError):
    """Raised for a logo upload we refuse; message is safe to show the user."""


def _load_logo(file_storage):
    """Validate an uploaded logo and return it as an RGBA PIL image, or None.

    Whitelist-based like the other inputs: size cap, format allowlist,
    pixel-count cap checked from the header *before* decoding.
    """
    if file_storage is None or not file_storage.filename:
        return None
    raw = file_storage.read(MAX_LOGO_BYTES + 1)
    if not raw:
        return None
    if len(raw) > MAX_LOGO_BYTES:
        raise LogoError('Logo must be 2 MB or smaller.')
    try:
        img = Image.open(io.BytesIO(raw))
        if img.format not in ALLOWED_LOGO_FORMATS:
            raise LogoError('Logo must be a PNG, JPEG, WebP, or GIF image.')
        w, h = img.size
        if w * h > MAX_LOGO_PIXELS:
            raise LogoError('Logo dimensions are too large.')
        img.seek(0)          # first frame of animated GIF/WebP
        img.load()
    except LogoError:
        raise
    except Exception:
        raise LogoError('Could not read the logo image.')
    return img.convert('RGBA')


def _parse_logo_opts(form):
    pct = _safe_int(form.get('logo_size', LOGO_SIZE_DEFAULT), LOGO_SIZE_DEFAULT,
                    LOGO_SIZE_MIN, LOGO_SIZE_MAX)
    pad = form.get('logo_pad', 'true') != 'false'
    return pct, pad


def _logo_geometry(modules, margin, total, pct):
    """Return (box, pad) for a centered logo, in the same units as `total`.

    `box` is the logo's square edge (pct of the code area, excluding the
    quiet zone); `pad` is the clear border drawn around it.
    """
    code_width = total * modules / float(modules + 2 * margin)
    box = code_width * pct / 100.0
    pad = max(code_width / modules, box * 0.08)   # at least one module
    return box, pad


def _snap_pad_rect(cx, cy, w, h, pad, modules, margin, total):
    """Grow the logo's clear area out to whole-module boundaries.

    Avoids slicing modules in half, which looks rough and can confuse
    scanners. Returns (x0, y0, x1, y1) in the same units as `total`.
    """
    unit = total / float(modules + 2 * margin)
    origin = margin * unit

    def lo(v):
        return origin + math.floor((v - origin) / unit) * unit

    def hi(v):
        return origin + math.ceil((v - origin) / unit) * unit

    return (lo(cx - w / 2.0 - pad), lo(cy - h / 2.0 - pad),
            hi(cx + w / 2.0 + pad), hi(cy + h / 2.0 + pad))


def _fit_logo(logo, box_px):
    fitted = logo.copy()
    fitted.thumbnail((box_px, box_px), Image.LANCZOS)
    return fitted


def _make_qr_png(data, ec, size, margin, fg, bg, logo=None, logo_pct=LOGO_SIZE_DEFAULT, logo_pad=True):
    box_size = max(1, size // (21 + margin * 2))
    qr = qrcode.QRCode(error_correction=ec, box_size=box_size, border=margin)
    qr.add_data(data)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color=fg, back_color=bg)
    pil_img = pil_img.resize((size, size), Image.LANCZOS)
    if logo is not None:
        pil_img = pil_img.convert('RGBA')
        box, pad = _logo_geometry(qr.modules_count, margin, size, logo_pct)
        fitted = _fit_logo(logo, max(1, int(round(box))))
        lw, lh = fitted.size
        cx, cy = size / 2.0, size / 2.0
        if logo_pad:
            draw = ImageDraw.Draw(pil_img)
            x0, y0, x1, y1 = _snap_pad_rect(cx, cy, lw, lh, pad, qr.modules_count, margin, size)
            draw.rectangle([int(round(x0)), int(round(y0)), int(round(x1)) - 1, int(round(y1)) - 1], fill=bg)
        pil_img.alpha_composite(fitted, (int(round(cx - lw / 2.0)), int(round(cy - lh / 2.0))))
        pil_img = pil_img.convert('RGB')
    buf = io.BytesIO()
    pil_img.save(buf, format='PNG')
    buf.seek(0)
    return buf


_SVG_WIDTH_RE = re.compile(r'<svg[^>]*\swidth="([0-9.]+)mm"')


def _make_qr_svg(data, ec, size, margin, logo=None, logo_pct=LOGO_SIZE_DEFAULT, logo_pad=True, bg='#ffffff'):
    box_size = max(1, size // (21 + margin * 2))
    factory = qrcode.image.svg.SvgImage
    img = qrcode.make(data, error_correction=ec, box_size=box_size,
                      border=margin, image_factory=factory)
    buf = io.BytesIO()
    img.save(buf)
    if logo is None:
        buf.seek(0)
        return buf

    svg = buf.getvalue().decode('utf-8')
    m = _SVG_WIDTH_RE.search(svg)
    total = float(m.group(1))
    box, pad = _logo_geometry(img.width, margin, total, logo_pct)
    # Embed a re-encoded PNG (never the raw upload) at a sane resolution.
    embedded = _fit_logo(logo, 512)
    png = io.BytesIO()
    embedded.save(png, format='PNG')
    href = 'data:image/png;base64,' + base64.b64encode(png.getvalue()).decode()
    lw, lh = embedded.size
    scale = box / float(max(lw, lh))
    w, h = lw * scale, lh * scale
    cx = total / 2.0
    parts = []
    if logo_pad:
        x0, y0, x1, y1 = _snap_pad_rect(cx, cx, w, h, pad, img.width, margin, total)
        parts.append('<rect x="{:.3f}mm" y="{:.3f}mm" width="{:.3f}mm" height="{:.3f}mm" '
                     'fill="{}"/>'.format(x0, y0, x1 - x0, y1 - y0, bg))
    parts.append('<image x="{:.3f}mm" y="{:.3f}mm" width="{:.3f}mm" height="{:.3f}mm" '
                 'href="{}" xlink:href="{}" xmlns:xlink="http://www.w3.org/1999/xlink"/>'
                 .format(cx - w / 2, cx - h / 2, w, h, href, href))
    idx = svg.rfind('</svg>')
    svg = svg[:idx] + ''.join(parts) + svg[idx:]
    out = io.BytesIO(svg.encode('utf-8'))
    out.seek(0)
    return out


def _render_qr(form, data, output_fmt, size, margin, fg, bg, ec):
    """Shared QR render for the POST routes. Handles the optional logo.

    A logo forces error-correction H so the covered modules are recoverable.
    Returns (buf, mime, ec_label, has_logo).
    """
    logo = _load_logo(request.files.get('logo'))
    ec_label = form.get('ec_level', 'M')
    logo_pct, logo_pad = _parse_logo_opts(form)
    if logo is not None:
        ec, ec_label = ERROR_CORRECT_H, 'H'
    if output_fmt == 'svg':
        buf = _make_qr_svg(data, ec, size, margin, logo, logo_pct, logo_pad, bg)
        return buf, 'image/svg+xml', ec_label, logo is not None
    buf = _make_qr_png(data, ec, size, margin, fg, bg, logo, logo_pct, logo_pad)
    return buf, 'image/png', ec_label, logo is not None


def _make_barcode_buf(fmt, data, output_fmt, bar_height, margin, show_text):
    bc_class = barcode.get_barcode_class(fmt)
    options = {
        'write_text': show_text,
        'module_height': bar_height,
        'quiet_zone': float(margin),
    }
    buf = io.BytesIO()
    writer = SVGWriter() if output_fmt == 'svg' else ImageWriter()
    bc_obj = bc_class(data, writer=writer)
    bc_obj.write(buf, options)
    buf.seek(0)
    return buf


@qr_bp.route('/generator')
def generator():
    return render_template('qr_generator.html')


@qr_bp.route('/api/generate', methods=['POST'])
def generate():
    form = request.form
    fmt = form.get('format', 'qrcode')
    output_fmt, size, margin, fg, bg, ec = _parse_common(form)

    source = _req_source()
    try:
        if fmt == 'qrcode':
            data = _build_qr_data(form)
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            buf, mime, ec_label, has_logo = _render_qr(form, data, output_fmt, size, margin, fg, bg, ec)
            b64 = base64.b64encode(buf.getvalue()).decode()
            resp = jsonify({'image': f'data:{mime};base64,{b64}', 'mime': mime})
            _log_event(event='generate', format=fmt, content_type=form.get('content_type', 'text'),
                       output_format=output_fmt, ec_level=ec_label, logo=has_logo,
                       source=source, status='success')
            return resp

        bc_id = BARCODE_FORMATS.get(fmt)
        if not bc_id:
            return jsonify({'error': 'Unknown format'}), 400
        data = form.get('barcode_data', '')[:MAX_DATA_LEN]
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        bar_height = _safe_float(form.get('bar_height', 15), 15, 5, 50)
        show_text = form.get('show_text', 'true') == 'true'
        buf = _make_barcode_buf(bc_id, data, output_fmt, bar_height, margin, show_text)
        mime = 'image/svg+xml' if output_fmt == 'svg' else 'image/png'
        b64 = base64.b64encode(buf.getvalue()).decode()
        _log_event(event='generate', format=fmt, output_format=output_fmt,
                   source=source, status='success')
        return jsonify({'image': f'data:{mime};base64,{b64}', 'mime': mime})

    except LogoError as e:
        _log_event(event='generate', format=fmt, source=source, status='rejected', error=str(e))
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        _log_event(event='generate', format=fmt, source=source, status='error', error=str(e))
        return jsonify({'error': 'Generation failed. Check your input data.'}), 500


@qr_bp.route('/api/qr', methods=['GET'])
def qr_image_get():
    """GET endpoint for embedding QRs as <img src=...>.

    Browsers can't <img src> a POST endpoint, so this is a thin GET shim
    over the QR pipeline. Takes simple query params, returns raw image
    bytes inline (no JSON envelope, no attachment header). Output is
    cacheable — a QR for a stable URL never changes.

    Query params:
      data       (required) — payload to encode (URL or text)
      size       (optional) — pixel dimension, default 300, clamped 100–2000
      format     (optional) — png | svg, default png
      margin     (optional) — quiet zone modules, default 4, clamped 0–10
      fg_color   (optional) — #rrggbb foreground, default #000000
      bg_color   (optional) — #rrggbb background, default #ffffff
      ec_level   (optional) — L | M | Q | H, default M
    """
    args = request.args
    data = args.get('data', '')[:MAX_DATA_LEN]
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    output_fmt = args.get('format', 'png').lower()
    if output_fmt not in ALLOWED_OUTPUT_FMTS:
        output_fmt = 'png'
    size = _safe_int(args.get('size', 300), 300, MIN_SIZE, MAX_SIZE)
    margin = _safe_int(args.get('margin', 4), 4, 0, 10)
    fg = _safe_color(args.get('fg_color'), '#000000')
    bg = _safe_color(args.get('bg_color'), '#ffffff')
    ec = ERROR_LEVELS.get(args.get('ec_level', 'M'), ERROR_CORRECT_M)

    try:
        if output_fmt == 'svg':
            buf = _make_qr_svg(data, ec, size, margin)
            mime = 'image/svg+xml'
        else:
            buf = _make_qr_png(data, ec, size, margin, fg, bg)
            mime = 'image/png'
        _log_event(event='qr_embed', output_format=output_fmt, ec_level=args.get('ec_level', 'M'),
                   size=size, source='api', status='success')
        resp = send_file(buf, mimetype=mime)
        # Same payload always yields the same image — let CDNs cache it.
        resp.headers['Cache-Control'] = 'public, max-age=86400, immutable'
        return resp
    except Exception as e:
        _log_event(event='qr_embed', source='api', status='error', error=str(e))
        return jsonify({'error': 'Generation failed. Check your input data.'}), 500


@qr_bp.route('/api/generate/download', methods=['POST'])
def download():
    form = request.form
    fmt = form.get('format', 'qrcode')
    output_fmt, size, margin, fg, bg, ec = _parse_common(form)

    source = _req_source()
    try:
        if fmt == 'qrcode':
            data = _build_qr_data(form)
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            buf, mime, ec_label, has_logo = _render_qr(form, data, output_fmt, size, margin, fg, bg, ec)
            _log_event(event='download', format=fmt, content_type=form.get('content_type', 'text'),
                       output_format=output_fmt, ec_level=ec_label, logo=has_logo,
                       source=source, status='success')
            return send_file(buf, mimetype=mime, as_attachment=True,
                             download_name='qrcode.' + output_fmt)

        bc_id = BARCODE_FORMATS.get(fmt)
        if not bc_id:
            return jsonify({'error': 'Unknown format'}), 400
        data = form.get('barcode_data', '')[:MAX_DATA_LEN]
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        bar_height = _safe_float(form.get('bar_height', 15), 15, 5, 50)
        show_text = form.get('show_text', 'true') == 'true'
        buf = _make_barcode_buf(bc_id, data, output_fmt, bar_height, margin, show_text)
        mime = 'image/svg+xml' if output_fmt == 'svg' else 'image/png'
        dl_name = f'{fmt}.{output_fmt}'
        _log_event(event='download', format=fmt, output_format=output_fmt,
                   source=source, status='success')
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=dl_name)

    except LogoError as e:
        _log_event(event='download', format=fmt, source=source, status='rejected', error=str(e))
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        _log_event(event='download', format=fmt, source=source, status='error', error=str(e))
        return jsonify({'error': 'Generation failed. Check your input data.'}), 500
