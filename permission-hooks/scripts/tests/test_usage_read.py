"""Tests for usage-read.py."""
import importlib
import json
import os
import subprocess
import sys
from datetime import datetime

# Import the hyphenated script module (mirrors test_permission_guard.py).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
ur = importlib.import_module("usage-read")


# Captured verbatim from `claude -p /usage` (2026-07-29), trimmed after the
# authoritative lines plus one line of the approximate block that follows.
REAL_OUTPUT = """You are currently using your subscription to power your Claude Code usage

Current session: 93% used · resets Jul 29, 6:49pm (Europe/Berlin)
Current week (all models): 28% used · resets Aug 3, 8:59pm (Europe/Berlin)
Current week (Fable): 0% used

What's contributing to your limits usage?
Approximate, based on local sessions on this machine — does not include other devices or claude.ai.

Last 24h · 2836 requests · 31 sessions
  93% of your usage came from subagent-heavy sessions
"""

NOW = datetime(2026, 7, 29, 17, 30)


# ── parsing ──────────────────────────────────────────────────────────────────

def test_parses_both_authoritative_lines():
    r = ur.parse_usage(REAL_OUTPUT, now=NOW)
    assert r["ok"] is True and r["error"] is None
    assert r["session_pct"] == 93
    assert r["session_reset"] == "Jul 29, 6:49pm"
    assert r["session_reset_iso"] == "2026-07-29T18:49:00"
    assert r["weekly_pct"] == 28
    assert r["weekly_reset_iso"] == "2026-08-03T20:59:00"


def test_ignores_the_approximate_block():
    """'93% of your usage came from …' must not be mistaken for a limit."""
    r = ur.parse_usage(REAL_OUTPUT, now=NOW)
    assert r["session_pct"] == 93 and r["weekly_pct"] == 28


def test_per_model_weekly_line_is_not_the_weekly_limit():
    body = REAL_OUTPUT.replace("Current week (all models): 28%", "Current week (all models): 41%")
    assert ur.parse_usage(body, now=NOW)["weekly_pct"] == 41


def test_missing_line_is_not_ok():
    body = "Current session: 93% used · resets Jul 29, 6:49pm (Europe/Berlin)\n"
    r = ur.parse_usage(body, now=NOW)
    assert r["ok"] is False
    assert "could not parse" in r["error"]
    assert r["session_pct"] == 93       # partial data is still reported


def test_empty_body_is_not_ok():
    for body in ("", None):
        assert ur.parse_usage(body, now=NOW)["ok"] is False


def test_reset_without_timezone_suffix():
    body = ("Current session: 5% used · resets Jul 29, 6:49pm\n"
            "Current week (all models): 3% used · resets Aug 3, 8:59pm\n")
    assert ur.parse_usage(body, now=NOW)["session_reset_iso"] == "2026-07-29T18:49:00"


def test_unparseable_reset_keeps_percentage():
    body = ("Current session: 77% used · resets soon\n"
            "Current week (all models): 3% used · resets Aug 3, 8:59pm\n")
    r = ur.parse_usage(body, now=NOW)
    assert r["ok"] is True and r["session_pct"] == 77
    assert r["session_reset_iso"] is None


# ── reset parsing edge cases ─────────────────────────────────────────────────

def test_reset_on_the_hour_omits_minutes():
    """Observed live: 'Aug 3, 9pm'. Parsing it to None would make the window unmutable."""
    assert ur.parse_reset("Aug 3, 9pm", now=NOW) == datetime(2026, 8, 3, 21, 0)
    assert ur.parse_reset("Jul 29, 7pm", now=NOW) == datetime(2026, 7, 29, 19, 0)


def test_on_the_hour_reset_reaches_the_reading():
    body = ("Current session: 5% used · resets Jul 29, 11:50pm (Europe/Berlin)\n"
            "Current week (all models): 29% used · resets Aug 3, 9pm (Europe/Berlin)\n")
    r = ur.parse_usage(body, now=NOW)
    assert r["weekly_reset_iso"] == "2026-08-03T21:00:00"


def test_reset_rolls_into_next_year():
    """A 'Jan 2' reset read on Dec 31 is next year, not ten months ago."""
    dt = ur.parse_reset("Jan 2, 1:15am", now=datetime(2026, 12, 31, 23, 40))
    assert dt == datetime(2027, 1, 2, 1, 15)


def test_reset_just_passed_stays_in_current_year():
    """Within the hour of grace a just-passed reset must not jump a year."""
    dt = ur.parse_reset("Jul 29, 6:49pm", now=datetime(2026, 7, 29, 19, 10))
    assert dt == datetime(2026, 7, 29, 18, 49)


def test_reset_none_and_garbage():
    assert ur.parse_reset(None, now=NOW) is None
    assert ur.parse_reset("whenever", now=NOW) is None


# ── subprocess contract ──────────────────────────────────────────────────────

def _fake_run(captured, stdout="", returncode=0, raises=None):
    def run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    return run


def test_read_usage_uses_no_session_persistence(monkeypatch):
    """Without the flag every read litters a phantom /usage session transcript."""
    captured = {}
    envelope = json.dumps({"is_error": False, "num_turns": 0, "result": REAL_OUTPUT})
    monkeypatch.setattr(ur.subprocess, "run", _fake_run(captured, stdout=envelope))
    r = ur.read_usage(now=NOW)
    assert r["ok"] is True and r["session_pct"] == 93
    assert "--no-session-persistence" in captured["cmd"]
    assert captured["cmd"][:5] == ["claude", "-p", "/usage", "--output-format", "json"]
    assert captured["kwargs"]["timeout"] == ur.DEFAULT_TIMEOUT_S


def test_read_usage_handles_plain_text_output(monkeypatch):
    monkeypatch.setattr(ur.subprocess, "run", _fake_run({}, stdout=REAL_OUTPUT))
    assert ur.read_usage(now=NOW)["session_pct"] == 93


def test_read_usage_error_envelope_is_not_ok(monkeypatch):
    envelope = json.dumps({"is_error": True, "result": "boom"})
    monkeypatch.setattr(ur.subprocess, "run", _fake_run({}, stdout=envelope))
    assert ur.read_usage(now=NOW)["ok"] is False


def test_read_usage_nonzero_exit_is_not_ok(monkeypatch):
    monkeypatch.setattr(ur.subprocess, "run", _fake_run({}, stdout="", returncode=1))
    r = ur.read_usage(now=NOW)
    assert r["ok"] is False and "exited 1" in r["error"]


def test_read_usage_timeout_is_not_ok(monkeypatch):
    monkeypatch.setattr(ur.subprocess, "run",
                        _fake_run({}, raises=subprocess.TimeoutExpired("claude", 60)))
    r = ur.read_usage(now=NOW)
    assert r["ok"] is False and "could not run" in r["error"]


def test_read_usage_missing_cli_is_not_ok(monkeypatch):
    monkeypatch.setattr(ur.subprocess, "run",
                        _fake_run({}, raises=FileNotFoundError("claude")))
    assert ur.read_usage(now=NOW)["ok"] is False


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_prints_json_and_exit_codes(monkeypatch, capsys):
    envelope = json.dumps({"is_error": False, "result": REAL_OUTPUT})
    monkeypatch.setattr(ur.subprocess, "run", _fake_run({}, stdout=envelope))
    assert ur.main([]) == 0
    assert json.loads(capsys.readouterr().out)["session_pct"] == 93

    monkeypatch.setattr(ur.subprocess, "run", _fake_run({}, stdout="nothing useful"))
    assert ur.main([]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
