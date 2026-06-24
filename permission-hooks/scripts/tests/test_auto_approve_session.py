"""Tests for auto-approve-session.py."""
import importlib
import json
import os
import sys
import time

# Import the hyphenated script module (mirrors test_permission_guard.py).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
aas = importlib.import_module("auto-approve-session")


# ── helpers ──────────────────────────────────────────────────────────────────

def _user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def _user_blocks(blocks):
    return {"type": "user", "message": {"role": "user", "content": blocks}}


def _assistant(text):
    return {"type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _tool_result(tuid="t1"):
    return {"type": "user", "message": {"role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tuid, "content": "out"}]}}


def _write_session(projects_dir, project_name, sid, entries, cwd="/home/u/proj"):
    pdir = projects_dir / project_name
    pdir.mkdir(parents=True, exist_ok=True)
    path = pdir / f"{sid}.jsonl"
    with open(path, "w") as f:
        for e in entries:
            e = dict(e)
            e.setdefault("cwd", cwd)
            f.write(json.dumps(e) + "\n")
    return path


# ── sidecar arm / is_armed / disarm ──────────────────────────────────────────

def test_arm_writes_sidecar(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    aas.arm_session("abc123")
    p = tmp_path / "sc" / "mg-session-abc123" / "context.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["command"] == "AUTO-APPROVE"
    assert isinstance(data["timestamp_ms"], int)
    assert aas.is_armed("abc123")


def test_is_armed_stale_and_future(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    aas.arm_session("s1")
    now = time.time()
    assert aas.is_armed("s1", now=now)
    assert not aas.is_armed("s1", now=now + aas.CONTEXT_TTL_S + 5)
    # future timestamp (clock skew) is not "armed"
    p = tmp_path / "sc" / "mg-session-s1" / "context.json"
    p.write_text(json.dumps({"command": "AUTO-APPROVE",
                             "timestamp_ms": int((now + 100) * 1000)}))
    assert not aas.is_armed("s1", now=now)


def test_is_armed_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    assert not aas.is_armed("nope")


def test_disarm(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    aas.arm_session("d1")
    assert aas.disarm_session("d1") is True
    assert not aas.is_armed("d1")
    assert aas.disarm_session("d1") is False


# ── session resolution ───────────────────────────────────────────────────────

def test_resolve_exact_and_prefix(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(projects))
    _write_session(projects, "-home-u-projA", "aaaa1111-2222", [_user("hi")])
    _write_session(projects, "-home-u-projB", "bbbb3333-4444", [_user("yo")])
    path, err = aas.resolve_session_file("aaaa1111-2222")
    assert err is None and path.stem == "aaaa1111-2222"
    path, err = aas.resolve_session_file("aaaa")
    assert err is None and path.stem.startswith("aaaa")
    path, err = aas.resolve_session_file("zzzz")
    assert path is None and "no session" in err


def test_resolve_ambiguous(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(projects))
    _write_session(projects, "p", "ab11", [_user("x")])
    _write_session(projects, "p", "ab22", [_user("y")])
    path, err = aas.resolve_session_file("ab")
    assert path is None and "ambiguous" in err


# ── user-command labels ──────────────────────────────────────────────────────

def test_label_plain_prompt():
    assert aas.user_command_label(_user("  fix the bug  ")) == "fix the bug"


def test_label_text_blocks():
    assert aas.user_command_label(_user_blocks([{"type": "text", "text": "hello world"}])) == "hello world"


def test_label_tool_result_is_none():
    assert aas.user_command_label(_tool_result()) is None


def test_label_slash_command_with_args():
    e = _user("<command-name>/gsd:execute-phase</command-name>\n"
              "<command-message>x</command-message>\n<command-args>12</command-args>")
    assert aas.user_command_label(e) == "/gsd:execute-phase 12"


def test_label_slash_command_no_args():
    e = _user("<command-name>/mg:auto-approve</command-name>\n<command-args></command-args>")
    assert aas.user_command_label(e) == "/mg:auto-approve"


def test_label_meta_and_sidechain_are_none():
    meta = _user("real text")
    meta["isMeta"] = True
    side = _user("sub text")
    side["isSidechain"] = True
    assert aas.user_command_label(meta) is None
    assert aas.user_command_label(side) is None


def test_label_system_reminder_stripped_to_none():
    assert aas.user_command_label(_user("<system-reminder>noise</system-reminder>")) is None


def test_label_system_reminder_keeps_real_prompt():
    e = _user("<system-reminder>ctx</system-reminder>\nwhat is the bug?")
    assert aas.user_command_label(e) == "what is the bug?"


def test_label_assistant_is_none():
    assert aas.user_command_label(_assistant("hi")) is None


def test_label_truncates():
    out = aas.user_command_label(_user("x" * 200))
    assert len(out) <= aas._LABEL_MAX_LEN and out.endswith("…")


# ── session_commands (condensed vs split) ────────────────────────────────────

def test_session_commands_condensed(tmp_path):
    path = _write_session(tmp_path / "projects", "p", "sid-small",
                          [_user("one"), _assistant("a"), _user("two"),
                           _tool_result(), _user("three")])
    cmds = aas.session_commands(path)
    assert cmds["condensed"] is True
    assert cmds["first"] == ["one", "two", "three"]
    assert cmds["last"] == []


def test_session_commands_split(tmp_path):
    entries = []
    for i in range(8):
        entries.append(_user(f"cmd{i}"))
        entries.append(_tool_result())
    path = _write_session(tmp_path / "projects", "p", "sid-big", entries)
    cmds = aas.session_commands(path)
    assert cmds["condensed"] is False
    assert cmds["first"] == ["cmd0", "cmd1", "cmd2"]
    assert cmds["last"] == ["cmd5", "cmd6", "cmd7"]


# ── session_info ─────────────────────────────────────────────────────────────

def test_session_info(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    projects = tmp_path / "projects"
    path = _write_session(projects, "-home-u-road_runner", "deadbeef-0001",
                          [_user("<command-name>/gsd:execute-phase</command-name>"),
                           _user("why prod?")], cwd="/home/u/road_runner")
    info = aas.session_info(path)
    assert info["id"] == "deadbeef-0001"
    assert info["short_id"] == "deadbeef"
    assert info["project"] == "road_runner"
    assert info["armed"] is False
    assert "/gsd:execute-phase" in info["commands"]["first"][0]
    aas.arm_session("deadbeef-0001")
    assert aas.session_info(path)["armed"] is True


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_list_limit_and_order(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    projects = tmp_path / "projects"
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(projects))
    base = time.time()
    for i in range(12):
        p = _write_session(projects, "p", f"sess-{i:02d}", [_user(f"hi {i}")])
        os.utime(p, (base + i, base + i))  # sess-11 is newest
    assert aas.main(["list", "--limit", "10"]) == 0
    sessions = json.loads(capsys.readouterr().out)["sessions"]
    assert len(sessions) == 10
    assert sessions[0]["id"] == "sess-11"
    assert sessions[-1]["id"] == "sess-02"


def test_cli_arm_and_off(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    projects = tmp_path / "projects"
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(projects))
    _write_session(projects, "-home-u-proj", "feedface-9999", [_user("hi")], cwd="/home/u/proj")

    assert aas.main(["arm", "feedface"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] and res["action"] == "armed" and res["id"] == "feedface-9999"
    assert res["project"] == "proj" and res["ttl_minutes"] == 30
    assert aas.is_armed("feedface-9999")

    assert aas.main(["off", "feedface"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] and res["was_armed"] is True
    assert not aas.is_armed("feedface-9999")


def test_cli_arm_no_match(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(tmp_path / "projects"))
    (tmp_path / "projects").mkdir()
    assert aas.main(["arm", "ghost"]) == 1
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] is False and "no session" in res["error"]
