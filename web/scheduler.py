# web/scheduler.py

from __future__ import annotations

import atexit
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

from models_saas import get_scheduler_template, get_branding
from scheduler_render import render_scheduler_html, DEFAULT_SCHEDULER_TEMPLATE
from gmail_sync import send_email_gmail
from web.compute_next import compute_next_send_at

from models_saas import (
    get_all_users,
    get_due_scheduled,
    mark_send_failed,
    mark_schedule_passed,
    set_status_running,
    mark_send_success_once,
    mark_send_success_repeat,
)

scheduler = BackgroundScheduler()
_started = False   # ✅ MUST start as False


from zoneinfo import ZoneInfo
TZ = ZoneInfo("Africa/Lagos")

def now_iso() -> str:
    # consistent with compute_next_send_at(input_tz="Africa/Lagos")
    return datetime.now(TZ).replace(tzinfo=None).isoformat(timespec="seconds")

def send_followup_email(user: dict, f: dict, message: str) -> None:
    to_email = (f.get("email") or "").strip()
    if not to_email:
        raise RuntimeError("Missing recipient email")

    subject = f"Follow-up: {f.get('followup_type') or 'follow-up'}"

    send_email_gmail(
        user=user,
        to_email=to_email,
        subject=subject,
        html_body=message,
    )


def run_scheduled_sends(app) -> None:
    with app.app_context():
        tick = now_iso()
        print("[SCHED] tick", tick)

        users = get_all_users() or []
        for u in users:
            uid = int(u["id"])

            items = get_due_scheduled(uid, tick) or []
            print("[SCHED] user", uid, "due", len(items))

            for f in items:
                fid = int(f["id"])

                try:
                    if not (u.get("gmail_token") or "").strip():
                        mark_send_failed(fid, uid, "Gmail not connected")
                        continue

                    try:
                        set_status_running(fid, uid)
                    except Exception as e:
                        print("[SCHED] warning: set_status_running failed", fid, uid, repr(e))

                    tmpl = get_scheduler_template(uid) or DEFAULT_SCHEDULER_TEMPLATE
                    branding = get_branding(uid)

                    body_html = render_scheduler_html(
                        tmpl,
                        user=u,
                        followup=f,
                        branding=branding,
                    )

                    send_followup_email(u, f, body_html)

                    repeat = (f.get("schedule_repeat") or "once").strip().lower()

                    if repeat == "once":
                        mark_send_success_once(fid, uid)
                        continue

                    start_date = (
                        (f.get("schedule_start_date") or "").strip()
                        or ((f.get("next_send_at") or "")[:10] if (f.get("next_send_at") or "").strip() else "")
                        or (f.get("due_date") or "").strip()
                    )
                    if not start_date:
                        start_date = datetime.utcnow().date().isoformat()

                    next_at = compute_next_send_at(
                        start_date=start_date,
                        send_time=(f.get("schedule_send_time") or "09:00"),
                        repeat=repeat,
                        rel_value=f.get("schedule_rel_value"),
                        rel_unit=f.get("schedule_rel_unit"),
                        input_tz="Africa/Lagos",
                        send_time_2=f.get("schedule_send_time_2"),
                        interval=f.get("schedule_interval"),
                        byweekday=f.get("schedule_byweekday"),
                    )

                    # 🔒 safety net: never schedule in the past
                    if next_at and next_at < tick:
                        next_at = (
                            datetime.now(TZ) + timedelta(seconds=60)
                        ).replace(tzinfo=None).isoformat(timespec="seconds")

                    mark_send_success_repeat(fid, uid, next_at)

                except Exception as e:
                    mark_send_failed(fid, uid, f"{type(e).__name__}: {e}")

            grace_cutoff = (datetime.now() - timedelta(minutes=2)).isoformat(timespec="seconds")
            mark_schedule_passed(uid, grace_cutoff)

def start_scheduler(app) -> None:
    global _started
    if _started:
        print("[SCHEDULER] already started")
        return

    scheduler.add_job(
        run_scheduled_sends,
        "interval",
        seconds=30,
        args=[app],
        id="scheduled_sends",
        replace_existing=True,
        max_instances=1,          # ✅ prevents overlapping runs
        coalesce=True,            # ✅ if it misses a tick, it merges
        misfire_grace_time=60,    # ✅ don’t skip if app was busy
    )

    scheduler.start()
    _started = True              # ✅ set TRUE only after start
    print("[SCHEDULER] Started (scheduled_sends every 30s)")
    atexit.register(lambda: scheduler.shutdown())
