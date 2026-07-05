import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from aider.providers.base import BaseProvider, ProviderEvent

logger = logging.getLogger(__name__)

_BENIGN_STDERR = "failed to record rollout items"


class CodexProvider(BaseProvider):
    def __init__(
        self,
        sandbox: str = "workspace-write",
        *,
        approval_policy: str | None = None,
        cwd: str | Path | None = None,
        ephemeral: bool = False,
        dangerously_bypass_approvals_and_sandbox: bool = False,
    ):
        self._thread_id: str | None = None
        self._sandbox = sandbox
        self._approval_policy = approval_policy
        self._cwd = Path(cwd) if cwd else None
        self._ephemeral = ephemeral
        self._dangerously_bypass_approvals_and_sandbox = dangerously_bypass_approvals_and_sandbox

    async def run_turn(self, prompt: str) -> AsyncIterator[ProviderEvent]:
        prefix = ["codex"]
        if self._dangerously_bypass_approvals_and_sandbox:
            prefix.append("--dangerously-bypass-approvals-and-sandbox")
        elif self._approval_policy:
            prefix.extend(["--ask-for-approval", self._approval_policy])

        if self._thread_id is None:
            cmd = [*prefix, "exec", "--json"]
            if not self._dangerously_bypass_approvals_and_sandbox:
                cmd.extend(["--sandbox", self._sandbox])
            if self._cwd:
                cmd.extend(["--cd", str(self._cwd)])
            if self._ephemeral:
                cmd.append("--ephemeral")
            cmd.append(prompt)
        else:
            cmd = [
                *prefix,
                "exec",
                "resume",
                self._thread_id,
                "--json",
            ]
            if not self._dangerously_bypass_approvals_and_sandbox:
                cmd.extend(["--sandbox", self._sandbox])
            if self._cwd:
                cmd.extend(["--cd", str(self._cwd)])
            if self._ephemeral:
                cmd.append("--ephemeral")
            cmd.append(prompt)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._cwd) if self._cwd else None,
        )

        async for raw in proc.stdout:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("codex non-json stdout: %s", line)
                continue

            match event.get("type"):
                case "thread.started":
                    self._thread_id = event["thread_id"]
                case "item.completed":
                    item = event.get("item", {})
                    if item.get("type") == "agent_message":
                        yield ProviderEvent(type="text", content=item.get("text", ""))
                case "turn.failed":
                    err = event.get("error", {})
                    if err.get("code") == "rate_limit_exceeded":
                        yield ProviderEvent(type="exhausted")
                    else:
                        yield ProviderEvent(type="error", content=str(err))
                case "turn.completed":
                    yield ProviderEvent(type="done", session_id=self._thread_id)
                case _:
                    logger.debug("codex unhandled event: %s", event.get("type"))

        stderr = (await proc.stderr.read()).decode().strip()
        for line in stderr.splitlines():
            if _BENIGN_STDERR in line:
                logger.debug("codex stderr (benign): %s", line)
            elif line:
                logger.warning("codex stderr: %s", line)

        await proc.wait()

    @property
    def current_session_id(self) -> str | None:
        return self._thread_id
