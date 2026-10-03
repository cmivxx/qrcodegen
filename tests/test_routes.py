"""Integration tests for the Flask routes."""
import base64


# ── /generator (UI) ──────────────────────────────────────────────────────────

class TestGeneratorPage:
    def test_returns_200(self, client):
        rv = client.get('/generator')
        assert rv.status_code == 200

    def test_returns_html(self, client):
        rv = client.get('/generator')
        assert b'<!DOCTYPE html>' in rv.data
        assert b'QR Code Generator' in rv.data

    def test_has_google_analytics(self, client):
        rv = client.get('/generator')
        assert b'G-PD7DGWW92P' in rv.data

    def test_has_chrisrmiller_link(self, client):
        rv = client.get('/generator')
        assert b'chrisrmiller.com' in rv.data.lower()


# ── POST /api/generate ───────────────────────────────────────────────────────

class TestGenerateApi:
    def test_qr_text_png_returns_base64(self, client):
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'text', 'text': 'hello',
            'output_format': 'png', 'size': '300', 'margin': '4',
        })
        assert rv.status_code == 200
        body = rv.get_json()
        assert body['mime'] == 'image/png'
        assert body['image'].startswith('data:image/png;base64,')
        # Decoded payload is a real PNG (starts with PNG magic bytes)
        b64 = body['image'].split(',', 1)[1]
        png_bytes = base64.b64decode(b64)
        assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n'

    def test_qr_text_svg_returns_svg(self, client):
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'text', 'text': 'hello',
            'output_format': 'svg',
        })
        assert rv.status_code == 200
        body = rv.get_json()
        assert body['mime'] == 'image/svg+xml'
        b64 = body['image'].split(',', 1)[1]
        svg_bytes = base64.b64decode(b64)
        assert b'<svg' in svg_bytes

    def test_qr_url_content_type(self, client):
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'url', 'url': 'https://example.com',
        })
        assert rv.status_code == 200

    def test_qr_wifi_content_type(self, client):
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'wifi',
            'wifi_ssid': 'TestNet', 'wifi_password': 'pass1234', 'wifi_auth': 'WPA',
        })
        assert rv.status_code == 200

    def test_empty_data_returns_400(self, client):
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'text', 'text': '',
        })
        assert rv.status_code == 400
        assert 'error' in rv.get_json()

    def test_unknown_format_returns_400(self, client):
        rv = client.post('/api/generate', data={
            'format': 'made_up_format', 'barcode_data': 'abc',
        })
        assert rv.status_code == 400

    def test_barcode_code128(self, client):
        rv = client.post('/api/generate', data={
            'format': 'code128', 'barcode_data': 'HELLO123',
            'output_format': 'png',
        })
        assert rv.status_code == 200
        body = rv.get_json()
        assert body['mime'] == 'image/png'

    def test_barcode_empty_data_returns_400(self, client):
        rv = client.post('/api/generate', data={
            'format': 'code128', 'barcode_data': '',
        })
        assert rv.status_code == 400

    # ── Security boundary tests ──────────────────────────────────────────────

    def test_malicious_color_falls_back_to_default(self, client):
        # Passing arbitrary string as fg_color should not crash;
        # _safe_color falls back to '#000000'
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'text', 'text': 'hi',
            'fg_color': 'red; DROP TABLE users;',
        })
        assert rv.status_code == 200

    def test_oversized_size_is_clamped(self, client):
        # Requesting 99999px should clamp to MAX_SIZE (2000), not blow up memory
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'text', 'text': 'hi',
            'size': '99999',
        })
        assert rv.status_code == 200

    def test_negative_size_is_clamped(self, client):
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'text', 'text': 'hi',
            'size': '-100',
        })
        assert rv.status_code == 200

    def test_invalid_output_format_falls_back_to_png(self, client):
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'text', 'text': 'hi',
            'output_format': 'evil_format',
        })
        assert rv.status_code == 200
        assert rv.get_json()['mime'] == 'image/png'

    def test_unknown_content_type_returns_400(self, client):
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'made_up', 'text': 'hi',
        })
        assert rv.status_code == 400


# ── POST /api/generate/download ──────────────────────────────────────────────

class TestDownloadApi:
    def test_qr_png_download_returns_attachment(self, client):
        rv = client.post('/api/generate/download', data={
            'format': 'qrcode', 'content_type': 'text', 'text': 'hello',
            'output_format': 'png',
        })
        assert rv.status_code == 200
        assert rv.mimetype == 'image/png'
        assert 'attachment' in rv.headers.get('Content-Disposition', '')
        assert rv.data[:8] == b'\x89PNG\r\n\x1a\n'

    def test_qr_svg_download(self, client):
        rv = client.post('/api/generate/download', data={
            'format': 'qrcode', 'content_type': 'text', 'text': 'hello',
            'output_format': 'svg',
        })
        assert rv.status_code == 200
        assert rv.mimetype == 'image/svg+xml'
        assert b'<svg' in rv.data

    def test_barcode_download(self, client):
        rv = client.post('/api/generate/download', data={
            'format': 'code128', 'barcode_data': 'ABC123',
            'output_format': 'png',
        })
        assert rv.status_code == 200
        assert rv.mimetype == 'image/png'

    def test_download_empty_data_returns_400(self, client):
        rv = client.post('/api/generate/download', data={
            'format': 'qrcode', 'content_type': 'text', 'text': '',
        })
        assert rv.status_code == 400


# ── GET /api/qr (img-src shim) ───────────────────────────────────────────────

class TestQrImageGet:
    def test_png_returns_inline_image_bytes(self, client):
        rv = client.get('/api/qr?data=https://example.com&size=256&format=png')
        assert rv.status_code == 200
        assert rv.mimetype == 'image/png'
        # Inline, not attachment — must embed in <img src>
        assert 'attachment' not in rv.headers.get('Content-Disposition', '')
        assert rv.data[:8] == b'\x89PNG\r\n\x1a\n'

    def test_svg_returns_svg_bytes(self, client):
        rv = client.get('/api/qr?data=hello&format=svg')
        assert rv.status_code == 200
        assert rv.mimetype == 'image/svg+xml'
        assert b'<svg' in rv.data

    def test_missing_data_returns_400(self, client):
        rv = client.get('/api/qr')
        assert rv.status_code == 400
        assert 'error' in rv.get_json()

    def test_empty_data_returns_400(self, client):
        rv = client.get('/api/qr?data=')
        assert rv.status_code == 400

    def test_default_size_when_omitted(self, client):
        rv = client.get('/api/qr?data=hi')
        assert rv.status_code == 200
        assert rv.mimetype == 'image/png'

    def test_oversized_size_is_clamped(self, client):
        rv = client.get('/api/qr?data=hi&size=99999')
        assert rv.status_code == 200

    def test_invalid_format_falls_back_to_png(self, client):
        rv = client.get('/api/qr?data=hi&format=evil')
        assert rv.status_code == 200
        assert rv.mimetype == 'image/png'

    def test_cache_control_header_set(self, client):
        # CDN-cacheable — same payload always renders the same QR
        rv = client.get('/api/qr?data=https://example.com')
        cc = rv.headers.get('Cache-Control', '')
        assert 'public' in cc
        assert 'max-age' in cc

    def test_malicious_color_falls_back_to_default(self, client):
        rv = client.get('/api/qr?data=hi&fg_color=red;DROP%20TABLE')
        assert rv.status_code == 200


# ── Root redirect ────────────────────────────────────────────────────────────

class TestRoot:
    def test_root_redirects_to_generator(self, client):
        rv = client.get('/')
        assert rv.status_code in (301, 302)
        assert '/generator' in rv.headers['Location']


# ── Security headers (set via Flask after_request) ───────────────────────────

class TestSecurityHeaders:
    def test_csp_present_on_ui(self, client):
        rv = client.get('/generator')
        csp = rv.headers.get('Content-Security-Policy', '')
        assert "default-src 'self'" in csp
        assert 'frame-ancestors' in csp

    def test_csp_allows_google_analytics(self, client):
        rv = client.get('/generator')
        csp = rv.headers.get('Content-Security-Policy', '')
        assert 'googletagmanager.com' in csp
        assert 'google-analytics.com' in csp

    def test_x_frame_options(self, client):
        rv = client.get('/generator')
        assert rv.headers.get('X-Frame-Options') == 'SAMEORIGIN'

    def test_x_content_type_options(self, client):
        rv = client.get('/generator')
        assert rv.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_referrer_policy(self, client):
        rv = client.get('/generator')
        assert rv.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    def test_permissions_policy(self, client):
        rv = client.get('/generator')
        pp = rv.headers.get('Permissions-Policy', '')
        assert 'geolocation=()' in pp
        assert 'microphone=()' in pp
        assert 'camera=()' in pp

    def test_headers_present_on_api(self, client):
        rv = client.post('/api/generate', data={
            'format': 'qrcode', 'content_type': 'text', 'text': 'hi',
        })
        assert rv.headers.get('X-Content-Type-Options') == 'nosniff'
        assert 'Content-Security-Policy' in rv.headers


# ── Logo overlay (POST routes only) ──────────────────────────────────────────

def _logo_png(w=200, h=120, color=(108, 99, 255, 255)):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGBA', (w, h), color).save(buf, format='PNG')
    buf.seek(0)
    return buf


def _qr_form(**extra):
    form = {'format': 'qrcode', 'content_type': 'url', 'url': 'https://example.com',
            'output_format': 'png', 'size': '400', 'margin': '4'}
    form.update(extra)
    return form


class TestLogo:
    def test_png_with_logo_returns_png(self, client):
        rv = client.post('/api/generate', data=_qr_form(logo=(_logo_png(), 'logo.png')),
                         content_type='multipart/form-data')
        assert rv.status_code == 200
        b64 = rv.get_json()['image'].split(',', 1)[1]
        assert base64.b64decode(b64)[:8] == b'\x89PNG\r\n\x1a\n'

    def test_logo_changes_output(self, client):
        plain = client.post('/api/generate', data=_qr_form(ec_level='H')).get_json()['image']
        with_logo = client.post('/api/generate', data=_qr_form(ec_level='H', logo=(_logo_png(), 'l.png')),
                                content_type='multipart/form-data').get_json()['image']
        assert plain != with_logo

    def test_logo_forces_ec_h(self, client):
        # With a logo, ec_level=L must render identically to ec_level=H.
        low = client.post('/api/generate', data=_qr_form(ec_level='L', logo=(_logo_png(), 'l.png')),
                          content_type='multipart/form-data').get_json()['image']
        high = client.post('/api/generate', data=_qr_form(ec_level='H', logo=(_logo_png(), 'l.png')),
                           content_type='multipart/form-data').get_json()['image']
        assert low == high

    def test_svg_with_logo_embeds_png_image(self, client):
        rv = client.post('/api/generate/download',
                         data=_qr_form(output_format='svg', logo=(_logo_png(), 'logo.png')),
                         content_type='multipart/form-data')
        assert rv.status_code == 200
        assert rv.mimetype == 'image/svg+xml'
        assert b'<image' in rv.data
        assert b'data:image/png;base64,' in rv.data
        assert rv.data.rstrip().endswith(b'</svg>')

    def test_png_download_with_logo(self, client):
        rv = client.post('/api/generate/download', data=_qr_form(logo=(_logo_png(), 'logo.png')),
                         content_type='multipart/form-data')
        assert rv.status_code == 200
        assert rv.mimetype == 'image/png'
        assert 'attachment' in rv.headers['Content-Disposition']

    def test_jpeg_logo_accepted(self, client):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (100, 100), (255, 0, 0)).save(buf, format='JPEG')
        buf.seek(0)
        rv = client.post('/api/generate', data=_qr_form(logo=(buf, 'logo.jpg')),
                         content_type='multipart/form-data')
        assert rv.status_code == 200

    def test_non_image_logo_rejected(self, client):
        import io
        rv = client.post('/api/generate', data=_qr_form(logo=(io.BytesIO(b'not an image'), 'x.png')),
                         content_type='multipart/form-data')
        assert rv.status_code == 400
        assert 'logo' in rv.get_json()['error'].lower()

    def test_svg_logo_upload_rejected(self, client):
        import io
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        rv = client.post('/api/generate', data=_qr_form(logo=(io.BytesIO(svg), 'x.svg')),
                         content_type='multipart/form-data')
        assert rv.status_code == 400

    def test_oversized_logo_rejected(self, client):
        import io
        big = io.BytesIO(b'\x89PNG' + b'0' * (2 * 1024 * 1024 + 1))
        rv = client.post('/api/generate', data=_qr_form(logo=(big, 'big.png')),
                         content_type='multipart/form-data')
        assert rv.status_code in (400, 413)
        assert 'error' in rv.get_json()

    def test_empty_file_field_ignored(self, client):
        import io
        rv = client.post('/api/generate', data=_qr_form(logo=(io.BytesIO(b''), '')),
                         content_type='multipart/form-data')
        assert rv.status_code == 200

    def test_logo_size_clamped(self, client):
        rv = client.post('/api/generate', data=_qr_form(logo_size='95', logo=(_logo_png(), 'l.png')),
                         content_type='multipart/form-data')
        assert rv.status_code == 200

    def test_logo_ignored_for_barcodes(self, client):
        rv = client.post('/api/generate', data={
            'format': 'code128', 'barcode_data': 'ABC123', 'output_format': 'png',
            'logo': (_logo_png(), 'l.png')}, content_type='multipart/form-data')
        assert rv.status_code == 200

    def test_get_endpoint_unchanged(self, client):
        rv = client.get('/api/qr?data=https://example.com')
        assert rv.status_code == 200
        assert rv.mimetype == 'image/png'

    def test_ui_has_logo_controls(self, client):
        rv = client.get('/generator')
        assert b'id="logo-file"' in rv.data
