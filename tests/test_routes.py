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
