"""
Relay loop — routes a coding task through providers, switching on exhaustion
with MTARP session continuation (KB-2026-021/026/030).

Entry point for the installed `aider-relay` CLI command. Also importable as
a library: `from aider.relay.loop import relay`.

Usage (installed):
    aider-relay "add OAuth login"
    aider-relay --primary codex --fallback claude "refactor foo.py"
    aider-relay --autonomous --max-turns 20 --task-file TASK.md

Usage (source):
    python -m aider.relay.loop "add OAuth login"
    uv run aider-relay "add OAuth login"
"""

import argparse
import asyncio
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aider.openspec import OpenSpecAdapter
from aider.planning import PlanningSnapshot
from aider.providers.base import BaseProvider
from aider.providers.claude_code import ClaudeCodeProvider
from aider.providers.codex import CodexProvider
from aider.relay.campaign import CampaignEvent, CampaignState
from aider.relay.campaign_runner import (
    ScriptedCampaignWorker,
    parse_duration_seconds,
    run_autonomous_campaign,
)
from aider.relay.codex_worker import CodexCliCampaignWorker
from aider.relay.session import MTARPSession
from aider.speckit import SpecKitAdapter

_MAX_DIFF_CHARS = 8_000
_CONTINUATION_PROMPT = (
    "Continue working on the task. Check git log to see what has been committed. "
    "Keep going until the task is complete or you cannot proceed further."
)
_MERGE_REVIEW_PROMPT = (
    "Before this session ends, perform a self-review of your changes against these criteria:\n\n"
    "1. **Process artifacts** — Have you committed any relay-internal files (TASK.md, "
    "session.json, *.patch)? If so, remove them from the branch.\n"
    "2. **Doc/runtime alignment** — Every path, command, or output path you documented — "
    "does it match what the code actually produces? Run a check if needed.\n"
    "3. **Version consistency** — Do version strings in docs, configs, and changelogs agree?\n"
    "4. **Proof encoding** — Every proof claim ('test X passes') — is it encoded as a "
    "repo-owned automation step (CI task, test, Makefile target)?\n"
    "5. **Handoff envelope** — Ensure .aider-relay/session.json has non-empty "
    "files_in_scope and session_summary.\n\n"
    "Fix any issues found. If you cannot fix something, state why in a comment or TODO."
)


def make_provider(name: str) -> BaseProvider:
    if name == "codex":
        return CodexProvider()
    if name == "claude":
        return ClaudeCodeProvider()
    raise ValueError(f"Unknown provider: {name}")


def _try_make_git_repo():
    """Create a GitRepo for richer git operations. Returns None if unavailable."""
    try:
        from aider.io import InputOutput
        from aider.repo import GitRepo

        _io = InputOutput(pretty=False, yes=True)
        return GitRepo(io=_io, fnames=[], git_dname=str(Path.cwd()))
    except Exception:
        return None


def _files_changed(session: MTARPSession, git_repo) -> list[str]:
    """Return files changed between session start and current HEAD via git diff --name-only."""
    if not (git_repo and session.git_diff_since and session.git_head):
        return []
    try:
        raw = git_repo.repo.git.diff("--name-only", session.git_diff_since, session.git_head)
        return [f for f in raw.splitlines() if f.strip()]
    except Exception:
        return []


def _generate_summary(task: str, diff: str, model_name: str = "claude-haiku-4-5-20251001") -> str:
    """Generate a 2-3 sentence summary of what was accomplished. Returns '' on any failure."""
    if not diff.strip():
        return ""
    try:
        import litellm

        prompt = (
            f"Task: {task}\n\n"
            f"Git diff:\n{diff[:6000]}\n\n"
            "Summarise in 2-3 sentences what was accomplished. "
            "Be specific: mention file names and key changes."
        )
        response = litellm.completion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return ""


def _build_repomap_context(session: MTARPSession, git_repo) -> str:
    """Return a RepoMap string for files changed during the session, or '' on any failure."""
    try:
        from aider.io import InputOutput
        from aider.models import Model
        from aider.repomap import RepoMap

        changed = session.files_in_scope or _files_changed(session, git_repo)
        all_files = list(git_repo.get_tracked_files())
        if not all_files:
            return ""

        io = InputOutput(pretty=False, yes=True)
        model = Model("claude-haiku-4-5-20251001")
        repo_map = RepoMap(map_tokens=2048, root=str(Path.cwd()), main_model=model, io=io)
        return repo_map.get_repo_map(chat_files=changed, other_files=all_files) or ""
    except Exception:
        return ""


def git_context(git_repo=None) -> str:
    if git_repo is not None:
        try:
            log = git_repo.repo.git.log("--oneline", "-10") or "(no git history)"
            diff = git_repo.get_diffs() or "(none)"
            if len(diff) > _MAX_DIFF_CHARS:
                diff = (
                    diff[:_MAX_DIFF_CHARS]
                    + f"\n... (truncated — {len(diff) - _MAX_DIFF_CHARS} chars omitted)"
                )
            return f"Recent git history:\n{log}\n\nCurrent uncommitted changes:\n{diff}"
        except Exception:
            pass  # fall through to subprocess

    def run(cmd):
        try:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        except (subprocess.CalledProcessError, OSError):
            return None

    log = run(["git", "log", "--oneline", "-10"]) or "(no git history)"
    diff = run(["git", "diff", "HEAD"]) or "(none)"
    if len(diff) > _MAX_DIFF_CHARS:
        diff = (
            diff[:_MAX_DIFF_CHARS]
            + f"\n... (truncated — {len(diff) - _MAX_DIFF_CHARS} chars omitted)"
        )
    return f"Recent git history:\n{log}\n\nCurrent uncommitted changes:\n{diff}"


def _planning_context_section(spec_context: dict) -> str:
    """Render compact, framework-neutral planning context for prompts."""
    if not spec_context:
        return ""

    lines = ["## Planning Context"]

    feature = spec_context.get("feature", {})
    feature_bits = [bit for bit in [spec_context.get("change_id"), feature.get("title")] if bit]
    if feature_bits:
        lines.append(f"Feature: {' - '.join(feature_bits)}")

    summary = spec_context.get("capability_summary")
    if summary:
        lines.extend(["", summary])

    unresolved = spec_context.get("execution_context_pack", {}).get("unresolved_tasks", [])
    if unresolved:
        lines.extend(["", "Unresolved tasks:"])
        for item in unresolved[:5]:
            item_id = item.get("id", "TASK")
            title = item.get("title", "").strip()
            section = item.get("section", "").strip()
            if section:
                lines.append(f"- {item_id} ({section}): {title}")
            else:
                lines.append(f"- {item_id}: {title}")
        if len(unresolved) > 5:
            lines.append(f"- ... {len(unresolved) - 5} more")

    pending_verification = [
        item
        for item in spec_context.get("verification_refs", [])
        if item.get("status") != "completed"
    ]
    if pending_verification:
        lines.extend(["", "Verification obligations:"])
        for item in pending_verification[:5]:
            lines.append(f"- {item.get('id', 'CHECK')}: {item.get('text', '').strip()}")
        if len(pending_verification) > 5:
            lines.append(f"- ... {len(pending_verification) - 5} more")

    artifact_refs = spec_context.get("artifact_refs", [])
    if artifact_refs:
        lines.extend(["", "Artifact refs:"])
        for item in artifact_refs[:4]:
            sha = item.get("sha256", "")[:8]
            suffix = f" [{sha}]" if sha else ""
            lines.append(f"- {item.get('path', '')}{suffix}")
        if len(artifact_refs) > 4:
            lines.append(f"- ... {len(artifact_refs) - 4} more")

    return "\n".join(lines)


def _initial_prompt(task: str, spec_context: dict | None = None) -> str:
    """Build the first provider prompt, adding planning context when supplied."""
    if not spec_context:
        return task

    return (
        "You are starting a coding task in this repository.\n\n"
        f"## Task\n{task}\n\n"
        f"{_planning_context_section(spec_context)}\n\n"
        "Treat the planning context as intent. Verify it against the repository state before"
        " editing."
    )


def handoff_prompt(task: str, session: MTARPSession | None = None, git_repo=None) -> str:
    session_diff = None
    if git_repo and session and session.git_diff_since and session.git_head:
        try:
            session_diff = git_repo.diff_commits(False, session.git_diff_since, session.git_head)
            if len(session_diff) > _MAX_DIFF_CHARS:
                session_diff = (
                    session_diff[:_MAX_DIFF_CHARS]
                    + f"\n... (truncated — {len(session_diff) - _MAX_DIFF_CHARS} chars omitted)"
                )
        except Exception:
            session_diff = None

    if session_diff is not None:
        since = session.git_diff_since[:7]
        head = session.git_head[:7]
        context_section = (
            f"## What was done this session (git diff {since}..{head})\n"
            f"{session_diff or '(no changes committed)'}"
        )
    else:
        context_section = f"## What has been done (from git)\n{git_context(git_repo)}"

    repomap_section = ""
    if git_repo and session:
        repomap = _build_repomap_context(session, git_repo)
        if repomap:
            repomap_section = f"\n\n## Repository map (files touched this session)\n{repomap}"

    planning_section = ""
    if session and session.spec_context:
        planning_section = f"\n\n{_planning_context_section(session.spec_context)}"

    base = (
        "You are continuing a coding task in this repository. "
        "A previous AI assistant was working on this and hit its usage limit.\n\n"
        f"## Task\n{task}\n"
        f"{planning_section}"
        f"{repomap_section}\n\n"
        f"{context_section}\n\n"
        "Please continue from where the previous assistant left off."
    )
    if session is not None:
        base += (
            "\n\n## MTARP Session Envelope\n"
            "A session record has been written to .aider-relay/session.json capturing the task,\n"
            "git state at handoff, and which provider was working. You can inspect it with:\n"
            "  cat .aider-relay/session.json"
        )
    return base


def _check_interrupt(session_dir: str) -> bool:
    """Return True (and remove sentinel) if .aider-relay/interrupt exists."""
    sentinel = Path(session_dir) / "interrupt"
    if sentinel.exists():
        sentinel.unlink()
        return True
    return False


async def _run_turn_events(provider: BaseProvider, prompt: str, label: str) -> str | None:
    async for event in provider.run_turn(prompt):
        if event.type == "text":
            print(event.content, end="", flush=True)
        elif event.type == "exhausted":
            suffix = f" (resets at {event.reset_at})" if event.reset_at else ""
            print(f"\n\n[{label}] Usage window exhausted{suffix}.")
            return "exhausted"
        elif event.type == "error":
            print(f"\n[{label}] Error: {event.content}")
        elif event.type == "done":
            print()
    return None


async def _heartbeat(label: str, interval: float = 15.0) -> None:
    """Print elapsed time every *interval* seconds while a turn is in flight."""
    elapsed = 0.0
    while True:
        await asyncio.sleep(interval)
        elapsed += interval
        print(f"\n[{label}] ... {int(elapsed)}s elapsed", end="", flush=True)


async def run_turn(
    provider: BaseProvider, prompt: str, label: str, turn_timeout: int = 0
) -> str | None:
    """Run one provider turn. Returns 'exhausted'/'timeout' if limit hit, None on success."""
    print(f"\n[{label}] ", end="", flush=True)
    coro = _run_turn_events(provider, prompt, label)
    heartbeat_task = asyncio.create_task(_heartbeat(label))
    try:
        if turn_timeout > 0:
            try:
                return await asyncio.wait_for(coro, timeout=turn_timeout)
            except asyncio.TimeoutError:
                print(f"\n[{label}] Turn timed out after {turn_timeout}s.")
                return "timeout"
        return await coro
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


async def relay(
    task: str,
    primary: str,
    fallback: str,
    sim_exhaust_after: int = 0,
    session_dir: str = ".aider-relay",
    autonomous: bool = False,
    max_turns: int = 0,
    turn_timeout: int = 0,
    merge_review: bool = False,
    snapshot: PlanningSnapshot | None = None,
) -> None:
    git_repo = _try_make_git_repo()
    providers = {primary: make_provider(primary), fallback: make_provider(fallback)}
    active = primary
    spec_context = snapshot.to_spec_context() if snapshot else {}
    prompt = _initial_prompt(task, spec_context=spec_context)
    exhausted: set[str] = set()
    turn_counts: dict[str, int] = {primary: 0, fallback: 0}
    total_turns = 0

    session = MTARPSession.create(task=task, primary_provider=primary, spec_context=spec_context)
    provider_started_at = datetime.now(tz=timezone.utc).isoformat()

    while True:
        if _check_interrupt(session_dir):
            print("\n[RELAY] Interrupt sentinel detected. Stopping after current turn boundary.")
            break

        label = active.upper()
        result = await run_turn(providers[active], prompt, label, turn_timeout=turn_timeout)

        if result is None:
            turn_counts[active] += 1
            total_turns += 1

        if result is None and sim_exhaust_after > 0 and turn_counts[active] >= sim_exhaust_after:
            other = fallback if active == primary else primary
            print(
                f"\n[RELAY] (sim) Simulating exhaustion after {sim_exhaust_after} turn(s) on"
                f" {label}. Switching to {other.upper()}..."
            )
            result = "exhausted"

        if result in ("exhausted", "timeout"):
            exhausted.add(active)
            end_reason = result

            ended_at = datetime.now(tz=timezone.utc).isoformat()
            if git_repo:
                head = git_repo.get_head_commit_sha()
                if head:
                    session.git_head = head
            else:
                try:
                    session.git_head = subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
                    ).strip()
                except (subprocess.CalledProcessError, OSError):
                    pass

            session.files_in_scope = _files_changed(session, git_repo)
            diff_for_summary = ""
            if git_repo and session.git_diff_since and session.git_head:
                try:
                    diff_for_summary = (
                        git_repo.diff_commits(False, session.git_diff_since, session.git_head) or ""
                    )
                except Exception:
                    pass
            session.session_summary = _generate_summary(task, diff_for_summary)

            for warning in session.validate_handoff():
                print(f"[RELAY] Warning: {warning}")

            session.add_provider_run(
                provider=active,
                tier=providers[active].tier,
                session_id=providers[active].current_session_id or "",
                started_at=provider_started_at,
                ended_at=ended_at,
                end_reason=end_reason,
            )
            session.outgoing_provider = active
            session.handoff_reason = end_reason
            session.handoff_at = ended_at
            session_path = Path(session_dir) / "session.json"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session.write(session_path)
            provider_started_at = datetime.now(tz=timezone.utc).isoformat()

            other = fallback if active == primary else primary
            if other in exhausted:
                print("\n[RELAY] Both providers exhausted. Stopping.")
                break
            print(f"[RELAY] Switching to {other.upper()}...")
            active = other
            prompt = handoff_prompt(task, session=session, git_repo=git_repo)

        else:
            if max_turns > 0 and total_turns >= max_turns:
                print(f"\n[RELAY] Reached max turns ({max_turns}). Stopping.")
                if merge_review:
                    print(f"[RELAY] Running merge-readiness review on {label}...")
                    await run_turn(
                        providers[active], _MERGE_REVIEW_PROMPT, label, turn_timeout=turn_timeout
                    )
                break

            if autonomous:
                prompt = _CONTINUATION_PROMPT
            else:
                try:
                    next_input = input("\nYou: ").strip()
                except EOFError:
                    if merge_review:
                        print(f"[RELAY] Running merge-readiness review on {label}...")
                        await run_turn(
                            providers[active],
                            _MERGE_REVIEW_PROMPT,
                            label,
                            turn_timeout=turn_timeout,
                        )
                    break
                if not next_input:
                    if merge_review:
                        print(f"[RELAY] Running merge-readiness review on {label}...")
                        await run_turn(
                            providers[active],
                            _MERGE_REVIEW_PROMPT,
                            label,
                            turn_timeout=turn_timeout,
                        )
                    break
                prompt = next_input


def _load_snapshot(
    *,
    spec_feature: str | None = None,
    openspec_change: str | None = None,
    spec_snapshot_path: str | None = None,
) -> PlanningSnapshot | None:
    """Load a planning snapshot from either a repo feature or a JSON file."""
    if not spec_feature and not openspec_change and not spec_snapshot_path:
        return None
    if spec_snapshot_path:
        return PlanningSnapshot.read_json(spec_snapshot_path)
    if openspec_change:
        return OpenSpecAdapter(str(Path.cwd())).build_snapshot(change=openspec_change)
    return SpecKitAdapter(str(Path.cwd())).build_snapshot(feature=spec_feature)


def _campaign_worker_from_args(args):
    if args.worker == "scripted":
        return ScriptedCampaignWorker()
    if args.worker == "codex":
        return CodexCliCampaignWorker(
            cwd=args.cwd,
            sandbox=args.codex_sandbox,
            approval_policy=args.codex_approval_policy,
            ephemeral=not args.codex_persist_session,
            turn_timeout=args.turn_timeout,
            dangerously_bypass_approvals_and_sandbox=(
                args.codex_dangerously_bypass_approvals_and_sandbox
            ),
        )
    raise ValueError(f"Unknown campaign worker: {args.worker}")


def _print_campaign_summary(state: CampaignState) -> None:
    counts: dict[str, int] = {}
    for queue in state.queues:
        counts[queue.state.value] = counts.get(queue.state.value, 0) + 1

    print(f"[CAMPAIGN] id: {state.campaign_id}")
    print(f"[CAMPAIGN] active: {state.active_queue_id or '(none)'}")
    print(
        "[CAMPAIGN] queues: "
        + ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    )
    print(f"[CAMPAIGN] worker_turns: {len(state.worker_turns)}")
    print(f"[CAMPAIGN] validation_receipts: {len(state.validation_receipts)}")
    if state.stop_audit:
        print(f"[CAMPAIGN] stopped: {state.stop_audit.reason}")
    else:
        print("[CAMPAIGN] stopped: no")


def _print_campaign_event(event: CampaignEvent) -> None:
    bits = [event.at, event.type]
    if event.queue_id:
        bits.append(f"queue={event.queue_id}")
    if event.provider:
        bits.append(f"provider={event.provider}")
    print("[CAMPAIGN] " + " ".join(bits) + f" | {event.message}", flush=True)


def _watch_campaign_status(state_path: Path, interval: float) -> None:
    last_seen = 0
    try:
        while True:
            if state_path.exists():
                state = CampaignState.read(state_path)
                for event in state.events[last_seen:]:
                    _print_campaign_event(event)
                last_seen = len(state.events)
                _print_campaign_summary(state)
                if state.stopped:
                    return
            else:
                print(f"[CAMPAIGN] waiting for state file: {state_path}", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("[CAMPAIGN] watch interrupted")


def campaign_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="aider-relay campaign control plane")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_run_args(run_parser):
        run_parser.add_argument(
            "--state",
            default=".aider-relay/campaign.json",
            help="Campaign state path",
        )
        run_parser.add_argument(
            "--event-log",
            default=".aider-relay/campaign.events.jsonl",
            help="Append-only campaign event JSONL path",
        )
        run_parser.add_argument(
            "--worker",
            choices=["codex", "scripted"],
            default="codex",
            help="Campaign worker implementation",
        )
        run_parser.add_argument(
            "--cwd",
            default=".",
            help="Working directory for provider and validation commands",
        )
        run_parser.add_argument(
            "--max-queues",
            type=int,
            default=0,
            help="Stop after N queues this invocation (0=unlimited)",
        )
        run_parser.add_argument(
            "--max-runtime",
            default="0",
            help="Stop after duration, e.g. 12h, 90m, 86400s (0=unlimited)",
        )
        run_parser.add_argument(
            "--heartbeat",
            default="5m",
            help="Emit heartbeat events every duration (0=disabled)",
        )
        run_parser.add_argument(
            "--interrupt-file",
            default=".aider-relay/interrupt",
            help="Stop gracefully before the next queue when this file exists",
        )
        run_parser.add_argument(
            "--pause-file",
            default=".aider-relay/pause",
            help="Pause before the next queue while this file exists",
        )
        run_parser.add_argument(
            "--pause-poll-interval",
            type=float,
            default=5.0,
            help="Seconds between pause/interrupt checks while paused",
        )
        run_parser.add_argument(
            "--turn-timeout",
            type=int,
            default=3600,
            help="Provider turn timeout in seconds",
        )
        run_parser.add_argument(
            "--validation-timeout",
            type=int,
            default=1200,
            help="Validation command timeout in seconds",
        )
        run_parser.add_argument(
            "--require-clean-worktree",
            action="store_true",
            help="Refuse to start unless git status --porcelain is empty",
        )
        run_parser.add_argument(
            "--checkpoint-command",
            default="",
            help=(
                "Optional shell command after each queue. "
                "Use {queue_id} placeholder, e.g. "
                "'git add -A && git commit -m \"campaign checkpoint: {queue_id}\"'"
            ),
        )
        run_parser.add_argument(
            "--codex-sandbox",
            choices=["read-only", "workspace-write", "danger-full-access"],
            default="workspace-write",
            help="Codex sandbox mode when not using dangerous bypass",
        )
        run_parser.add_argument(
            "--codex-approval-policy",
            choices=["untrusted", "on-request", "on-failure", "never"],
            default="never",
            help="Codex approval policy when not using dangerous bypass",
        )
        run_parser.add_argument(
            "--codex-persist-session",
            action="store_true",
            help="Allow Codex to persist its own session files",
        )
        run_parser.add_argument(
            "--codex-dangerously-bypass-approvals-and-sandbox",
            action="store_true",
            help=(
                "Pass Codex --dangerously-bypass-approvals-and-sandbox. "
                "Only use inside an externally isolated environment."
            ),
        )

    run_parser = subparsers.add_parser("run", help="Start a campaign from a manifest")
    run_parser.add_argument("--manifest", required=True, help="Campaign manifest YAML/JSON")
    add_common_run_args(run_parser)

    resume_parser = subparsers.add_parser("resume", help="Resume an existing campaign state")
    add_common_run_args(resume_parser)

    status_parser = subparsers.add_parser("status", help="Print campaign state summary")
    status_parser.add_argument(
        "--state",
        default=".aider-relay/campaign.json",
        help="Campaign state path",
    )
    status_parser.add_argument(
        "--watch",
        action="store_true",
        help="Poll campaign state and print new events until the campaign stops",
    )
    status_parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Watch polling interval in seconds",
    )

    args = parser.parse_args(argv)

    if args.command == "status":
        state_path = Path(args.state)
        if args.watch:
            _watch_campaign_status(state_path, args.interval)
            return
        if not state_path.exists():
            print(f"Campaign state not found: {state_path}")
            sys.exit(1)
        _print_campaign_summary(CampaignState.read(state_path))
        return

    if args.codex_dangerously_bypass_approvals_and_sandbox:
        print(
            "[CAMPAIGN] WARNING: Codex dangerous bypass is enabled. "
            "Use only in an externally isolated environment."
        )

    worker = _campaign_worker_from_args(args)
    state = run_autonomous_campaign(
        manifest_path=args.manifest if args.command == "run" else None,
        state_path=args.state,
        worker=worker,
        max_queues=args.max_queues,
        validation_cwd=args.cwd,
        validation_timeout=args.validation_timeout,
        event_sink=_print_campaign_event,
        event_log_path=args.event_log,
        interrupt_path=args.interrupt_file,
        pause_path=args.pause_file,
        pause_poll_interval=args.pause_poll_interval,
        max_runtime_seconds=parse_duration_seconds(args.max_runtime),
        heartbeat_interval=parse_duration_seconds(args.heartbeat),
        require_clean_worktree=args.require_clean_worktree,
        checkpoint_command=args.checkpoint_command,
    )
    _print_campaign_summary(state)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "campaign":
        campaign_main(sys.argv[2:])
        return

    parser = argparse.ArgumentParser(description="aider-relay: multi-provider relay loop")
    parser.add_argument("task", nargs="?", help="Initial task (prompted if omitted)")
    parser.add_argument("--primary", default="claude", choices=["claude", "codex"])
    parser.add_argument("--fallback", default="codex", choices=["claude", "codex"])
    parser.add_argument(
        "--sim-exhaust-after",
        type=int,
        default=0,
        metavar="N",
        help="Simulate exhaustion after N turns on each provider (0=disabled)",
    )
    parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Run autonomously without waiting for user input between turns",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=0,
        metavar="N",
        help="Stop after N total turns across all providers (0=unlimited)",
    )
    parser.add_argument(
        "--task-file",
        metavar="PATH",
        help="Read initial task from a file (e.g. TASK.md)",
    )
    spec_group = parser.add_mutually_exclusive_group()
    spec_group.add_argument(
        "--spec",
        metavar="FEATURE",
        help="Load planning context from a checked-in SpecKit feature directory",
    )
    spec_group.add_argument(
        "--openspec-change",
        metavar="CHANGE",
        help="Load planning context from a checked-in OpenSpec change directory",
    )
    spec_group.add_argument(
        "--spec-snapshot",
        metavar="PATH",
        help="Load planning context from a deterministic snapshot JSON file",
    )
    parser.add_argument(
        "--turn-timeout",
        type=int,
        default=0,
        metavar="SECONDS",
        help="Kill a provider turn after N seconds and treat as exhausted (0=disabled)",
    )
    parser.add_argument(
        "--merge-review",
        action="store_true",
        help="Send a merge-readiness self-review prompt to the active provider before stopping",
    )
    parser.add_argument(
        "--exec-prefix",
        metavar="CMD",
        default="",
        help=(
            "Container exec gateway (e.g. 'podman exec mycontainer'). "
            "Prepended to the task as a system instruction so the agent knows "
            "all build/test/git-write commands must route through the container."
        ),
    )
    args = parser.parse_args()

    if args.primary == args.fallback:
        print("Primary and fallback must be different providers.")
        sys.exit(1)

    if args.task_file:
        task_path = Path(args.task_file)
        if not task_path.exists():
            print(f"Task file not found: {args.task_file}")
            sys.exit(1)
        task = task_path.read_text().strip()
    else:
        task = args.task or input("Task: ").strip()

    if not task:
        print("No task provided.")
        sys.exit(1)
    try:
        snapshot = _load_snapshot(
            spec_feature=args.spec,
            openspec_change=args.openspec_change,
            spec_snapshot_path=args.spec_snapshot,
        )
    except Exception as err:
        print(f"Unable to load planning context: {err}")
        sys.exit(1)

    if args.exec_prefix:
        gateway_instruction = (
            "SYSTEM — EXECUTION GATEWAY\n"
            "All build, test, and git-write commands MUST run inside the container "
            f"via:\n\n  {args.exec_prefix} <command>\n\n"
            f"Example: `{args.exec_prefix} ./gradlew build`\n"
            "Direct execution of these commands on the host is blocked by the "
            "permission system. File reads/writes and git reads (status/log/diff) "
            "may be run on the host directly.\n\n---\n\n"
        )
        task = gateway_instruction + task

    print(f"[RELAY] Primary: {args.primary.upper()} | Fallback: {args.fallback.upper()}")
    if args.autonomous:
        limit = f" (max {args.max_turns} turns)" if args.max_turns else ""
        print(f"[RELAY] Mode: autonomous{limit}")
    print(f"[RELAY] Task: {task[:120]}{'...' if len(task) > 120 else ''}")

    asyncio.run(
        relay(
            task,
            args.primary,
            args.fallback,
            args.sim_exhaust_after,
            session_dir=".aider-relay",
            autonomous=args.autonomous,
            max_turns=args.max_turns,
            turn_timeout=args.turn_timeout,
            merge_review=args.merge_review,
            snapshot=snapshot,
        )
    )


if __name__ == "__main__":
    main()
