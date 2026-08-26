"""Confirmation manager for human-in-the-loop tool approval.

When a tool with requires_confirmation=True is about to execute,
the system pauses and waits for the user to approve or reject via
a confirmation_id. Used by both Web (SSE + POST) and CLI (prompt) flows.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("confirmation")


@dataclass
class ConfirmationRequest:
    """A pending confirmation request."""
    confirmation_id: str
    tool_name: str
    tool_args: Dict[str, Any]
    description: str
    _future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())


class ConfirmationManager:
    """Manages pending confirmation requests.

    Workflow:
      1. create_request() -> returns ConfirmationRequest with a confirmation_id
      2. Yield a confirmation_required event to the frontend (SSE) or prompt (CLI)
      3. await request._future  (pauses execution)
      4. resolve() is called by the confirm API endpoint or CLI input
      5. Execution resumes with the user's decision
    """

    def __init__(self) -> None:
        self._pending: Dict[str, ConfirmationRequest] = {}

    def create_request(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        description: str = "",
    ) -> ConfirmationRequest:
        """Create a new confirmation request and register it."""
        req = ConfirmationRequest(
            confirmation_id=str(uuid.uuid4()),
            tool_name=tool_name,
            tool_args=tool_args,
            description=description
                or f"工具 '{tool_name}' 需要确认授权。参数: {tool_args}",
        )
        self._pending[req.confirmation_id] = req
        logger.info(
            "Created confirmation request %s for tool '%s'",
            req.confirmation_id,
            tool_name,
        )
        return req

    def resolve(self, confirmation_id: str, approved: bool) -> bool:
        """Resolve a pending confirmation request.

        Returns True if the request was found and resolved, False otherwise.
        """
        req = self._pending.pop(confirmation_id, None)
        if req is None:
            logger.warning("Confirmation request %s not found", confirmation_id)
            return False
        if req._future.done():
            logger.warning("Confirmation request %s already resolved", confirmation_id)
            return False
        req._future.set_result(approved)
        logger.info(
            "Resolved confirmation %s: %s",
            confirmation_id,
            "approved" if approved else "rejected",
        )
        return True

    def get_request(self, confirmation_id: str) -> Optional[ConfirmationRequest]:
        """Get a pending request by ID."""
        return self._pending.get(confirmation_id)

    def list_pending(self) -> list[Dict[str, Any]]:
        """List all pending confirmation requests."""
        return [
            {
                "confirmation_id": req.confirmation_id,
                "tool_name": req.tool_name,
                "tool_args": req.tool_args,
                "description": req.description,
            }
            for req in self._pending.values()
        ]

    async def wait_for_decision(self, confirmation_id: str, timeout: float = 300.0) -> bool:
        """Wait for the user's decision. Returns True if approved, False if rejected.

        Raises TimeoutError if no response within timeout seconds.
        """
        req = self._pending.get(confirmation_id)
        if req is None:
            raise ValueError(f"Confirmation request {confirmation_id} not found")
        try:
            result = await asyncio.wait_for(req._future, timeout=timeout)
            return bool(result)
        except asyncio.TimeoutError:
            self._pending.pop(confirmation_id, None)
            raise TimeoutError(
                f"Confirmation request {confirmation_id} timed out after {timeout}s"
            )

    @property
    def has_pending(self) -> bool:
        return len(self._pending) > 0