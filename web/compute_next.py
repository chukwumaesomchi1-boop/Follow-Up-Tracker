
from __future__ import annotations
from datetime import datetime
from database import get_connection


from datetime import datetime, timedelta, timezone


def _now_utc():
    return datetime.now(timezone.utc)

def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()





from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional




def _parse_unit(unit: str) -> str:
    u = (unit or "").strip().lower()
    aliases = {
        "min": "minutes",
        "mins": "minutes",
        "minute": "minutes",
        "minutes": "minutes",
        "hr": "hours",
        "hrs": "hours",
        "hour": "hours",
        "hours": "hours",
        "day": "days",
        "days": "days",
    }
    if u in aliases:
        return aliases[u]
    raise ValueError(f"Unsupported rel_unit: {unit!r} (use minutes/hours/days)")


def _coerce_int(value: Optional[int], default: int = 1) -> int:
    if value is None:
        return default
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"rel_value must be an int, got {value!r}")
    if v <= 0:
        raise ValueError(f"rel_value must be > 0, got {v}")
    return v


def _parse_start_datetime(
    start_date: str,
    send_time: str,
    input_tz: Optional[str] = "UTC",
) -> datetime:
    """
    start_date: 'YYYY-MM-DD'
    send_time: 'HH:MM' (24h)
    input_tz: IANA tz like 'Africa/Lagos' or 'UTC'
    Returns an aware datetime converted to UTC.
    """
    if not start_date or not send_time:
        raise ValueError("start_date and send_time are required for non-relative schedules")

    # Normalize send_time a bit (e.g., allow '9:05' -> '09:05')
    st = send_time.strip()
    if len(st.split(":")) != 2:
        raise ValueError(f"send_time must be 'HH:MM', got {send_time!r}")

    hh, mm = st.split(":")
    if not (hh.isdigit() and mm.isdigit()):
        raise ValueError(f"send_time must be numeric 'HH:MM', got {send_time!r}")
    hh_i, mm_i = int(hh), int(mm)
    if not (0 <= hh_i <= 23 and 0 <= mm_i <= 59):
        raise ValueError(f"send_time out of range, got {send_time!r}")

    local_tz = ZoneInfo(input_tz or "UTC")
    # Build a local-time aware datetime, then convert to UTC
    dt_local = datetime.fromisoformat(start_date).replace(
        hour=hh_i, minute=mm_i, second=0, microsecond=0, tzinfo=local_tz
    )
    return dt_local.astimezone(timezone.utc)




from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo

# assumes you already have these helpers in the same file:
# - _now_utc()
# - _coerce_int()
# - _parse_unit()
# - _parse_start_datetime(start_date, send_time, input_tz=...)
# - _iso(dt)

_WEEKDAY_MAP = {
    "MO": 0,
    "TU": 1,
    "WE": 2,
    "TH": 3,
    "FR": 4,
    "SA": 5,
    "SU": 6,
}

def _parse_hhmm(hhmm: str, default: str = "09:00") -> tuple[int, int]:
    s = (hhmm or "").strip() or default
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError(f"Bad time format: {hhmm!r} (expected HH:MM)")
    return int(parts[0]), int(parts[1])



from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo


from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo

# You already have these in your file somewhere:
# _now_utc(), _iso(dt), _coerce_int(), _parse_unit(), _parse_hhmm(), _parse_start_datetime()
# _WEEKDAY_MAP = {"MO":0,"TU":1,"WE":2,"TH":3,"FR":4,"SA":5,"SU":6}

def compute_next_send_at(
    start_date: str,
    send_time: str,
    repeat: str,
    rel_value: int | None = None,
    rel_unit: str | None = None,
    input_tz: str | None = "UTC",
    send_time_2: str | None = None,
    interval: int | None = None,          # every_n_days
    byweekday: str | None = None,         # weekday, e.g. "MO,TU,FR"
) -> str:
    """
    Returns ISO string in UTC.

    Key rule:
      - For non-relative repeats, NEVER schedule before start_date (if provided).
      - NEVER return past/now; clamp to now+10s.
    """

    def _clamp_next_send_at(dt_utc: datetime, now_utc: datetime) -> datetime:
        if dt_utc <= now_utc:
            dt_utc = now_utc + timedelta(seconds=10)
        return dt_utc

    def _parse_start_day_local(tz: ZoneInfo, now_local: datetime) -> date | None:
        raw = (start_date or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except Exception:
            raise ValueError("start_date must be YYYY-MM-DD")

    rep = (repeat or "").strip().lower()
    now_utc = _now_utc()  # tz-aware UTC datetime

    # -------------------------
    # RELATIVE (pure UTC)
    # -------------------------
    if rep == "relative":
        v = _coerce_int(rel_value, default=1)
        unit = _parse_unit(rel_unit or "hours")
        if unit == "minutes":
            dt_utc = now_utc + timedelta(minutes=v)
        elif unit == "hours":
            dt_utc = now_utc + timedelta(hours=v)
        else:
            dt_utc = now_utc + timedelta(days=v)
        return _iso(_clamp_next_send_at(dt_utc, now_utc))

    # -------------------------
    # Local time helpers
    # -------------------------
    tz = ZoneInfo(input_tz or "UTC")
    now_local = now_utc.astimezone(tz)

    start_day = _parse_start_day_local(tz, now_local)  # may be None
    # earliest day we allow scheduling on (for all non-relative repeats)
    min_day = max(now_local.date(), start_day) if start_day else now_local.date()

    # -------------------------
    # ONCE
    # -------------------------
    if rep == "once":
        dt_utc = _parse_start_datetime(start_date, send_time, input_tz=input_tz)
        return _iso(_clamp_next_send_at(dt_utc, now_utc))

    # -------------------------
    # DAILY (respect start_date)
    # -------------------------
    if rep == "daily":
        hh, mm = _parse_hhmm(send_time, default="09:00")

        # schedule on min_day at send_time; if already passed (same day), go next day
        candidate_local = datetime(min_day.year, min_day.month, min_day.day, hh, mm, 0, tzinfo=tz)
        if candidate_local <= now_local:
            candidate_local += timedelta(days=1)

        dt_utc = candidate_local.astimezone(timezone.utc)
        return _iso(_clamp_next_send_at(dt_utc, now_utc))

    # -------------------------
    # TWICE DAILY (already respects start_date via min_day)
    # -------------------------
    if rep == "twice_daily":
        hh1, mm1 = _parse_hhmm(send_time, default="09:00")
        if not (send_time_2 or "").strip():
            raise ValueError("twice_daily requires send_time_2")
        hh2, mm2 = _parse_hhmm(send_time_2, default="15:00")

        day = min_day  # <-- key change: respect start_date
        cand1 = datetime(day.year, day.month, day.day, hh1, mm1, 0, tzinfo=tz)
        cand2 = datetime(day.year, day.month, day.day, hh2, mm2, 0, tzinfo=tz)

        for c in sorted([cand1, cand2]):
            if c > now_local:
                dt_utc = c.astimezone(timezone.utc)
                return _iso(_clamp_next_send_at(dt_utc, now_utc))

        tomorrow = day + timedelta(days=1)
        next_local = datetime(tomorrow.year, tomorrow.month, tomorrow.day, hh1, mm1, 0, tzinfo=tz)
        dt_utc = next_local.astimezone(timezone.utc)
        return _iso(_clamp_next_send_at(dt_utc, now_utc))

    # -------------------------
    # WEEKLY (respect start_date)
    # -------------------------
    if rep == "weekly":
        if not (start_date or "").strip():
            raise ValueError("weekly requires start_date (YYYY-MM-DD)")
        hh, mm = _parse_hhmm(send_time, default="09:00")

        start_d = date.fromisoformat(start_date.strip())
        target_wd = start_d.weekday()  # 0=Mon..6=Sun

        base_day = max(now_local.date(), start_d)
        days_ahead = (target_wd - base_day.weekday()) % 7
        candidate_day = base_day + timedelta(days=days_ahead)

        candidate_local = datetime(candidate_day.year, candidate_day.month, candidate_day.day, hh, mm, 0, tzinfo=tz)
        if candidate_local <= now_local:
            candidate_day += timedelta(days=7)
            candidate_local = datetime(candidate_day.year, candidate_day.month, candidate_day.day, hh, mm, 0, tzinfo=tz)

        dt_utc = candidate_local.astimezone(timezone.utc)
        return _iso(_clamp_next_send_at(dt_utc, now_utc))

    # -------------------------
    # EVERY N DAYS (from start_date) - already start_date based
    # -------------------------
    if rep == "every_n_days":
        if not (start_date or "").strip():
            raise ValueError("every_n_days requires start_date (YYYY-MM-DD)")
        n = _coerce_int(interval, default=1)
        if n < 1:
            n = 1

        hh, mm = _parse_hhmm(send_time, default="09:00")
        start_d = date.fromisoformat(start_date.strip())

        day = start_d
        if day < now_local.date():
            diff = (now_local.date() - day).days
            jumps = diff // n
            day = day + timedelta(days=jumps * n)
            if day < now_local.date():
                day = day + timedelta(days=n)

        candidate_local = datetime(day.year, day.month, day.day, hh, mm, 0, tzinfo=tz)
        if candidate_local <= now_local:
            day = day + timedelta(days=n)
            candidate_local = datetime(day.year, day.month, day.day, hh, mm, 0, tzinfo=tz)

        dt_utc = candidate_local.astimezone(timezone.utc)
        return _iso(_clamp_next_send_at(dt_utc, now_utc))

    # -------------------------
    # WEEKDAY (respect start_date)
    # -------------------------
    if rep == "weekday":
        hh, mm = _parse_hhmm(send_time, default="09:00")
        raw = (byweekday or "").strip()
        if not raw:
            raise ValueError("weekday requires byweekday (e.g. 'MO,TU,FR')")

        wanted: set[int] = set()
        for x in [p.strip().upper() for p in raw.split(",") if p.strip()]:
            if x not in _WEEKDAY_MAP:
                raise ValueError(f"Invalid weekday: {x!r} (use MO..SU)")
            wanted.add(_WEEKDAY_MAP[x])

        # Start searching from min_day (not today)
        for i in range(0, 21):
            day = min_day + timedelta(days=i)
            if day.weekday() not in wanted:
                continue
            candidate_local = datetime(day.year, day.month, day.day, hh, mm, 0, tzinfo=tz)
            if candidate_local > now_local:
                dt_utc = candidate_local.astimezone(timezone.utc)
                return _iso(_clamp_next_send_at(dt_utc, now_utc))

        # fallback: one week later at send_time
        day = min_day + timedelta(days=7)
        candidate_local = datetime(day.year, day.month, day.day, hh, mm, 0, tzinfo=tz)
        dt_utc = candidate_local.astimezone(timezone.utc)
        return _iso(_clamp_next_send_at(dt_utc, now_utc))

    raise ValueError(
        f"Unsupported repeat: {repeat!r} "
        "(use once/daily/twice_daily/weekly/every_n_days/weekday/relative)"
    )
