import io
import re
import base64
import qrcode
import qrcode.image.svg
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
from PIL import Image
import barcode
from barcode.writer import ImageWriter, SVGWriter
from flask import Blueprint, render_template, request, send_file, jsonify

qr_bp = Blueprint('qr', __name__)

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


def _make_qr_png(data, ec, size, margin, fg, bg):
    box_size = max(1, size // (21 + margin * 2))
    qr = qrcode.QRCode(error_correction=ec, box_size=box_size, border=margin)
    qr.add_data(data)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color=fg, back_color=bg)
    pil_img = pil_img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    pil_img.save(buf, format='PNG')
    buf.seek(0)
    return buf


def _make_qr_svg(data, ec, size, margin):
    box_size = max(1, size // (21 + margin * 2))
    factory = qrcode.image.svg.SvgImage
    img = qrcode.make(data, error_correction=ec, box_size=box_size,
                      border=margin, image_factory=factory)
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return buf


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

    try:
        if fmt == 'qrcode':
            data = _build_qr_data(form)
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            if output_fmt == 'svg':
                buf = _make_qr_svg(data, ec, size, margin)
                b64 = base64.b64encode(buf.getvalue()).decode()
                return jsonify({'image': f'data:image/svg+xml;base64,{b64}', 'mime': 'image/svg+xml'})
            else:
                buf = _make_qr_png(data, ec, size, margin, fg, bg)
                b64 = base64.b64encode(buf.getvalue()).decode()
                return jsonify({'image': f'data:image/png;base64,{b64}', 'mime': 'image/png'})

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
        return jsonify({'image': f'data:{mime};base64,{b64}', 'mime': mime})

    except Exception as e:
        return jsonify({'error': 'Generation failed. Check your input data.'}), 500


@qr_bp.route('/api/generate/download', methods=['POST'])
def download():
    form = request.form
    fmt = form.get('format', 'qrcode')
    output_fmt, size, margin, fg, bg, ec = _parse_common(form)

    try:
        if fmt == 'qrcode':
            data = _build_qr_data(form)
            if not data:
                return jsonify({'error': 'No data provided'}), 400
            if output_fmt == 'svg':
                buf = _make_qr_svg(data, ec, size, margin)
                return send_file(buf, mimetype='image/svg+xml', as_attachment=True,
                                 download_name='qrcode.svg')
            else:
                buf = _make_qr_png(data, ec, size, margin, fg, bg)
                return send_file(buf, mimetype='image/png', as_attachment=True,
                                 download_name='qrcode.png')

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
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=dl_name)

    except Exception as e:
        return jsonify({'error': 'Generation failed. Check your input data.'}), 500
