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


def _write_agent(directory, name, mtime, meta=None):
    """An agent-<id>.jsonl (+ optional .meta.json) as CC writes them."""
    directory.mkdir(parents=True, exist_ok=True)
    agent = directory / f"{name}.jsonl"
    agent.write_text("{}\n")
    os.utime(agent, (mtime, mtime))
    if meta is not None:
        (directory / f"{name}.meta.json").write_text(json.dumps(meta))
    return agent


def _write_subagent(session_path, name, mtime, meta=None):
    """A Task subagent: <session>/subagents/agent-<id>.jsonl"""
    subdir = session_path.parent / session_path.stem / "subagents"
    return _write_agent(subdir, name, mtime, meta)


def _write_workflow_agent(session_path, run_id, name, mtime,
                          meta={"agentType": "workflow-subagent", "spawnDepth": 1}):
    """A workflow agent: <session>/subagents/workflows/<run_id>/agent-<id>.jsonl"""
    run = session_path.parent / session_path.stem / "subagents" / "workflows" / run_id
    return _write_agent(run, name, mtime, meta)


def _write_workflow_journal(session_path, run_id, mtime):
    run = session_path.parent / session_path.stem / "subagents" / "workflows" / run_id
    run.mkdir(parents=True, exist_ok=True)
    journal = run / "journal.jsonl"
    journal.write_text('{"type":"started","agentId":"a1"}\n')
    os.utime(journal, (mtime, mtime))
    return journal


def _write_workflow_script(session_path, run_id, wf_name):
    """The persisted script — the only on-disk source of the workflow's name."""
    sdir = session_path.parent / session_path.stem / "workflows" / "scripts"
    sdir.mkdir(parents=True, exist_ok=True)
    path = sdir / f"{wf_name}-{run_id}.js"
    path.write_text(f"export const meta = {{ name: '{wf_name}' }}\n")
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


# ── session-limit mute ───────────────────────────────────────────────────────

def _publish(tmp_path, over=True, binding="session", age_s=0,
             session_iso="2026-07-29T18:49:00", weekly_iso="2026-08-03T20:59:00",
             ok=True):
    p = tmp_path / "sc" / aas.USAGE_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    window = session_iso if binding == "session" else weekly_iso
    p.write_text(json.dumps({
        "ok": ok, "over": over, "binding": binding, "pct": 94,
        "window_iso": window, "window_human": "Jul 29, 6:49pm",
        "session_reset_iso": session_iso, "weekly_reset_iso": weekly_iso,
        "read_at_ms": int((time.time() - age_s) * 1000),
    }))
    return p


def test_usage_state_reports_gated_then_muted(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    reading = json.loads(_publish(tmp_path).read_text())
    assert aas.usage_state("s1") == "gated"
    aas.mute_session_limit("s1", reading)
    assert aas.usage_state("s1") == "muted"
    aas.unmute_session_limit("s1")
    assert aas.usage_state("s1") == "gated"


def test_usage_state_clear_when_under_the_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    _publish(tmp_path, over=False)
    assert aas.usage_state("s1") == "clear"


def test_usage_state_unknown_without_a_publisher(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    assert aas.usage_state("s1") == "unknown"
    _publish(tmp_path, age_s=aas.USAGE_STALE_S + 600)
    assert aas.usage_state("s1") == "unknown"      # stale reading is not a gate


def test_mute_covers_whichever_limit_binds(tmp_path, monkeypatch):
    """A pre-emptive mute records both windows, so a weekly bind is covered too."""
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    reading = json.loads(_publish(tmp_path, over=False).read_text())
    aas.mute_session_limit("s1", reading)
    _publish(tmp_path, binding="weekly")
    assert aas.usage_state("s1") == "muted"


def test_mute_expires_with_its_window(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    reading = json.loads(_publish(tmp_path).read_text())
    aas.mute_session_limit("s1", reading)
    _publish(tmp_path, session_iso="2026-07-29T23:49:00")   # next window
    assert aas.usage_state("s1") == "gated"


def test_mute_tolerates_reported_drift(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    reading = json.loads(_publish(tmp_path).read_text())
    aas.mute_session_limit("s1", reading)
    _publish(tmp_path, session_iso="2026-07-29T18:50:00")   # same window, 1 min drift
    assert aas.usage_state("s1") == "muted"


def test_corrupt_mute_does_not_silence(tmp_path, monkeypatch):
    """A mute grants silence, so an unparseable one must fail toward warning."""
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    _publish(tmp_path)
    p = tmp_path / "sc" / "mg-session-s1" / aas.USAGE_MUTE_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not-json{{{")
    assert aas.usage_state("s1") == "gated"


def test_unmute_missing_reports_false(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    assert aas.unmute_session_limit("nope") is False


def test_mute_and_pause_are_independent(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    reading = json.loads(_publish(tmp_path).read_text())
    aas.pause_session("s1", "manual")
    aas.mute_session_limit("s1", reading)
    aas.unmute_session_limit("s1")
    assert aas.is_paused("s1")


def test_cli_mute_and_unmute(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    projects = tmp_path / "projects"
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(projects))
    _write_session(projects, "-home-u-proj", "beefcafe-0001", [_user("hi")], cwd="/home/u/proj")
    _publish(tmp_path)

    assert aas.main(["mute-session-limit", "beefcafe"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] and res["action"] == "muted" and res["usage"] == "muted"
    assert res["windows"]["session"] == "2026-07-29T18:49:00"

    assert aas.main(["unmute-session-limit", "beefcafe"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] and res["was_muted"] is True and res["usage"] == "gated"


def test_cli_mute_without_a_reading_refuses(tmp_path, monkeypatch, capsys):
    """Writing a mute with no window would silence nothing — say so instead."""
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    projects = tmp_path / "projects"
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(projects))
    _write_session(projects, "p", "dead0000-0001", [_user("hi")])
    assert aas.main(["mute-session-limit", "dead0000"]) == 1
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] is False and "mg-usage-watch" in res["error"]


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


def test_last_activity_sees_workflow_agents(tmp_path):
    """Workflow agents live a level below subagents/ — a flat glob missed them."""
    projects = tmp_path / "projects"
    path = _write_session(projects, "p", "wf-0001", [_user("hi")])
    base = time.time() - 3600
    os.utime(path, (base, base))
    _write_workflow_agent(path, "wf_abc123-def", "agent-a1", base + 3400)
    assert aas.last_activity(path) == base + 3400


def test_picker_order_follows_workflow_activity(tmp_path, monkeypatch):
    """A session in the middle of a dynamic workflow must sort as busy."""
    projects = tmp_path / "projects"
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(projects))
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    base = time.time() - 3600
    busy = _write_session(projects, "p", "wbusy-001", [_user("ultracode this")])
    idle = _write_session(projects, "p", "widle-002", [_user("nothing")])
    os.utime(busy, (base, base))
    os.utime(idle, (base + 600, base + 600))
    _write_workflow_agent(busy, "wf_run-001", "agent-a1", base + 3000)
    assert [f.stem for f in aas.all_session_files()] == ["wbusy-001", "widle-002"]


# ── live activity (what is running now) ──────────────────────────────────────

def test_activity_empty_when_nothing_runs(tmp_path):
    path = _write_session(tmp_path / "projects", "p", "quiet-001", [_user("hi")])
    assert aas.session_activity(path) == {"workflows": [], "subagents_live": 0,
                                          "subagents": []}


def test_activity_names_live_subagents_newest_first(tmp_path):
    """The picker's real gap: a guarded call from subagent #9 had no label."""
    path = _write_session(tmp_path / "projects", "p", "sub-live", [_user("go")])
    now = time.time()
    _write_subagent(path, "agent-a1", now - 90,
                    {"agentType": "general-purpose", "description": "Research barrier count"})
    _write_subagent(path, "agent-a2", now - 5,
                    {"agentType": "Explore", "description": "Find the callers"})
    act = aas.session_activity(path, now)
    assert act["subagents_live"] == 2
    assert act["subagents"] == [{"type": "Explore", "description": "Find the callers"},
                                {"type": "general-purpose",
                                 "description": "Research barrier count"}]


def test_activity_ignores_finished_subagents(tmp_path):
    path = _write_session(tmp_path / "projects", "p", "sub-old", [_user("go")])
    now = time.time()
    _write_subagent(path, "agent-done", now - aas.LIVE_WINDOW_S - 60,
                    {"agentType": "general-purpose", "description": "Long gone"})
    act = aas.session_activity(path, now)
    assert act["subagents_live"] == 0 and act["subagents"] == []


def test_activity_caps_labels_but_not_the_count(tmp_path):
    path = _write_session(tmp_path / "projects", "p", "sub-many", [_user("go")])
    now = time.time()
    for i in range(7):
        _write_subagent(path, f"agent-a{i}", now - i,
                        {"agentType": "general-purpose", "description": f"task {i}"})
    act = aas.session_activity(path, now)
    assert act["subagents_live"] == 7
    assert [s["description"] for s in act["subagents"]] == ["task 0", "task 1", "task 2"]


def test_activity_survives_missing_and_corrupt_meta(tmp_path):
    path = _write_session(tmp_path / "projects", "p", "sub-nometa", [_user("go")])
    now = time.time()
    _write_subagent(path, "agent-bare", now - 1)                 # no meta sidecar
    bad = _write_subagent(path, "agent-bad", now - 2, {"agentType": "x"})
    bad.with_suffix(".meta.json").write_text("not-json{{{")
    act = aas.session_activity(path, now)
    assert act["subagents_live"] == 2
    assert act["subagents"] == [{"type": "", "description": ""},
                                {"type": "", "description": ""}]


def test_activity_reports_workflow_run_by_name(tmp_path):
    path = _write_session(tmp_path / "projects", "p", "wf-live", [_user("ultracode")])
    now = time.time()
    _write_workflow_script(path, "wf_e94972d4-091", "connection-budget-redesign")
    _write_workflow_agent(path, "wf_e94972d4-091", "agent-a1", now - 3)
    _write_workflow_agent(path, "wf_e94972d4-091", "agent-a2", now - 20)
    _write_workflow_agent(path, "wf_e94972d4-091", "agent-a3",
                          now - aas.LIVE_WINDOW_S - 60)          # already finished
    act = aas.session_activity(path, now)
    assert act["workflows"] == [{"name": "connection-budget-redesign",
                                 "run": "wf_e94972d4-091", "agents_live": 2}]
    # workflow agents are not double-counted as plain subagents
    assert act["subagents_live"] == 0


def test_activity_keeps_a_workflow_between_phases(tmp_path):
    """At a barrier no agent is writing — the journal is the proof of life."""
    path = _write_session(tmp_path / "projects", "p", "wf-barrier", [_user("go")])
    now = time.time()
    _write_workflow_script(path, "wf_run-002", "review-changes")
    _write_workflow_agent(path, "wf_run-002", "agent-a1", now - aas.LIVE_WINDOW_S - 60)
    _write_workflow_journal(path, "wf_run-002", now - 4)
    assert aas.session_activity(path, now)["workflows"] == [
        {"name": "review-changes", "run": "wf_run-002", "agents_live": 0}]


def test_activity_drops_a_finished_workflow(tmp_path):
    path = _write_session(tmp_path / "projects", "p", "wf-done", [_user("go")])
    now = time.time()
    old = now - aas.LIVE_WINDOW_S - 60
    _write_workflow_script(path, "wf_run-003", "old-run")
    _write_workflow_agent(path, "wf_run-003", "agent-a1", old)
    _write_workflow_journal(path, "wf_run-003", old)
    assert aas.session_activity(path, now)["workflows"] == []


def test_activity_falls_back_to_run_id_without_a_script(tmp_path):
    path = _write_session(tmp_path / "projects", "p", "wf-noscript", [_user("go")])
    now = time.time()
    _write_workflow_agent(path, "wf_run-004", "agent-a1", now - 2)
    assert aas.session_activity(path, now)["workflows"] == [
        {"name": "wf_run-004", "run": "wf_run-004", "agents_live": 1}]


def test_activity_reports_concurrent_runs_and_subagents(tmp_path):
    path = _write_session(tmp_path / "projects", "p", "wf-both", [_user("go")])
    now = time.time()
    _write_workflow_script(path, "wf_run-005", "first-run")
    _write_workflow_script(path, "wf_run-006", "second-run")
    _write_workflow_agent(path, "wf_run-005", "agent-a1", now - 2)
    _write_workflow_agent(path, "wf_run-006", "agent-a2", now - 3)
    _write_subagent(path, "agent-plain", now - 1,
                    {"agentType": "general-purpose", "description": "Side quest"})
    act = aas.session_activity(path, now)
    assert [w["name"] for w in act["workflows"]] == ["first-run", "second-run"]
    assert act["subagents_live"] == 1
    assert act["subagents"][0]["description"] == "Side quest"


def test_activity_truncates_a_long_description(tmp_path):
    path = _write_session(tmp_path / "projects", "p", "sub-long", [_user("go")])
    now = time.time()
    _write_subagent(path, "agent-a1", now - 1,
                    {"agentType": "general-purpose", "description": "x" * 200})
    desc = aas.session_activity(path, now)["subagents"][0]["description"]
    assert len(desc) <= aas._LABEL_MAX_LEN and desc.endswith("…")


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
    assert info["activity"] == {"workflows": [], "subagents_live": 0, "subagents": []}
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


def test_cli_list_carries_activity(tmp_path, monkeypatch, capsys):
    """The picker renders straight from this — a live run must reach the caller."""
    monkeypatch.setenv("MG_SESSION_BASE", str(tmp_path / "sc"))
    projects = tmp_path / "projects"
    monkeypatch.setenv("MG_CLAUDE_PROJECTS_DIR", str(projects))
    path = _write_session(projects, "p", "live-0001", [_user("ultracode this")])
    now = time.time()
    _write_workflow_script(path, "wf_run-007", "find-flaky-tests")
    _write_workflow_agent(path, "wf_run-007", "agent-a1", now - 2)
    _write_subagent(path, "agent-plain", now - 2,
                    {"agentType": "Explore", "description": "Sweep the callers"})

    assert aas.main(["list"]) == 0
    session = json.loads(capsys.readouterr().out)["sessions"][0]
    assert session["id"] == "live-0001"
    assert session["last_active"].endswith("s ago")
    assert session["activity"]["workflows"][0]["name"] == "find-flaky-tests"
    assert session["activity"]["subagents"][0]["description"] == "Sweep the callers"


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
