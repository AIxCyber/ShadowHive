"""Unit tests for _parse_honeypot_event() normalizer."""

from datetime import UTC, datetime

from backend.main import _parse_honeypot_event


class TestParseOpenCanary:
    def test_basic_opencanary_event(self):
        raw = {
            "remote_host": "10.0.0.1",
            "logtype": "ftp.login",
            "message": "Login attempt: admin / admin123",
            "conversation_id": "conv-001",
            "timestamp": "2026-06-20T12:00:00Z",
        }
        result = _parse_honeypot_event(raw, "opencanary")
        assert result["source_ip"] == "10.0.0.1"
        assert result["event_type"] == "opencanary.ftp.login"
        assert "Login attempt" in result["command"]
        assert result["session_id"] == "conv-001"
        assert result["detected_at"] is not None

    def test_opencanary_fallback_fields(self):
        raw = {"src_ip": "10.0.0.2", "event_type": "telnet.login", "data": "root:x"}
        result = _parse_honeypot_event(raw, "opencanary")
        assert result["source_ip"] == "10.0.0.2"
        assert result["event_type"] == "opencanary.telnet.login"
        assert result["command"] == "root:x"

    def test_opencanary_unknown_defaults(self):
        raw = {"source_ip": "10.0.0.3"}
        result = _parse_honeypot_event(raw, "opencanary")
        assert result["event_type"] == "opencanary.unknown"

    def test_opencanary_detected_at_normalized(self):
        raw = {"remote_host": "1.2.3.4", "timestamp": "2026-06-20T12:00:00Z"}
        result = _parse_honeypot_event(raw, "opencanary")
        assert result["detected_at"].tzinfo is None
        assert result["detected_at"].hour == 12


class TestParsePortal:
    def test_basic_portal_event(self):
        raw = {
            "source_ip": "10.0.0.5",
            "event_type": "wp_login",
            "path": "/wp-login.php",
            "session_id": "sess-portal",
            "timestamp": "2026-06-20T12:00:00Z",
        }
        result = _parse_honeypot_event(raw, "portal")
        assert result["source_ip"] == "10.0.0.5"
        assert result["event_type"] == "web.wp_login"
        assert result["command"] == "/wp-login.php"
        assert result["session_id"] == "sess-portal"

    def test_portal_fallback_remote_addr(self):
        raw = {"remote_addr": "10.0.0.6", "url": "/phpmyadmin/"}
        result = _parse_honeypot_event(raw, "portal")
        assert result["source_ip"] == "10.0.0.6"
        assert result["command"] == "/phpmyadmin/"
        assert result["event_type"] == "web.credential_harvest"


class TestParseCowrie2:
    def test_basic_cowrie2_event(self):
        raw = {
            "eventid": "cowrie.session.connect",
            "src_ip": "10.0.0.7",
            "session": "sess-c2",
            "message": "New connection",
            "timestamp": "2026-06-20T12:00:00Z",
        }
        result = _parse_honeypot_event(raw, "cowrie2")
        assert result["source_ip"] == "10.0.0.7"
        assert result["event_type"] == "cowrie.session.connect"
        assert result["session_id"] == "sess-c2"

    def test_cowrie3_event(self):
        raw = {
            "eventid": "cowrie.command.input",
            "src_ip": "10.0.0.8",
            "session": "sess-c3",
            "input": "whoami",
            "timestamp": "2026-06-20T12:00:00Z",
        }
        result = _parse_honeypot_event(raw, "cowrie3")
        assert result["source_ip"] == "10.0.0.8"
        assert result["event_type"] == "cowrie.command.input"
        assert result["command"] == "whoami"
        assert result["session_id"] == "sess-c3"


class TestParseDionaea:
    def test_basic_dionaea_event(self):
        raw = {
            "remote_host": "10.0.0.9",
            "logtype": "malware.download",
            "data": "/payload.exe",
            "conversation_id": "conv-dio",
            "timestamp": "2026-06-20T12:00:00Z",
        }
        result = _parse_honeypot_event(raw, "dionaea")
        assert result["source_ip"] == "10.0.0.9"
        assert result["event_type"] == "dionaea.malware.download"
        assert result["command"] == "/payload.exe"
        assert result["session_id"] == "conv-dio"

    def test_dionaea_default_logtype(self):
        raw = {"src_ip": "10.0.0.10"}
        result = _parse_honeypot_event(raw, "dionaea")
        assert result["event_type"] == "dionaea.unknown"


class TestParseWordPress:
    def test_basic_wordpress_event(self):
        raw = {
            "remote_addr": "10.0.0.11",
            "event_type": "login_attempt",
            "request": "POST /wp-login.php",
            "session": "sess-wp",
            "timestamp": "2026-06-20T12:00:00Z",
        }
        result = _parse_honeypot_event(raw, "wordpress")
        assert result["source_ip"] == "10.0.0.11"
        assert result["event_type"] == "wp.login_attempt"
        assert result["command"] == "POST /wp-login.php"
        assert result["session_id"] == "sess-wp"

    def test_wordpress_default_event_type(self):
        raw = {"source_ip": "10.0.0.12"}
        result = _parse_honeypot_event(raw, "wordpress")
        assert result["event_type"] == "wp.login_attempt"


class TestParseFallback:
    def test_unknown_source(self):
        raw = {"source_ip": "10.0.0.99", "event_type": "custom.event"}
        result = _parse_honeypot_event(raw, "custom")
        assert result["source_ip"] == "10.0.0.99"
        assert result["event_type"] == "custom.event"

    def test_unknown_source_defaults(self):
        raw = {"src_ip": "10.0.0.98"}
        result = _parse_honeypot_event(raw, "weird")
        assert result["source_ip"] == "10.0.0.98"
        assert result["event_type"] == "weird.unknown"

    def test_no_source_ip_fallback(self):
        raw = {}
        result = _parse_honeypot_event(raw, "opencanary")
        assert result["source_ip"] == "unknown"


class TestTimestampNormalization:
    def test_z_suffix(self):
        raw = {"remote_host": "1.2.3.4", "timestamp": "2026-06-20T12:00:00Z"}
        result = _parse_honeypot_event(raw, "opencanary")
        assert result["detected_at"] is not None
        assert str(result["detected_at"]).startswith("2026-06-20 12:00:00")

    def test_underscore_time_field(self):
        raw = {"remote_host": "1.2.3.4", "_time": "2026-06-20T13:00:00Z"}
        result = _parse_honeypot_event(raw, "opencanary")
        assert str(result["detected_at"]).startswith("2026-06-20 13:00:00")

    def test_log_time_field(self):
        raw = {"remote_host": "1.2.3.4", "log_time": "2026-06-20T14:00:00Z"}
        result = _parse_honeypot_event(raw, "opencanary")
        assert str(result["detected_at"]).startswith("2026-06-20 14:00:00")

    def test_invalid_timestamp_falls_back(self):
        raw = {"remote_host": "1.2.3.4", "timestamp": "not-a-date"}
        before = datetime.now(UTC).replace(tzinfo=None)
        result = _parse_honeypot_event(raw, "opencanary")
        after = datetime.now(UTC).replace(tzinfo=None)
        assert before <= result["detected_at"] <= after

    def test_no_timestamp_falls_back(self):
        raw = {"remote_host": "1.2.3.4"}
        before = datetime.now(UTC).replace(tzinfo=None)
        result = _parse_honeypot_event(raw, "opencanary")
        after = datetime.now(UTC).replace(tzinfo=None)
        assert before <= result["detected_at"] <= after
