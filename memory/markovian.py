"""Meterless Markovian wrapper — bounded-context long reasoning.

Each step sees only (compressed carryover + new context), never the full
history, so synthesis over many findings can't overflow the context window.
The step function is injected (an LLM call in Synthesis); the default just
concatenates and truncates. Swap internals for the Meterless SDK later.
"""
import uuid
from typing import Callable

StepFn = Callable[[str, str, str], str]   # (goal, carryover, new_context) → new carryover


def _truncate_step(goal: str, carryover: str, new_context: str) -> str:
    return f"{carryover}\n{new_context}".strip()


class Markovian:
    def __init__(self, task_id: str | None = None, max_carryover_chars: int = 3000,
                 step_fn: StepFn | None = None):
        self.task_id = task_id or f"mk-{uuid.uuid4().hex[:12]}"
        self.max_carryover_chars = max_carryover_chars
        self.step_fn = step_fn or _truncate_step
        self.goal = ""
        self.constraints: list[str] = []
        self._carryover = ""
        self._trace: list[dict] = []

    def start_task(self, goal: str, constraints: list[str] | None = None) -> None:
        self.goal = goal
        self.constraints = constraints or []
        self._carryover = ""
        self._trace = []

    def next_step(self, carryover: str | None, new_context: str, label: str = "") -> dict:
        carry_in = self._carryover if carryover is None else carryover
        try:
            carry_out = self.step_fn(self.goal, carry_in, new_context)
        except Exception:
            carry_out = _truncate_step(self.goal, carry_in, new_context)
        carry_out = (carry_out or "")[: self.max_carryover_chars]
        self._carryover = carry_out
        step = {
            "step": len(self._trace) + 1,
            "label": label,
            "context_chars": len(new_context),
            "carryover_in_chars": len(carry_in),
            "carryover_out_chars": len(carry_out),
            "carryover": carry_out,
        }
        self._trace.append(step)
        return step

    def get_carryover(self) -> str:
        return self._carryover

    def get_trace(self) -> list[dict]:
        return list(self._trace)
