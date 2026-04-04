# web/scheduler.py

from __future__ import annotations

import atexit
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from gmail_sync import check_replies_for_user
from models_saas import save_outbound_gmail_metadata
from models_saas import get_scheduler_template, get_branding
from scheduler_render import render_scheduler_html, DEFAULT_SCHEDULER_TEMPLATE
from gmail_sync import send_email_gmail
from web.compute_next import compute_next_send_at
from web.smart_followups import evaluate_smart_followup
from web.smart_templates import render_smart_template
from models_saas import update_smart_followup_state, stop_smart_followup
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
_started = False

from zoneinfo import ZoneInfo
TZ = ZoneInfo("Africa/Lagos")


def now_iso() -> str:
    return datetime.now(TZ).replace(tzinfo=None).isoformat(timespec="seconds")


from send_via_preference import (
    format_plain_text_message,
    render_text_email_html,
    build_branded_email_html,
)
from email_scheduler import send_branded_email_gmail
from flask import current_app

import time


def send_followup_email(user: dict, f: dict, message: str | None):
    def as_text(value, default=""):
        return value.strip() if isinstance(value, str) else default

    to_email = as_text(f.get("email"))
    if not to_email:
        raise RuntimeError("Missing recipient email")

    followup_type = as_text(f.get("followup_type"), "Follow-Up")
    client_name = as_text(f.get("client_name"), "Client")

    subject = as_text(f.get("subject")) or f"{followup_type.title()} for {client_name}"

    email_format = as_text(f.get("email_format"), "html").lower()
    if email_format not in {"text", "html", "raw"}:
        email_format = "html"

    raw_message = (
        message
        if isinstance(message, str) and message.strip()
        else as_text(f.get("message_override")) or as_text(f.get("description"))
    )

    if email_format == "text":
        formatted = format_plain_text_message(raw_message)
        branding = get_branding(user.get("id")) or {}
        html_body = render_text_email_html(user, f, formatted, branding)

        send_meta = send_email_gmail(
            user,
            to_email,
            subject,
            html_body,
            is_html=True,
        )
        return send_meta

    # Default: branded HTML
    if raw_message and not as_text(f.get("message_override")):
        f = dict(f)
        f["message_override"] = raw_message

    html_body = build_branded_email_html(user, f)

    send_meta = send_email_gmail(
        user,
        to_email,
        subject,
        html_body,
        is_html=True,
    )
    return send_meta


def run_scheduled_sends(app) -> None:
    with app.app_context():
        tick = now_iso()
        current_app.logger.info(f"[SCHED] ===== TICK START @ {tick} =====")

        users = get_all_users() or []
        current_app.logger.info(f"[SCHED] total users: {len(users)}")

        for u in users:
            uid = int(u["id"])
            current_app.logger.info(f"[SCHED][USER {uid}] processing")

            # =========================
            # STEP 1: REPLY DETECTION
            # =========================
            try:
                current_app.logger.debug(f"[SCHED][USER {uid}] checking replies...")
                reply_results = check_replies_for_user(u)
                for r in reply_results or []:
                    fid = r.get("followup_id")
                    if not fid:
                        continue

                    current_app.logger.info(
                        f"[REPLY][USER {uid}][F {fid}] reply detected → stopping automation"
                    )

                    stop_smart_followup(fid, uid, "Client replied")

                if reply_results:
                    current_app.logger.info(
                        f"[SCHED][USER {uid}] replies detected: {len(reply_results)}"
                    )
                else:
                    current_app.logger.debug(f"[SCHED][USER {uid}] no replies found")

            except Exception:
                current_app.logger.exception(
                    f"[SCHED][USER {uid}] reply detection FAILED"
                )

            # =========================
            # STEP 2: FETCH DUE ITEMS
            # =========================
            items = get_due_scheduled(uid, tick) or []
            current_app.logger.info(
                f"[SCHED][USER {uid}] due followups: {len(items)}"
            )

            # =========================
            # STEP 3: SEND LOOP
            # =========================
            for f in items:
                fid = int(f["id"])
                current_app.logger.info(
                    f"[SCHED][USER {uid}][F {fid}] START sending"
                )

                try:
                    if not (u.get("gmail_token") or "").strip():
                        current_app.logger.warning(
                            f"[SCHED][USER {uid}][F {fid}] Gmail not connected"
                        )
                        mark_send_failed(fid, uid, "Gmail not connected")
                        continue

                    # Mark running
                    try:
                        set_status_running(fid, uid)
                    except Exception:
                        current_app.logger.warning(
                            f"[SCHED][USER {uid}][F {fid}] failed to set running"
                        )

                    # =========================
                    # ✅ SMART FOLLOW-UP LOGIC
                    # =========================
                    smart_enabled = int(f.get("smart_enabled") or 0) == 1

                    if smart_enabled:
                        decision = evaluate_smart_followup(f)

                        current_app.logger.info(
                            "[SMART][USER %s][F %s] should_send=%s stage=%s template=%s note=%s",
                            uid,
                            fid,
                            decision.should_send,
                            decision.stage,
                            decision.template_key,
                            decision.decision_note,
                        )

                        update_smart_followup_state(
                            fid=fid,
                            user_id=uid,
                            stage=decision.stage,
                            template_key=decision.template_key,
                            decision_note=decision.decision_note,
                        )

                        if decision.stop_reason:
                            stop_smart_followup(fid, uid, decision.stop_reason)
                            continue

                        if not decision.should_send:
                            current_app.logger.info(
                                f"[SMART][USER {uid}][F {fid}] skipped (no send)"
                            )

                            # ✅ move next send forward (avoid infinite loop)
                            repeat = (f.get("schedule_repeat") or "once").strip().lower()

                            if repeat != "once":
                                next_at = compute_next_send_at(
                                    start_date=(f.get("schedule_start_date") or "")[:10] or datetime.utcnow().date().isoformat(),
                                    send_time=(f.get("schedule_send_time") or "09:00"),
                                    repeat=repeat,
                                    rel_value=f.get("schedule_rel_value"),
                                    rel_unit=f.get("schedule_rel_unit"),
                                    input_tz="Africa/Lagos",
                                )

                                mark_send_success_repeat(fid, uid, next_at)

                            continue

                        context = {
                            "name": f.get("client_name") or "there",
                            "type": f.get("followup_type") or "follow-up",
                            "sender": (get_branding(uid) or {}).get("company_name")
                            or "Your Company",
                        }

                        smart_message = render_smart_template(
                            decision.template_key, context
                        )

                        f = dict(f)
                        f["message_override"] = smart_message

                    # =========================
                    # BUILD EMAIL
                    # =========================
                    tmpl = get_scheduler_template(uid) or DEFAULT_SCHEDULER_TEMPLATE
                    branding = get_branding(uid)

                    body_html = render_scheduler_html(
                        tmpl,
                        user=u,
                        followup=f,
                        branding=branding,
                    )

                    # SEND EMAIL
                    send_meta = send_followup_email(u, f, body_html)

                    if send_meta:
                        current_app.logger.info(
                            f"[SCHED][USER {uid}][F {fid}] SENT OK"
                        )

                        save_outbound_gmail_metadata(
                            fid=fid,
                            user_id=uid,
                            gmail_message_id=send_meta.get("message_id") or "",
                            gmail_thread_id=send_meta.get("thread_id") or "",
                        )

                    # =========================
                    # STEP 4: HANDLE REPEAT
                    # =========================
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

                    if next_at and next_at < tick:
                        next_at = (
                            datetime.now(TZ) + timedelta(seconds=60)
                        ).replace(tzinfo=None).isoformat(timespec="seconds")

                    mark_send_success_repeat(fid, uid, next_at)

                except Exception as e:
                    current_app.logger.exception(
                        f"[SCHED][USER {uid}][F {fid}] SEND FAILED"
                    )
                    mark_send_failed(fid, uid, f"{type(e).__name__}: {e}")

            # =========================
            # STEP 5: CLEANUP
            # =========================
            grace_cutoff = (
                datetime.now() - timedelta(minutes=2)
            ).isoformat(timespec="seconds")

            mark_schedule_passed(uid, grace_cutoff)

        current_app.logger.info(f"[SCHED] ===== TICK END =====")


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
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.start()
    _started = True
    print("[SCHEDULER] Started (scheduled_sends every 30s)")
    atexit.register(lambda: scheduler.shutdown())