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
    p = tmp_path / "sc" / "mg-session-abc123" / aas.SIDECAR_FILENAME
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
    p = tmp_path / "sc" / "mg-session-s1" / aas.SIDECAR_FILENAME
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


# ── pause latch ──────────────────────────────────────────────────────────────

def test_pause_writes_latch_with_note(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    aas.pause_session("p1", "check the migration first")
    p = tmp_path / "sc" / "mg-session-p1" / aas.PAUSE_FILENAME
    data = json.loads(p.read_text())
    assert data["note"] == "check the migration first"
    assert isinstance(data["paused_at_ms"], int)
    assert aas.is_paused("p1")


def test_pause_without_note_omits_field(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    aas.pause_session("p2")
    p = tmp_path / "sc" / "mg-session-p2" / aas.PAUSE_FILENAME
    assert "note" not in json.loads(p.read_text())


def test_unpause_clears_latch(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    aas.pause_session("p3")
    assert aas.unpause_session("p3") is True
    assert not aas.is_paused("p3")
    assert aas.unpause_session("p3") is False


def test_pause_and_arm_are_independent(tmp_path, monkeypatch):
    """Separate sidecars: neither control may disturb the other."""
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    aas.arm_session("p4")
    aas.pause_session("p4")
    assert aas.is_armed("p4") and aas.is_paused("p4")
    aas.unpause_session("p4")
    assert aas.is_armed("p4")
    aas.pause_session("p4")
    aas.disarm_session("p4")
    assert aas.is_paused("p4")


def test_pause_latch_never_expires(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    p = tmp_path / "sc" / "mg-session-p5" / aas.PAUSE_FILENAME
    p.parent.mkdir(parents=True)
    ancient = int((time.time() - 30 * 24 * 3600) * 1000)
    p.write_text(json.dumps({"paused_at_ms": ancient}))
    assert aas.is_paused("p5")


# ── guard activity ───────────────────────────────────────────────────────────

def _write_bridge(tmp_path, sid, mtime):
    p = tmp_path / "sc" / f"mg-session-{sid}" / aas.BRIDGE_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"state": "ON", "ts": int(mtime)}))
    os.utime(p, (mtime, mtime))
    return p


def test_guard_state_never_without_bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    assert aas.guard_state("g0", time.time()) == "never"


def test_guard_state_active_when_bridge_keeps_pace(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    now = time.time()
    _write_bridge(tmp_path, "g1", now - 10)
    assert aas.guard_state("g1", now) == "active"


def test_guard_state_active_when_session_idle(tmp_path, monkeypatch):
    """Both stale is not 'deferring' — the guard was active as of last activity."""
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    old = time.time() - 6 * 3600
    _write_bridge(tmp_path, "g2", old)
    assert aas.guard_state("g2", old + 5) == "active"


def test_guard_state_deferring_when_bridge_lags_activity(tmp_path, monkeypatch):
    """Session demonstrably working while the guard writes nothing → CC-vetted mode."""
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    now = time.time()
    _write_bridge(tmp_path, "g3", now - aas.GUARD_LAG_S - 120)
    assert aas.guard_state("g3", now) == "deferring"


# ── last activity (parent + subagent transcripts) ────────────────────────────

def test_last_activity_uses_newest_subagent(tmp_path):
    projects = tmp_path / "projects"
    path = _write_session(projects, "p", "sub-0001", [_user("hi")])
    base = time.time() - 3600
    os.utime(path, (base, base))
    subdir = path.parent / "sub-0001" / "subagents"
    subdir.mkdir(parents=True)
    agent = subdir / "agent-abc.jsonl"
    agent.write_text("{}\n")
    os.utime(agent, (base + 3000, base + 3000))
    assert aas.last_activity(path) == base + 3000


def test_picker_order_follows_subagent_activity(tmp_path, monkeypatch):
    """A session working through subagents must not sort below an idle one."""
    projects = tmp_path / "projects"
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(projects))
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    base = time.time() - 3600
    busy = _write_session(projects, "p", "busy-0001", [_user("run it")])
    idle = _write_session(projects, "p", "idle-0002", [_user("nothing")])
    os.utime(busy, (base, base))
    os.utime(idle, (base + 600, base + 600))
    subdir = busy.parent / "busy-0001" / "subagents"
    subdir.mkdir(parents=True)
    agent = subdir / "agent-xyz.jsonl"
    agent.write_text("{}\n")
    os.utime(agent, (base + 3000, base + 3000))
    assert [f.stem for f in aas.all_session_files()] == ["busy-0001", "idle-0002"]


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
    assert info["paused"] is False
    assert info["guard"] == "never"  # no bridge → guard has never run there
    aas.arm_session("deadbeef-0001")
    assert aas.session_info(path)["armed"] is True
    aas.pause_session("deadbeef-0001")
    assert aas.session_info(path)["paused"] is True


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


def test_cli_pause_and_unpause(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    projects = tmp_path / "projects"
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(projects))
    _write_session(projects, "-home-u-proj", "cafe0000-1111", [_user("hi")], cwd="/home/u/proj")

    assert aas.main(["pause", "cafe", "look", "at", "the", "plan"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] and res["action"] == "paused" and res["id"] == "cafe0000-1111"
    assert res["note"] == "look at the plan"
    assert res["guard"] == "never"  # surfaced so the caller can warn
    assert aas.is_paused("cafe0000-1111")

    assert aas.main(["unpause", "cafe"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] and res["action"] == "unpaused" and res["was_paused"] is True
    assert not aas.is_paused("cafe0000-1111")


def test_cli_pause_no_match(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(tmp_path / "projects"))
    (tmp_path / "projects").mkdir()
    assert aas.main(["pause", "ghost"]) == 1
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] is False and "no session" in res["error"]


def test_cli_arm_no_match(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(tmp_path / "projects"))
    (tmp_path / "projects").mkdir()
    assert aas.main(["arm", "ghost"]) == 1
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] is False and "no session" in res["error"]
