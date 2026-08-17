"""Small immutable representation of the active app session.

Carries just enough for the shell and every view: who is acting now. The
acting user is always passed explicitly into every business-data write
(AGENTS.md §6); views read ``user_id`` from here and never guess or default.

``read_only`` marks an archived-ledger session (plan-04 Task 3): while true,
views omit every write-triggering control and only the read surfaces stay
mounted. Defaults to ``False`` so the normal live-ledger flow is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    user_id: int
    user_name: str
    read_only: bool = False
