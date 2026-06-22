"""Unit tests for HoneypotFileWatcher generic JSON log watcher."""

import json
import os
import tempfile

import pytest

from backend.ingestion.honeypot_watcher import HoneypotFileWatcher


@pytest.fixture
def log_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write('{"event": "first"}\n{"event": "second"}\n')
        f.flush()
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def watcher(log_file):
    return HoneypotFileWatcher(log_path=log_file, source="test")


class TestHoneypotFileWatcher:
    async def test_fetch_events_returns_all(self, watcher):
        events = await watcher.fetch_events()
        assert len(events) == 2
        assert events[0] == {"event": "first"}
        assert events[1] == {"event": "second"}

    async def test_fetch_events_incremental(self, watcher):
        events = await watcher.fetch_events()
        assert len(events) == 2

        events2 = await watcher.fetch_events()
        assert events2 == []

    async def test_fetch_events_new_content(self, watcher):
        await watcher.fetch_events()

        with open(watcher.log_path, "a") as f:
            f.write('{"event": "third"}\n')

        events = await watcher.fetch_events()
        assert len(events) == 1
        assert events[0] == {"event": "third"}

    async def test_fetch_events_since_filter(self, watcher):
        await watcher.fetch_events()
        with open(watcher.log_path, "a") as f:
            f.write('{"event": "later", "timestamp": "2026-06-20T12:00:00"}\n')

        events = await watcher.fetch_events(since="2026-06-20T11:00:00")
        assert len(events) == 1
        assert events[0]["event"] == "later"

        events = await watcher.fetch_events(since="2026-06-20T13:00:00")
        assert len(events) == 0

    async def test_fetch_events_limit(self, watcher):
        with open(watcher.log_path, "a") as f:
            f.write('{"event": "a"}\n{"event": "b"}\n{"event": "c"}\n')

        events = await watcher.fetch_events(limit=2)
        assert len(events) == 2

    async def test_non_existent_file(self):
        w = HoneypotFileWatcher(log_path="/tmp/nonexistent_test.json", source="ghost")
        events = await w.fetch_events()
        assert events == []

    async def test_parse_timestamp(self):
        assert HoneypotFileWatcher.parse_timestamp("") == ""
        assert HoneypotFileWatcher.parse_timestamp("2026-06-20T12:00:00Z") == "2026-06-20T12:00:00+00:00"
        assert HoneypotFileWatcher.parse_timestamp("2026-06-20T12:00:00+00:00") == "2026-06-20T12:00:00+00:00"

    async def test_skips_malformed_json(self, log_file):
        with open(log_file, "a") as f:
            f.write("not valid json\n")
            f.write('{"valid": true}\n')

        w = HoneypotFileWatcher(log_path=log_file, source="test")
        events = await w.fetch_events()
        assert len(events) == 3
        assert events[-1]["valid"] is True

    async def test_source_property(self):
        w = HoneypotFileWatcher(log_path="/tmp/x.json", source="cowrie2")
        assert w.source == "cowrie2"
