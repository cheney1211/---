"""Startup recovery logic for pending tool calls.

Called once when the FastAPI app starts.
See DESIGN.md / plan for the safety policy:
  - running  -> error  (never auto-retry to avoid duplicate side-effects)
  - queued   -> error  (unless idempotency_key present)
"""

from __future__ import annotations

import logging
from typing import List

from .models import PendingToolCallRow
from .repositories import PendingToolRepo

logger = logging.getLogger("storage.recovery")


async def recover_pending_tool_calls() -> List[PendingToolCallRow]:
    """Scan for interrupted or queued tool calls and mark them safe.

    Returns the list of entries that were transitioned to ``error`` so
    the caller can log or surface them in the UI.
    """
    pendings = await PendingToolRepo.list_resumable()
    handled: List[PendingToolCallRow] = []

    for p in pendings:
        if p.status == "running":
            # Crash during execution -> mark error, require manual retry
            await PendingToolRepo.mark_error(
                p.id,
                "Execution interrupted (process crash). Please retry manually.",
            )
            logger.warning(
                "Pending tool call #%d [%s] was running at shutdown -> marked error",
                p.id,
                p.tool_name,
            )
            handled.append(p)

        elif p.status == "queued":
            if p.idempotency_key:
                # Safe to auto-retry: reset to queued (already queued, no change needed)
                logger.info(
                    "Pending tool call #%d [%s] has idempotency_key, "
                    "left as queued for auto-retry",
                    p.id,
                    p.tool_name,
                )
            else:
                # No idempotency guarantee -> mark error
                await PendingToolRepo.mark_error(
                    p.id,
                    "App restarted before execution. "
                    "No idempotency_key, please retry manually.",
                )
                logger.warning(
                    "Pending tool call #%d [%s] queued but no idempotency_key "
                    "-> marked error",
                    p.id,
                    p.tool_name,
                )
                handled.append(p)

    return handled
