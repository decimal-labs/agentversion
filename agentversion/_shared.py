"""Shared types used across replay, dataset, and other spec modules.

Internal module — do not import from outside the package. Public re-exports
live in ``agentversion.replay`` and ``agentversion.dataset``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Message(BaseModel):
    """A message in a conversation or trace.

    Used by both replay inputs and dataset step inputs.
    """

    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str | None = None
    content_ref: str | None = None
    name: str | None = None
