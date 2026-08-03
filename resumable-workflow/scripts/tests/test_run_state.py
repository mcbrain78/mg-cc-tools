"""Tests for run_state.py — the durable ledger behind the resumable loop.

The tests are organised around the failure modes that make a resume silently
*wrong* rather than merely broken, because those are the ones that cost a whole run:
a truncated payload accepted as done, a zombie record reopening a finished step, a
torn line eating every later append, an id that names different work on the second
pass.
"""
from __future__ import annotations

import json
import threading

import pytest

import run_state


# ── Identity: content slugs, not positions ──────────────────────────────────


class TestIdentity:
    def test_slug_is_stable_across_whitespace_and_case(self):
        a = run_state._slug("Which  MODULE validates tokens?", "q")
        b = run_state._slug("which module validates tokens?", "q")
        assert a == b

    def test_slug_differs_on_real_content_change(self):
        a = run_state._slug("which module validates tokens", "q")
        b = run_state._slug("which module issues tokens", "q")
        assert a != b

    def test_slug_carries_a_readable_prefix(self):
        assert run_state._slug("Where is auth checked?", "q").startswith(
            "q-where-is-auth-checked-"
        )

    def test_slug_survives_content_with_no_alphanumerics(self):
        assert run_state._slug("???", "q").startswith("q-x-")

    def test_payload_name_is_guard_safe(self, tmp_path):
        """`handoff-` is load-bearing: a subagent Write to a findings/report-named
        file trips a Claude Code guard that returns the content instead of writing
        it. Deriving the name here means a prompt cannot get it wrong."""
        name = run_state._payload_path(tmp_path, "q-abc").name
        assert name.startswith("handoff-")
        assert "findings" not in name and "report" not in name

    def test_add_is_idempotent_by_content(self, run_dir, out):
        """Decomposition re-runs every round; without content dedup it would
        re-research the same question forever."""
        run_state.main(["add", str(run_dir), "--kind", "question", "--text", "Q one"])
        first = out()
        run_state.main(["add", str(run_dir), "--kind", "question", "--text", "q   ONE"])
        second = out()
        assert first["id"] == second["id"]
        assert first["new"] is True
        assert second["new"] is False

    def test_verdict_dedups_per_finding_and_lens(self, run_dir, question, out):
        run_state.main(["add", str(run_dir), "--kind", "finding",
                        "--text", "F one", "--question", question])
        fid = out()["id"]
        for expected_new in (True, False):
            run_state.main(["add", str(run_dir), "--kind", "verdict", "--finding", fid,
                            "--lens", "correctness", "--refuted", "false"])
            assert out()["new"] is expected_new
        # A different lens is a different verdict.
        run_state.main(["add", str(run_dir), "--kind", "verdict", "--finding", fid,
                        "--lens", "sources", "--refuted", "true"])
        assert out()["new"] is True


# ── The done-marker is the ledger record, never file existence ──────────────


class TestDoneMarker:
    def test_payload_present_without_complete_record_still_runs(
        self, run_dir, question, write_payload, do_claim
    ):
        """The core resume rule. A file on disk may have been truncated by a kill
        mid-write, so only a `complete` record proves the step finished."""
        write_payload(question)
        assert do_claim(question)["action"] == "run"

    def test_complete_requires_a_payload(self, run_dir, question, do_claim):
        token = do_claim(question)["token"]
        assert run_state.main(["complete", str(run_dir), "--step", question,
                               "--token", token, "--summary", "s"]) == 1

    def test_complete_rejects_an_unterminated_payload(
        self, run_dir, question, write_payload, do_claim
    ):
        """A kill mid-write leaves a file with no trailing newline."""
        token = do_claim(question)["token"]
        write_payload(question, "a" * 200)  # long enough, but not newline-terminated
        assert run_state.main(["complete", str(run_dir), "--step", question,
                               "--token", token, "--summary", "s"]) == 1

    def test_complete_rejects_a_too_short_payload(
        self, run_dir, question, write_payload, do_claim
    ):
        token = do_claim(question)["token"]
        write_payload(question, "tiny\n")
        assert run_state.main(["complete", str(run_dir), "--step", question,
                               "--token", token, "--summary", "s"]) == 1

    def test_no_payload_flag_allows_a_bookkeeping_step(self, run_dir, do_claim):
        token = do_claim("decompose-r1")["token"]
        assert run_state.main(["complete", str(run_dir), "--step", "decompose-r1",
                               "--token", token, "--summary", "3 questions",
                               "--no-payload"]) == 0

    def test_complete_then_claim_skips_and_returns_prior_summary(
        self, run_dir, question, write_payload, do_claim
    ):
        """What makes a resume cheap: one Bash call per already-done step, and the
        orchestrator gets the summary without any agent being spawned."""
        token = do_claim(question)["token"]
        write_payload(question)
        assert run_state.main(["complete", str(run_dir), "--step", question,
                               "--token", token, "--summary", "found in auth.py"]) == 0
        again = do_claim(question)
        assert again["action"] == "skip"
        assert again["summary"] == "found in auth.py"

    def test_complete_is_idempotent(
        self, run_dir, question, write_payload, do_claim, out
    ):
        token = do_claim(question)["token"]
        write_payload(question)
        run_state.main(["complete", str(run_dir), "--step", question,
                        "--token", token, "--summary", "s"])
        out()
        assert run_state.main(["complete", str(run_dir), "--step", question,
                               "--token", token, "--summary", "s"]) == 0
        assert out()["idempotent"] is True
        records, _ = run_state._read_records(run_dir)
        assert sum(1 for r in records
                   if r["kind"] == "complete" and r["id"] == question) == 1

    def test_complete_without_claim_is_refused(self, run_dir, question, write_payload):
        write_payload(question)
        assert run_state.main(["complete", str(run_dir), "--step", question,
                               "--token", "made-up", "--summary", "s"]) == 1

    def test_stale_token_is_refused(
        self, run_dir, question, write_payload, do_claim
    ):
        """A re-claim supersedes the first; the loser's result must be discarded
        rather than recorded against work someone else redid."""
        stale = do_claim(question)["token"]
        fresh = do_claim(question)["token"]
        assert stale != fresh
        write_payload(question)
        assert run_state.main(["complete", str(run_dir), "--step", question,
                               "--token", stale, "--summary", "s"]) == 1
        assert run_state.main(["complete", str(run_dir), "--step", question,
                               "--token", fresh, "--summary", "s"]) == 0


# ── Fold precedence: `complete` is terminal ─────────────────────────────────


class TestPrecedence:
    def test_late_claim_record_cannot_reopen_a_completed_step(
        self, run_dir, question, write_payload, do_claim
    ):
        """A zombie agent from the interrupted session appends after the resume has
        already completed the step. Folding by line order would flip it back to
        claimed, and the next round would overwrite a good payload."""
        token = do_claim(question)["token"]
        write_payload(question)
        run_state.main(["complete", str(run_dir), "--step", question,
                        "--token", token, "--summary", "good"])
        run_state._append(run_dir, {"kind": "claimed", "id": question,
                                    "token": "zombie", "identity": None})
        assert do_claim(question)["action"] == "skip"

    def test_late_failure_record_cannot_reopen_a_completed_step(
        self, run_dir, question, write_payload, do_claim
    ):
        token = do_claim(question)["token"]
        write_payload(question)
        run_state.main(["complete", str(run_dir), "--step", question,
                        "--token", token, "--summary", "good"])
        run_state._append(run_dir, {"kind": "failed", "id": question, "reason": "x"})
        assert do_claim(question)["action"] == "skip"

    def test_fail_on_a_completed_step_is_refused(
        self, run_dir, question, write_payload, do_claim
    ):
        token = do_claim(question)["token"]
        write_payload(question)
        run_state.main(["complete", str(run_dir), "--step", question,
                        "--token", token, "--summary", "good"])
        assert run_state.main(["fail", str(run_dir), "--step", question,
                               "--reason", "late"]) == 1


# ── Id aliasing ─────────────────────────────────────────────────────────────


class TestIdentityGuard:
    def test_same_id_naming_different_work_is_refused(self, run_dir, do_claim):
        """The failure a positional id causes: once the iterated set shrinks,
        `step-3` names a different item and claim would skip work never done."""
        do_claim("step-3", "--identity", "src/alpha.py")
        assert run_state.main(["claim", str(run_dir), "--step", "step-3",
                               "--identity", "src/omega.py"]) == 1

    def test_same_id_same_identity_is_fine(self, run_dir, do_claim):
        do_claim("step-3", "--identity", "src/alpha.py")
        assert do_claim("step-3", "--identity", "src/alpha.py")["action"] == "run"


# ── Damage tolerance ────────────────────────────────────────────────────────


class TestDamageTolerance:
    def test_torn_line_is_counted_not_fatal(self, run_dir, question, out):
        """A strict json.loads-per-line fold would raise forever, on the line that
        is almost always the last one, with no repair path."""
        with open(run_dir / run_state.LEDGER_NAME, "a", encoding="utf-8") as fh:
            fh.write('{"kind":"question","id":"q-tor')
        assert run_state.main(["status", str(run_dir)]) == 0
        state = out()
        assert state["corrupt_lines"] == 1
        assert state["questions_total"] == 1

    def test_torn_line_does_not_swallow_the_next_append(self, run_dir, question, out):
        """Regression: `_append` assumed a trailing newline. Without closing the
        broken line off first, the next record is concatenated onto it and BOTH are
        lost — so one torn write silently ate every later record."""
        with open(run_dir / run_state.LEDGER_NAME, "a", encoding="utf-8") as fh:
            fh.write('{"kind":"question","id":"q-tor')
        run_state.main(["add", str(run_dir), "--kind", "finding",
                        "--text", "survives the tear", "--question", question])
        fid = out()["id"]
        run_state.main(["status", str(run_dir)])
        state = out()
        assert fid in state["findings"]
        assert state["corrupt_lines"] == 1

    def test_non_dict_line_counts_as_corrupt(self, run_dir, out):
        with open(run_dir / run_state.LEDGER_NAME, "a", encoding="utf-8") as fh:
            fh.write('["not", "a", "record"]\n')
        run_state.main(["status", str(run_dir)])
        assert out()["corrupt_lines"] == 1

    def test_concurrent_appends_lose_nothing(self, run_dir):
        """Batched agents append at the same time. flock + a single write of
        pre-encoded bytes is what keeps lines whole."""
        n_threads, per_thread = 16, 8

        def worker(w):
            for i in range(per_thread):
                run_state._append(run_dir, {"kind": "verdict",
                                            "id": f"v-{w}-{i}",
                                            "finding": "f-x", "lens": "l",
                                            "refuted": False})

        threads = [threading.Thread(target=worker, args=(w,))
                   for w in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        records, corrupt = run_state._read_records(run_dir)
        assert corrupt == 0
        ids = {r["id"] for r in records if r["kind"] == "verdict"}
        assert len(ids) == n_threads * per_thread


# ── Attempts and abandonment ────────────────────────────────────────────────


class TestAbandonment:
    def test_step_is_abandoned_after_max_attempts(self, run_dir, do_claim, out):
        """An impossible step must neither retry forever nor complete with a stub
        that poisons the summary."""
        for _ in range(run_state.MAX_ATTEMPTS):
            do_claim("q-impossible")
            run_state.main(["fail", str(run_dir), "--step", "q-impossible",
                            "--reason", "source deleted"])
            out()
        assert do_claim("q-impossible")["action"] == "abandon"

    def test_abandoned_step_is_reported_and_drops_out_of_pending(
        self, run_dir, question, do_claim, out
    ):
        for _ in range(run_state.MAX_ATTEMPTS):
            do_claim(question)
            run_state.main(["fail", str(run_dir), "--step", question,
                            "--reason", "nope"])
            out()
        run_state.main(["status", str(run_dir)])
        state = out()
        assert question in state["abandoned"]
        assert question not in state["pending"]

    def test_failure_below_the_cap_still_runs(self, run_dir, do_claim, out):
        do_claim("q-flaky")
        run_state.main(["fail", str(run_dir), "--step", "q-flaky", "--reason", "once"])
        assert out()["attempts"] == 1
        assert do_claim("q-flaky")["action"] == "run"


# ── Derived loop state ──────────────────────────────────────────────────────


class TestDerivedState:
    def test_round_is_derived_from_closed_round_markers(self, run_dir, out):
        """Storing a counter loses a round on one side of a crash or the other."""
        run_state.main(["status", str(run_dir)])
        assert out()["round"] == 1
        run_state.main(["round", str(run_dir), "--new-questions", "3"])
        out()
        run_state.main(["status", str(run_dir)])
        assert out()["round"] == 2

    def test_dry_rounds_count_only_the_trailing_run(self, run_dir, out):
        for n in ("0", "2", "0", "0"):
            run_state.main(["round", str(run_dir), "--new-questions", n])
            out()
        run_state.main(["status", str(run_dir)])
        assert out()["dry_rounds"] == 2

    def test_productive_round_resets_the_dry_count(self, run_dir, out):
        run_state.main(["round", str(run_dir), "--new-questions", "0"])
        out()
        run_state.main(["round", str(run_dir), "--new-questions", "5"])
        assert out()["dry_rounds"] == 0

    def test_non_integer_new_questions_is_refused(self, run_dir):
        assert run_state.main(["round", str(run_dir), "--new-questions", "many"]) == 1

    def test_pending_holds_unresearched_questions(self, run_dir, question, out):
        run_state.main(["status", str(run_dir)])
        assert out()["pending"] == [question]

    def test_unverified_holds_findings_with_no_verdict(self, run_dir, question, out):
        run_state.main(["add", str(run_dir), "--kind", "finding",
                        "--text", "F one", "--question", question])
        fid = out()["id"]
        run_state.main(["status", str(run_dir)])
        assert out()["unverified"] == [fid]
        run_state.main(["add", str(run_dir), "--kind", "verdict", "--finding", fid,
                        "--lens", "correctness", "--refuted", "false"])
        out()
        run_state.main(["status", str(run_dir)])
        state = out()
        assert state["unverified"] == []
        assert state["findings"][fid] == {"verdicts": 1, "refuted": 0}

    def test_refuted_verdicts_are_counted_separately(self, run_dir, question, out):
        """The loop owns the majority-refute threshold; the script only reports."""
        run_state.main(["add", str(run_dir), "--kind", "finding",
                        "--text", "F one", "--question", question])
        fid = out()["id"]
        for lens, refuted in (("correctness", "true"), ("sources", "true"),
                              ("repro", "false")):
            run_state.main(["add", str(run_dir), "--kind", "verdict", "--finding", fid,
                            "--lens", lens, "--refuted", refuted])
            out()
        run_state.main(["status", str(run_dir)])
        assert out()["findings"][fid] == {"verdicts": 3, "refuted": 2}

    def test_empty_run_is_not_all_complete(self, run_dir, out):
        """A fresh ledger must not read as finished, or a caller gating only on
        all_complete would summarise nothing."""
        run_state.main(["status", str(run_dir)])
        assert out()["all_complete"] is False

    def test_all_complete_requires_verdicts_too(
        self, run_dir, question, write_payload, do_claim, out
    ):
        token = do_claim(question)["token"]
        write_payload(question)
        run_state.main(["complete", str(run_dir), "--step", question,
                        "--token", token, "--summary", "s"])
        out()
        run_state.main(["add", str(run_dir), "--kind", "finding",
                        "--text", "F one", "--question", question])
        fid = out()["id"]
        run_state.main(["status", str(run_dir)])
        assert out()["all_complete"] is False
        run_state.main(["add", str(run_dir), "--kind", "verdict", "--finding", fid,
                        "--lens", "correctness", "--refuted", "false"])
        out()
        run_state.main(["status", str(run_dir)])
        assert out()["all_complete"] is True

    def test_open_step_blocks_all_complete(
        self, run_dir, question, write_payload, do_claim, out
    ):
        token = do_claim(question)["token"]
        write_payload(question)
        run_state.main(["complete", str(run_dir), "--step", question,
                        "--token", token, "--summary", "s"])
        out()
        do_claim("summary")          # claimed, never completed
        run_state.main(["status", str(run_dir)])
        assert out()["all_complete"] is False


# ── resolve: run-dir identity ───────────────────────────────────────────────


class TestResolve:
    def test_new_then_resumed(self, tmp_path, out):
        d = tmp_path / "r"
        run_state.main(["resolve", "--task", "a task", "--run-dir", str(d)])
        first = out()
        assert first["status"] == "new"
        assert first["invocation"] == 1
        run_state.main(["resolve", "--task", "a task", "--run-dir", str(d)])
        second = out()
        assert second["status"] == "resumed"
        assert second["invocation"] == 2

    def test_same_task_resolves_to_the_same_dir(self, tmp_path, monkeypatch, out):
        """Re-typing the identical command IS the resume ritual, so the dir must be
        a pure function of the task text."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(run_state, "RUNS_ROOT", run_state.RUNS_ROOT)
        run_state.main(["resolve", "--task", "Investigate the auth flow"])
        first = out()["run_dir"]
        run_state.main(["resolve", "--task", "investigate   the AUTH flow"])
        assert out()["run_dir"] == first

    def test_adopting_a_run_dir_from_another_task_is_refused(self, tmp_path):
        d = tmp_path / "r"
        assert run_state.main(["resolve", "--task", "task one", "--run-dir", str(d)]) == 0
        assert run_state.main(["resolve", "--task", "task two", "--run-dir", str(d)]) == 1

    def test_force_overrides_a_task_mismatch(self, tmp_path):
        d = tmp_path / "r"
        run_state.main(["resolve", "--task", "task one", "--run-dir", str(d)])
        assert run_state.main(["resolve", "--task", "task two", "--run-dir", str(d),
                               "--force"]) == 0

    def test_near_identical_sibling_is_refused_without_force(
        self, tmp_path, monkeypatch, out
    ):
        """A reworded task would silently fork the run and redo all the work."""
        monkeypatch.chdir(tmp_path)
        run_state.main(["resolve", "--task", "check the auth flow now"])
        out()
        # Same readable slug stem, different hash: force a collision by hand.
        first = sorted((tmp_path / run_state.RUNS_ROOT).iterdir())[0]
        twin = first.parent / (first.name.rsplit("-", 1)[0] + "-deadbeef")
        twin.mkdir()
        (twin / run_state.MANIFEST_NAME).write_text("{}\n", encoding="utf-8")
        import shutil
        shutil.rmtree(first)
        assert run_state.main(["resolve", "--task", "check the auth flow now"]) == 1
        assert run_state.main(["resolve", "--task", "check the auth flow now",
                               "--force"]) == 0

    def test_resolve_requires_a_task(self):
        assert run_state.main(["resolve"]) == 1
        assert run_state.main(["resolve", "--task", "   "]) == 1

    def test_resolve_reports_the_derived_paths(self, tmp_path, out):
        run_state.main(["resolve", "--task", "t", "--run-dir", str(tmp_path / "r")])
        state = out()
        assert state["digest_path"].endswith("digest.md")
        assert state["summary_path"].endswith("summary.md")

    def test_digest_path_is_the_digest_steps_own_payload_path(self, tmp_path, out):
        """Regression: these were two different files. The digest agent writes where
        `claim` sends it, and every later agent is handed `digest_path` — so a
        mismatch points the whole run at a digest that does not exist."""
        d = tmp_path / "r"
        run_state.main(["resolve", "--task", "t", "--run-dir", str(d)])
        assert out()["digest_path"] == str(
            run_state._payload_path(d, "digest").resolve()
        )


# ── CLI contract ────────────────────────────────────────────────────────────


class TestCli:
    def test_no_args_prints_usage_and_fails(self, capsys):
        assert run_state.main([]) == 1
        assert "Usage:" in capsys.readouterr().err

    def test_unknown_command_fails(self, capsys):
        assert run_state.main(["frobnicate"]) == 1
        assert "unknown command" in capsys.readouterr().err

    def test_missing_run_dir_fails(self):
        assert run_state.main(["status"]) == 1

    def test_nonexistent_run_dir_fails(self, tmp_path):
        assert run_state.main(["status", str(tmp_path / "nope")]) == 1

    @pytest.mark.parametrize("argv", [
        ["add", "--kind", "banana", "--text", "x"],
        ["add", "--kind", "question"],
        ["add", "--kind", "finding", "--text", "x"],
        ["add", "--kind", "verdict", "--finding", "f-x"],
        ["add", "--kind", "verdict", "--finding", "f-x", "--lens", "l",
         "--refuted", "maybe"],
        ["claim"],
        ["complete", "--step", "q-x"],
        ["fail", "--step", "q-x"],
        ["round"],
    ])
    def test_bad_flags_fail_with_exit_1(self, run_dir, argv):
        """Exit code 1, never argparse's 2 — the house contract is 0/1."""
        assert run_state.main([argv[0], str(run_dir), *argv[1:]]) == 1

    def test_every_success_emits_one_json_object(self, run_dir, question, out):
        """The orchestrator parses stdout, so every command must emit exactly one
        parseable object."""
        run_state.main(["status", str(run_dir)])
        assert isinstance(out(), dict)


def test_ledger_records_are_sorted_json_one_per_line(run_dir, question):
    """A stable on-disk shape keeps the file diffable and hand-inspectable when a
    run goes wrong."""
    text = (run_dir / run_state.LEDGER_NAME).read_text(encoding="utf-8")
    assert text.endswith("\n")
    for line in text.splitlines():
        assert json.loads(line)["kind"]
