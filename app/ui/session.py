"""Small immutable representation of the active app session.

Carries just enough for the shell and every view: who is acting now. The
acting user is always passed explicitly into every business-data write
(AGENTS.md §6); views read ``user_id`` from here and never guess or default.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    user_id: int
    user_name: str
