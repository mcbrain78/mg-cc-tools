"""Tests for usage-watch.py — the publisher. Readings are injected."""
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
uw = importlib.import_module("usage-watch")
aas = importlib.import_module("auto-approve-session")


def _reading(session_pct=50, weekly_pct=10, ok=True,
             session_reset="Jul 29, 6:49pm", session_iso="2026-07-29T18:49:00",
             weekly_reset="Aug 3, 8:59pm", weekly_iso="2026-08-03T20:59:00"):
    return {"ok": ok, "error": None,
            "session_pct": session_pct, "session_reset": session_reset,
            "session_reset_iso": session_iso,
            "weekly_pct": weekly_pct, "weekly_reset": weekly_reset,
            "weekly_reset_iso": weekly_iso}


# ── verdict ──────────────────────────────────────────────────────────────────

def test_under_both_limits_is_not_over():
    v = uw.verdict(_reading(90, 50), 93, 98)
    assert v["over"] is False and v["binding"] is None


def test_session_over_binds_session():
    v = uw.verdict(_reading(94, 50), 93, 98)
    assert v["over"] is True and v["binding"] == "session" and v["pct"] == 94
    assert v["window_iso"] == "2026-07-29T18:49:00"
    assert v["window_human"] == "Jul 29, 6:49pm"


def test_weekly_binds_ahead_of_session():
    """A session reset does not clear a weekly cap, so weekly wins when both are over."""
    v = uw.verdict(_reading(99, 99), 93, 98)
    assert v["binding"] == "weekly" and v["window_iso"] == "2026-08-03T20:59:00"


def test_threshold_is_strictly_greater():
    assert uw.verdict(_reading(93, 10), 93, 98)["over"] is False
    assert uw.verdict(_reading(94, 10), 93, 98)["over"] is True


def test_unreadable_reading_is_never_over():
    """The guard treats ok:false as no gate, so a hiccup cannot block work."""
    v = uw.verdict(_reading(99, 99, ok=False), 93, 98)
    assert v["over"] is False and v["ok"] is False


def test_verdict_carries_limits_and_read_time():
    v = uw.verdict(_reading(50, 10), 93, 98, now_ms=1_700_000_000_000)
    assert v["session_max"] == 93 and v["weekly_max"] == 98
    assert v["read_at_ms"] == 1_700_000_000_000


# ── publish ──────────────────────────────────────────────────────────────────

def test_publish_writes_the_account_wide_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    uw.publish(uw.verdict(_reading(94, 10), 93, 98))
    published = json.loads((tmp_path / "sc" / aas.USAGE_FILENAME).read_text())
    assert published["over"] is True and published["binding"] == "session"


def test_publish_leaves_no_temp_file_behind(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    uw.publish(uw.verdict(_reading(50, 10), 93, 98))
    names = {p.name for p in (tmp_path / "sc").iterdir()}
    assert names == {aas.USAGE_FILENAME}      # atomic replace, no .tmp residue


def test_publish_overwrites_the_previous_reading(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    uw.publish(uw.verdict(_reading(94, 10), 93, 98))
    uw.publish(uw.verdict(_reading(20, 10), 93, 98))
    assert json.loads(uw.published_path().read_text())["over"] is False


# ── run_once ─────────────────────────────────────────────────────────────────

def test_run_once_publishes_and_logs_the_gate(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    monkeypatch.setattr(uw._ur, "read_usage", lambda *a, **k: _reading(94, 29))
    record = uw.run_once(93, 98, 60)
    assert record["over"] is True
    out = capsys.readouterr().out
    assert "session 94% / weekly 29%" in out and "GATE ON" in out


def test_run_once_logs_clear_below_the_limits(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    monkeypatch.setattr(uw._ur, "read_usage", lambda *a, **k: _reading(40, 29))
    assert uw.run_once(93, 98, 60)["over"] is False
    assert "clear" in capsys.readouterr().out


def test_run_once_publishes_even_when_unreadable(tmp_path, monkeypatch, capsys):
    """Publishing ok:false is how a stale gate gets cleared rather than stuck on."""
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    monkeypatch.setattr(uw._ur, "read_usage",
                        lambda *a, **k: _reading(99, 99, ok=False))
    record = uw.run_once(93, 98, 60)
    assert record["ok"] is False and record["over"] is False
    assert uw.published_path().exists()
    assert "unreadable" in capsys.readouterr().out


def test_run_once_never_touches_session_dirs(tmp_path, monkeypatch):
    """The daemon is a publisher: no latches, no per-session writes."""
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    aas.arm_session("s1")
    monkeypatch.setattr(uw._ur, "read_usage", lambda *a, **k: _reading(99, 99))
    uw.run_once(93, 98, 60)
    assert not aas.is_paused("s1")
    assert not (tmp_path / "sc" / "mg-session-s1" / aas.USAGE_MUTE_FILENAME).exists()


# ── lock / CLI ───────────────────────────────────────────────────────────────

def test_lock_is_exclusive(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    first = uw.acquire_lock()
    assert first is not None
    assert uw.acquire_lock() is None      # a second publisher must not start
    first.close()
    second = uw.acquire_lock()
    assert second is not None
    second.close()


def test_cli_once_publishes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    monkeypatch.setattr(uw._ur, "read_usage", lambda *a, **k: _reading(94, 29))
    assert uw.main(["--once", "--no-lock"]) == 0
    assert json.loads(uw.published_path().read_text())["pct"] == 94


def test_cli_defaults_are_93_98():
    assert (uw.DEFAULT_SESSION_MAX, uw.DEFAULT_WEEKLY_MAX) == (93, 98)
