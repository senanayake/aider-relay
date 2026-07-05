"""
Codex CLI worker adapter for relay campaigns.

This module adapts the existing Codex provider into the campaign worker
protocol. It does not read, write, log, or persist credentials.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path

from aider.providers.base import BaseProvider
from aider.providers.codex import CodexProvider
from aider.relay.campaign import (
    CampaignEvent,
    CampaignState,
    DryRunWorkerResult,
    QueueRecord,
)
from aider.relay.campaign_runner import WorkerResult


class CodexCliCampaignWorker:
    def __init__(
        self,
        *,
        cwd: str | Path | None = None,
        sandbox: str = "read-only",
        approval_policy: str = "never",
        ephemeral: bool = True,
        turn_timeout: int = 600,
        dangerously_bypass_approvals_and_sandbox: bool = False,
        provider_factory: Callable[[], BaseProvider] | None = None,
    ):
        self.cwd = Path(cwd) if cwd else None
        self.sandbox = sandbox
        self.approval_policy = approval_policy
        self.ephemeral = ephemeral
        self.turn_timeout = turn_timeout
        self.dangerously_bypass_approvals_and_sandbox = dangerously_bypass_approvals_and_sandbox
        self.provider_factory = provider_factory
        self.prompts_received: list[str] = []

    def run_queue(self, queue: QueueRecord, state: CampaignState) -> WorkerResult:
        prompt = campaign_prompt_for_codex(queue)
        self.prompts_received.append(prompt)
        provider = self._make_provider()
        try:
            return asyncio.run(self._run_provider(provider, prompt))
        except TimeoutError:
            return WorkerResult(
                outcome=DryRunWorkerResult.BLOCKED_EXTERNAL,
                summary=f"codex cli timed out after {self.turn_timeout}s",
                provider="codex",
            )

    def _make_provider(self) -> BaseProvider:
        if self.provider_factory:
            return self.provider_factory()
        return CodexProvider(
            sandbox=self.sandbox,
            approval_policy=self.approval_policy,
            cwd=self.cwd,
            ephemeral=self.ephemeral,
            dangerously_bypass_approvals_and_sandbox=(
                self.dangerously_bypass_approvals_and_sandbox
            ),
        )

    async def _run_provider(self, provider: BaseProvider, prompt: str) -> WorkerResult:
        return await asyncio.wait_for(
            self._collect_provider_events(provider, prompt),
            timeout=self.turn_timeout,
        )

    async def _collect_provider_events(self, provider: BaseProvider, prompt: str) -> WorkerResult:
        messages = []
        events = [
            CampaignEvent(
                type="provider.started",
                message="codex cli started",
                provider="codex",
            )
        ]
        async for event in provider.run_turn(prompt):
            if event.type == "text" and event.content:
                messages.append(event.content)
                events.append(
                    CampaignEvent(
                        type="provider.text",
                        message=event.content,
                        provider="codex",
                    )
                )
            elif event.type == "exhausted":
                return WorkerResult(
                    outcome=DryRunWorkerResult.BLOCKED_EXTERNAL,
                    summary="codex cli exhausted",
                    provider="codex",
                    reset_at=event.reset_at,
                    events=[
                        *events,
                        CampaignEvent(
                            type="provider.exhausted",
                            message="codex cli exhausted",
                            provider="codex",
                            data={"reset_at": event.reset_at},
                        ),
                    ],
                )
            elif event.type == "error":
                return WorkerResult(
                    outcome=DryRunWorkerResult.BLOCKED_EXTERNAL,
                    summary=f"codex cli error: {event.content}",
                    provider="codex",
                    events=[
                        *events,
                        CampaignEvent(
                            type="provider.error",
                            message=event.content,
                            provider="codex",
                        ),
                    ],
                )
            elif event.type == "done":
                return WorkerResult(
                    outcome=DryRunWorkerResult.COMPLETED,
                    summary="\n".join(messages).strip() or "codex cli completed",
                    provider="codex",
                    events=[
                        *events,
                        CampaignEvent(
                            type="provider.completed",
                            message="codex cli completed",
                            provider="codex",
                            data={"session_id": event.session_id},
                        ),
                    ],
                )

        return WorkerResult(
            outcome=DryRunWorkerResult.BLOCKED_EXTERNAL,
            summary="codex cli ended without done event",
            provider="codex",
            events=[
                *events,
                CampaignEvent(
                    type="provider.error",
                    message="codex cli ended without done event",
                    provider="codex",
                ),
            ],
        )


def campaign_prompt_for_codex(queue: QueueRecord) -> str:
    task = queue.prompt or queue.title or queue.id
    return (
        "You are a bounded worker in an aider-relay campaign. "
        "Complete only this queue and then stop. The orchestrator decides what runs next.\n\n"
        f"Queue: {queue.id}\n"
        f"Title: {queue.title or queue.id}\n\n"
        f"Task:\n{task}\n"
    )
