"""Unit tests for the input-validation helpers in qr_generator."""
from qr_generator import _safe_color, _safe_int, _safe_float, _build_qr_data
from werkzeug.datastructures import ImmutableMultiDict


# ── _safe_color ──────────────────────────────────────────────────────────────

class TestSafeColor:
    def test_valid_lowercase_hex(self):
        assert _safe_color('#abcdef', '#000000') == '#abcdef'

    def test_valid_uppercase_hex(self):
        assert _safe_color('#ABCDEF', '#000000') == '#ABCDEF'

    def test_valid_mixed_case(self):
        assert _safe_color('#AbCdEf', '#000000') == '#AbCdEf'

    def test_valid_digits_only(self):
        assert _safe_color('#123456', '#000000') == '#123456'

    def test_missing_hash_returns_default(self):
        assert _safe_color('abcdef', '#000000') == '#000000'

    def test_short_hex_returns_default(self):
        assert _safe_color('#abc', '#000000') == '#000000'

    def test_too_long_returns_default(self):
        assert _safe_color('#abcdef0', '#000000') == '#000000'

    def test_invalid_chars_returns_default(self):
        assert _safe_color('#xyzxyz', '#000000') == '#000000'

    def test_css_name_returns_default(self):
        # PIL accepts names like "red" — we don't, to keep the surface tight
        assert _safe_color('red', '#000000') == '#000000'

    def test_empty_returns_default(self):
        assert _safe_color('', '#000000') == '#000000'

    def test_none_returns_default(self):
        assert _safe_color(None, '#000000') == '#000000'

    def test_injection_attempt_returns_default(self):
        # Make sure we can't sneak in arbitrary strings
        assert _safe_color('javascript:alert(1)', '#fff') == '#fff'
        assert _safe_color('"; rm -rf /;', '#fff') == '#fff'


# ── _safe_int ────────────────────────────────────────────────────────────────

class TestSafeInt:
    def test_valid_in_range(self):
        assert _safe_int('300', 100, 100, 2000) == 300

    def test_clamps_above_max(self):
        assert _safe_int('99999', 300, 100, 2000) == 2000

    def test_clamps_below_min(self):
        assert _safe_int('5', 300, 100, 2000) == 100

    def test_invalid_string_returns_default(self):
        assert _safe_int('not-a-number', 300, 100, 2000) == 300

    def test_none_returns_default(self):
        assert _safe_int(None, 300, 100, 2000) == 300

    def test_float_string_returns_default(self):
        # int('3.5') raises ValueError; we fall back
        assert _safe_int('3.5', 300, 100, 2000) == 300

    def test_negative_clamped_to_min(self):
        assert _safe_int('-100', 300, 0, 2000) == 0


# ── _safe_float ──────────────────────────────────────────────────────────────

class TestSafeFloat:
    def test_valid_int_string(self):
        assert _safe_float('15', 15, 5, 50) == 15.0

    def test_valid_float_string(self):
        assert _safe_float('12.5', 15, 5, 50) == 12.5

    def test_clamps_above_max(self):
        assert _safe_float('1000', 15, 5, 50) == 50.0

    def test_clamps_below_min(self):
        assert _safe_float('1', 15, 5, 50) == 5.0

    def test_invalid_returns_default(self):
        assert _safe_float('xyz', 15, 5, 50) == 15


# ── _build_qr_data ───────────────────────────────────────────────────────────

def _form(**kwargs):
    """Build an ImmutableMultiDict like Flask's request.form."""
    return ImmutableMultiDict(kwargs)


class TestBuildQrData:
    def test_text(self):
        assert _build_qr_data(_form(content_type='text', text='hello')) == 'hello'

    def test_url(self):
        assert _build_qr_data(_form(content_type='url', url='https://example.com')) == 'https://example.com'

    def test_email_basic(self):
        out = _build_qr_data(_form(content_type='email', email_addr='a@b.com'))
        assert out == 'mailto:a@b.com'

    def test_email_with_subject_body(self):
        out = _build_qr_data(_form(
            content_type='email', email_addr='a@b.com',
            email_subject='Hi', email_body='Hello'
        ))
        assert out == 'mailto:a@b.com?subject=Hi&body=Hello'

    def test_phone(self):
        assert _build_qr_data(_form(content_type='phone', phone='+15550001234')) == 'tel:+15550001234'

    def test_sms_with_body(self):
        out = _build_qr_data(_form(content_type='sms', sms_number='+15550001234', sms_body='Hi'))
        assert out == 'smsto:+15550001234:Hi'

    def test_sms_without_body(self):
        out = _build_qr_data(_form(content_type='sms', sms_number='+15550001234'))
        assert out == 'smsto:+15550001234'

    def test_wifi_wpa(self):
        out = _build_qr_data(_form(
            content_type='wifi', wifi_ssid='MyNet', wifi_password='secret', wifi_auth='WPA'
        ))
        assert out == 'WIFI:T:WPA;S:MyNet;P:secret;H:false;;'

    def test_wifi_hidden_flag(self):
        out = _build_qr_data(_form(
            content_type='wifi', wifi_ssid='MyNet', wifi_password='secret',
            wifi_auth='WPA', wifi_hidden='on'
        ))
        assert 'H:true' in out

    def test_wifi_invalid_auth_falls_back_to_wpa(self):
        out = _build_qr_data(_form(
            content_type='wifi', wifi_ssid='MyNet', wifi_password='secret', wifi_auth='HACK'
        ))
        assert 'T:WPA;' in out

    def test_contact_minimal(self):
        out = _build_qr_data(_form(content_type='contact', contact_name='Jane Doe'))
        assert out.startswith('MECARD:N:Jane Doe')
        assert out.endswith(';;')

    def test_contact_full(self):
        out = _build_qr_data(_form(
            content_type='contact', contact_name='Jane', contact_phone='+1',
            contact_email='j@x.com', contact_org='Acme', contact_url='https://x',
            contact_addr='123 Main'
        ))
        assert 'TEL:+1' in out
        assert 'EMAIL:j@x.com' in out
        assert 'ORG:Acme' in out
        assert 'URL:https://x' in out
        assert 'ADR:123 Main' in out

    def test_geo(self):
        out = _build_qr_data(_form(content_type='geo', geo_lat='37.7749', geo_lng='-122.4194'))
        assert out == 'geo:37.7749,-122.4194'

    def test_geo_with_query(self):
        out = _build_qr_data(_form(
            content_type='geo', geo_lat='37.7749', geo_lng='-122.4194', geo_query='SF'
        ))
        assert out == 'geo:37.7749,-122.4194?q=SF'

    def test_calendar(self):
        out = _build_qr_data(_form(
            content_type='calendar', cal_summary='Meeting',
            cal_start='2026-06-01T09:00', cal_end='2026-06-01T10:00'
        ))
        assert 'BEGIN:VEVENT' in out
        assert 'SUMMARY:Meeting' in out
        assert 'DTSTART:20260601T0900' in out
        assert 'END:VEVENT' in out

    def test_unknown_content_type_returns_empty(self):
        assert _build_qr_data(_form(content_type='evil', text='x')) == ''

    def test_text_truncated_at_max_len(self):
        long_text = 'A' * 5000
        out = _build_qr_data(_form(content_type='text', text=long_text))
        assert len(out) == 2000  # MAX_DATA_LEN

    def test_wifi_ssid_truncated(self):
        long_ssid = 'S' * 200
        out = _build_qr_data(_form(content_type='wifi', wifi_ssid=long_ssid, wifi_password='x'))
        # SSID limited to 64 chars
        assert 'S:' + 'S' * 64 + ';' in out
