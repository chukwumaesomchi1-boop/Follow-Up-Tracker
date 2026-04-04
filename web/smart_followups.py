# web/smart_followups.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


SMART_STAGES = ("nudge_1", "nudge_2", "nudge_3", "close_out")


@dataclass
class SmartDecision:
    should_send: bool
    stage: str
    template_key: str
    next_delay_days: int
    stop_reason: str = ""
    decision_note: str = ""


def as_text(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) else default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def parse_iso(value: str) -> Optional[datetime]:
    value = as_text(value)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def days_since(dt: Optional[datetime], now: datetime) -> Optional[int]:
    if not dt:
        return None
    return max(0, (now - dt).days)


def choose_stage(sent_count: int) -> str:
    if sent_count <= 0:
        return "nudge_1"
    if sent_count == 1:
        return "nudge_2"
    if sent_count == 2:
        return "nudge_3"
    return "close_out"


def template_for_stage(stage: str, followup_type: str) -> str:
    ft = as_text(followup_type, "general").lower()

    mapping = {
        "nudge_1": f"{ft}_nudge_1",
        "nudge_2": f"{ft}_nudge_2",
        "nudge_3": f"{ft}_nudge_3",
        "close_out": f"{ft}_close_out",
    }
    return mapping.get(stage, f"{ft}_nudge_1")


def delay_for_stage(stage: str) -> int:
    delays = {
        "nudge_1": 2,
        "nudge_2": 3,
        "nudge_3": 4,
        "close_out": 5,
    }
    return delays.get(stage, 3)


def evaluate_smart_followup(followup: Dict[str, Any], now: Optional[datetime] = None) -> SmartDecision:
    now = now or datetime.utcnow()

    status = as_text(followup.get("status")).lower()
    if status in {"replied", "done", "deleted"}:
        return SmartDecision(
            should_send=False,
            stage=as_text(followup.get("smart_stage"), "nudge_1"),
            template_key="",
            next_delay_days=0,
            stop_reason=status,
            decision_note=f"Stopped because status is {status}.",
        )

    sent_count = as_int(followup.get("sent_count"), 0)
    max_sends = as_int(followup.get("max_sends"), 4)

    if sent_count >= max_sends:
        return SmartDecision(
            should_send=False,
            stage="close_out",
            template_key="",
            next_delay_days=0,
            stop_reason="max_sends_reached",
            decision_note="Stopped because max sends was reached.",
        )

    last_sent_at = parse_iso(as_text(followup.get("last_sent_at")))
    days_waited = days_since(last_sent_at, now)

    stage = choose_stage(sent_count)
    template_key = template_for_stage(stage, as_text(followup.get("followup_type"), "general"))
    next_delay = delay_for_stage(stage)

    # First send in smart mode
    if sent_count == 0 and last_sent_at is None:
        return SmartDecision(
            should_send=True,
            stage=stage,
            template_key=template_key,
            next_delay_days=next_delay,
            decision_note="First smart follow-up send.",
        )

    # Wait until enough days have passed
    if days_waited is not None and days_waited < next_delay:
        return SmartDecision(
            should_send=False,
            stage=stage,
            template_key=template_key,
            next_delay_days=next_delay,
            decision_note=f"Waiting. Only {days_waited} day(s) since last send.",
        )

    return SmartDecision(
        should_send=True,
        stage=stage,
        template_key=template_key,
        next_delay_days=next_delay,
        decision_note=f"Stage {stage} selected after {days_waited} day(s).",
    )