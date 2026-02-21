# web/app.py
from dotenv import load_dotenv
load_dotenv()

import os
import csv
from database import ensure_billing_columns
ensure_billing_columns()

import re
import secrets
from io import StringIO, BytesIO
from datetime import datetime, timedelta

# ✅ allow http:// for localhost dev only
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, Response, current_app, abort, jsonify
)





from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

import stripe
#  from xhtml2pdf import pisa
from google_auth_oauthlib.flow import Flow
# from auth_utils import start_email_verification
from database import init_db, get_connection, dict_connection
from flask import redirect, url_for, session, flash, request
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import secrets

from mailer import send_email_smtp 
from gmail_sync import send_email_gmail


from web.scheduler import start_scheduler

from models_saas import (
    # users
    create_user,
    get_user_by_email,
    get_user_by_id,
    is_trial_active,
    activate_subscription,
    update_gmail_token,
    _set_user_subscription_ids,
    _find_user_id_by_customer,
    _update_subscription_state,
   

    # followups
    add_followup,
    update_followup,
    get_followup,
    get_user_followups,
    update_followup_due_date,
    delete_followup,
    mark_followup_done_by_id,
    mark_followup_replied,

    # send tracking
    mark_send_attempt,
    mark_send_failed,
    mark_send_success,
    update_chase_stage,

    # templates/settings
    get_templates,
    save_template,
    get_settings,
    upsert_settings,

    # scheduler rules
    # set_followup_schedule,
    clear_followup_schedule,
    bulk_set_followup_schedule_rule,
    set_followup_schedule_rule,
    get_scheduler_settings,
    upsert_scheduler_settings,

    # notifications
    add_notification,
    mark_notification_read,
    get_notifications,

    # branding
    set_branding,
    get_branding,

    # email templates
    get_email_templates,
    add_email_template,
    update_email_template,
    delete_email_template,

    # analytics/admin
    get_analytics_data,
    stats_overview,
    get_all_users,

    # done count
    count_done,

    # message override
    update_followup_message_override,
)

# -----------------------------
# INIT
# -----------------------------
from flask import Flask
from flask_socketio import SocketIO
import os
import secrets
import stripe
from database import init_db, ensure_auth_columns

init_db()
ensure_auth_columns()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
# socketio = SocketIO(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
from flask_socketio import join_room

@socketio.on("join_import")
def join_import(data):
    job_id = (data or {}).get("job_id")
    if not job_id:
        return
    join_room(job_id)



import logging

# Quiet down engineio/socketio internal logs
logging.getLogger("engineio").setLevel(logging.ERROR)
logging.getLogger("socketio").setLevel(logging.ERROR)

# Optional: quiet werkzeug lines that contain /socket.io
class _NoSocketIOFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "/socket.io" not in msg

werkzeug_logger = logging.getLogger("werkzeug")
werkzeug_logger.addFilter(_NoSocketIOFilter())



@app.get("/import-csv-mapped/status/<job_id>")
def import_csv_mapped_status(job_id):
    job = IMPORT_JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "job_not_found"}), 404
    return jsonify({"ok": True, "job": job})


from flask import request, redirect, url_for, session, flash


from billing import billing_bp
app.register_blueprint(billing_bp)


OPEN_ENDPOINTS = {
    "static",
    "login",
    "register",
    "logout",

    # email verify
    "verify_email",
    "verify_email_submit",
    "verify_email_resend",

    # google oauth
    "auth_google",
    "auth_google_callback",

    # forgot password / reset
    "forgot_password",
    "forgot_password_verify",
    "reset_password_submit",
    "resett_password",

    # billing MUST be open or you will loop
    "billing",
    "subscribe",
    "billing_success",
    "billing_cancel",
}



@app.before_request
def gate_auth_and_verify():
    ep = request.endpoint or ""

    # allow public endpoints
    if ep in OPEN_ENDPOINTS:
        return None

    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login"))

    user = get_user_by_id(int(uid))
    if not user:
        session.clear()
        return redirect(url_for("login"))

    # email verification block (but verify routes are open so no loop)
    if int(user.get("email_verified") or 0) != 1:
        session["pending_verify_user_id"] = int(uid)
        return redirect(url_for("verify_email"))

    return None


@app.before_request
def gate_billing():
    ep = request.endpoint or ""
    if ep in OPEN_ENDPOINTS:
        return None

    uid = session.get("user_id")
    if not uid:
        return None  # auth gate handles redirect to login

    user = get_user_by_id(int(uid))
    if not user:
        return None

    if _has_access(user):
        return None

    flash("Your trial ended. Subscribe to continue.", "danger")
    return redirect(url_for("billing"))



@app.before_request
def debug_ep():
    print("PATH:", request.path, "ENDPOINT:", request.endpoint)



app.secret_key = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False  # local http


app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
app.config["MAX_IMPORT_PREVIEW_ROWS"] = 5
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False  # local http

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5001")
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL") or "admin@me.com").strip().lower()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",

]
CREDS_PATH = os.getenv("GOOGLE_CREDENTIALS") or "credentials.json"

from authlib.integrations.flask_client import OAuth
oauth = OAuth(app)
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)



# -----------------------------
# HELPERS
# -----------------------------
def parse_yyyy_mm_dd(date_str: str):
    date_str = (date_str or "").strip()
    if not date_str:
        return None, "Date is required (YYYY-MM-DD)."
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        return dt.isoformat(), None
    except ValueError:
        return None, "Invalid date. Use YYYY-MM-DD (example: 2026-01-19)."


def require_user():
    uid = session.get("user_id")
    if not uid:
        flash("Please log in.", "warning")
        return None, redirect(url_for("login"))

    user = get_user_by_id(int(uid))
    if not user:
        session.clear()
        flash("Session expired. Login again.", "warning")
        return None, redirect(url_for("login"))

    return user, None


@app.get("/verify-email/resend")
def resend_verification():
    uid = session.get("pending_verify_user_id")
    if not uid:
        flash("No verification in progress.", "danger")
        return redirect(url_for("login"))

    user = get_user_by_id(int(uid))
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("login"))

    try:
        start_email_verification(int(uid), user["email"])
    except Exception:
        current_app.logger.exception("Resend verification failed")
        flash("Could not resend code.", "danger")
        return redirect(url_for("verify_email"))

    flash("New code sent ✅", "success")
    return redirect(url_for("verify_email"))


def _endpoint_exists(name: str) -> bool:
    try:
        return name in current_app.view_functions
    except Exception:
        return False


import csv
import io
from flask import request, redirect, url_for, flash
from models_saas import add_followup,bulk_mark_done,bulk_delete_followups


import os, tempfile
from flask import request, render_template, redirect, url_for, flash
from import_csv import import_followups_from_csv
from models_saas import looks_like_text_file

def _get_user_id():
    from flask import session
    return int(session.get("user_id"))

import csv

@app.route("/import-csv", methods=["GET", "POST"])
def import_csv():
    user_id = _get_user_id()

    if request.method == "GET":
        return render_template("import.html")  # simple upload page

    # POST: upload -> read headers -> show mapping page
    up = request.files.get("file")

    if not up or up.filename == "":
        flash("Pick a CSV file first.", "danger")
        return redirect(url_for("import_csv"))

    if not allowed_file(up.filename):
        flash(
            "Only CSV files are supported. Export your Excel file as CSV and try again.",
            "danger",
        )
        return redirect(url_for("import_csv"))
    from werkzeug.utils import secure_filename
    import uuid
    tmpdir = tempfile.gettempdir()
    safe = secure_filename(up.filename)
    tmp_path = os.path.join(tmpdir, f"fu_{uuid.uuid4().hex}_{safe}")
    up.save(tmp_path)
    
    if not looks_like_text_file(tmp_path):
        flash("That file doesn’t look like a CSV. If it’s an Excel file (.xlsx), please export it as CSV and upload again.", "danger")
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return redirect(url_for("import_csv"))

    # read headers
    with open(tmp_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, [])

    if not headers:
        flash("CSV file has no header row.", "danger")
        return redirect(url_for("import_csv"))

    return render_template(
        "import_map.html",
        tmp_path=tmp_path,
        headers=headers,
    )

from models_saas import allowed_file
# @app.route("/preview/<int:fid>/edit-all", methods=["POST"])
# def preview_edit_all(fid):
#     user, block = require_user()
#     if block:
#         return block

#     f = get_followup(fid, user["id"])
#     if not f:
#         flash("Follow-up not found.", "danger")
#         return redirect(url_for("dashboard"))

#     # pull fields
#     client_name = (request.form.get("client_name") or "").strip()
#     email = (request.form.get("email") or "").strip()
#     preferred_channel = (request.form.get("preferred_channel") or "whatsapp").strip().lower()
#     followup_type = (request.form.get("followup_type") or "other").strip()
#     description = (request.form.get("description") or "").strip()
#     if err:
#         flash(err, "danger")
#         return redirect(url_for("preview", fid=fid))

#     # update followup row
#     ok = update_followup(
#         fid=fid,
#         user_id=user["id"],
#         client_name=client_name,
#         email=email,
#         followup_type=followup_type,
#         description=description,
#         due_date=due_date,
#         preferred_channel=preferred_channel,
#         # recurring_interval=f.get("recurring_interval", 0),  # keep same
#     )
#     if not ok:
#         flash("Update failed (not found / not yours).", "danger")
#         return redirect(url_for("preview", fid=fid))

#     # update message override
#     msg_override = (request.form.get("message_override") or "").strip()
#     update_followup_message_override(fid, user["id"], msg_override if msg_override else None)

#     flash("Saved ✅", "success")
#     return redirect(url_for("preview", fid=fid))


from datetime import datetime

@app.route("/preview/<int:fid>/edit-all", methods=["POST"])
def preview_edit_all(fid):
    user, block = require_user()
    if block:
        return block

    f = get_followup(fid, user["id"])
    if not f:
        flash("Follow-up not found.", "danger")
        return redirect(url_for("dashboard"))

    client_name = (request.form.get("client_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    preferred_channel = (request.form.get("preferred_channel") or "whatsapp").strip().lower()
    followup_type = (request.form.get("followup_type") or "other").strip()
    description = (request.form.get("description") or "").strip()

    # ✅ if your edit-all form does NOT include due_date, keep the existing one
    # due_date = (request.form.get("due_date") or "").strip() or (f.get("due_date") or "").strip()

    err = None
    if not client_name:
        err = "Client name is required."
    elif not email:
        err = "Email is required."
    if err:
        flash(err, "danger")
        return redirect(url_for("preview", fid=fid))

    ok = update_followup(
        fid=fid,
        user_id=user["id"],
        client_name=client_name,
        email=email,
        followup_type=followup_type,
        description=description,
        preferred_channel=preferred_channel,
    )
    if not ok:
        flash("Update failed (not found / not yours).", "danger")
        return redirect(url_for("preview", fid=fid))

    msg_override = (request.form.get("message_override") or "").strip()
    update_followup_message_override(fid, user["id"], msg_override if msg_override else None)

    flash("Saved ✅", "success")
    return redirect(url_for("preview", fid=fid))


from flask import jsonify, request
from scheduler_render import render_scheduler_html, DEFAULT_SCHEDULER_TEMPLATE
from models_saas import get_branding


@app.post("/scheduler-template/preview")
def scheduler_template_preview():
    user, block = require_user()
    if block:
        return block

    data = request.get_json(silent=True) or {}
    tmpl = (data.get("tmpl") or "").strip() or DEFAULT_SCHEDULER_TEMPLATE

    # sample followup/user values (NO real client data)
    sample_followup = {
        "client_name": "Alex",
        "followup_type": "invoice follow-up",
        "description": "Just checking in — quick reminder about the invoice. Reply if you need anything.",
        "due_date": "2026-02-17",
        "message_override": "",  # keep empty here
    }
    sample_user = {
        "id": user.get("id"),
        "name": user.get("name") or "You",
    }

    branding = get_branding(int(user["id"])) or {}

    try:
        preview_html = render_scheduler_html(
            tmpl=tmpl,
            user=sample_user,
            followup=sample_followup,
            branding=branding,
        )
        return jsonify({"ok": True, "preview_html": preview_html})
    except Exception as e:
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 400


import uuid
from flask_socketio import join_room

IMPORT_JOBS = {}  # job_id -> {"status": "...", "result": {...}}

@socketio.on("join_import")
def on_join_import(data):
    job_id = (data or {}).get("job_id")
    if job_id:
        join_room(job_id)



@app.get("/import-csv-mapped/result/<job_id>")
def import_csv_job_result(job_id):
    data = IMPORT_JOBS.get(job_id)
    if not data:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, **data})



# @app.route("/import-csv-mapped", methods=["POST"])
# def import_csv_mapped():
#     user_id = _get_user_id()

#     tmp_path = (request.form.get("tmp_path") or "").strip()
#     if not tmp_path:
#         flash("Import session is missing the uploaded file. Upload again.", "warning")
#         return redirect(url_for("import_csv"))

#     if not os.path.exists(tmp_path):
#         flash("Uploaded CSV is gone. Upload again.", "warning")
#         return redirect(url_for("import_csv"))

#     mapping = {
#         "client_name": request.form.get("col_name"),
#         "email": request.form.get("col_email"),
#         "phone": request.form.get("col_phone"),
#         "description": request.form.get("col_desc"),
#         "due_date": request.form.get("col_due"),
#     }

#     # ✅ validate BEFORE importing
#     if not (mapping.get("email") or "").strip():
#         flash("You must map an Email column.", "danger")
#         return redirect(url_for("import_csv"))

#     # ✅ import ONCE
#     result = import_followups_from_csv(tmp_path, user_id, mapping=mapping)

#     flash(f"Imported {result['imported']} | Skipped {result['skipped']}", "success")
#     for e in result.get("errors", [])[:5]:
#         flash(e, "warning")

#     # optional cleanup
#     try:
#         os.remove(tmp_path)
#     except Exception:
#         pass

#     return redirect(url_for("dashboard"))


from import_csv import import_followups_from_csv

@app.post("/import-csv-mapped/start")
def import_csv_mapped_start():
    user_id = _get_user_id()

    tmp_path = (request.form.get("tmp_path") or "").strip()
    if not tmp_path or not os.path.exists(tmp_path):
        return jsonify({"ok": False, "error": "missing_file"}), 400

    mapping = {
        "client_name": request.form.get("col_name"),
        "email": request.form.get("col_email"),
        "phone": request.form.get("col_phone"),
        "description": request.form.get("col_desc"),
        "due_date": request.form.get("col_due"),
        "preferred_channel": request.form.get("preferred_channel") or "email",
    }

    if not (mapping.get("email") or "").strip():
        return jsonify({"ok": False, "error": "missing_email_mapping"}), 400

    job_id = uuid.uuid4().hex
    IMPORT_JOBS[job_id] = {"status": "running", "result": None}

    def _run_job():
        def progress_cb(done, total):
            pct = 100 if total <= 0 else int((done / total) * 100)
            socketio.emit("import_progress", {"job_id": job_id, "done": done, "total": total, "pct": pct}, room=job_id)

        try:
            result = import_followups_from_csv(tmp_path, user_id, mapping=mapping, progress_cb=progress_cb)
            IMPORT_JOBS[job_id] = {"status": "done", "result": result}
            socketio.emit("import_done", {"job_id": job_id, "result": result}, room=job_id)
        except Exception as e:
            IMPORT_JOBS[job_id] = {"status": "error", "result": {"error": str(e)}}
            socketio.emit("import_error", {"job_id": job_id, "error": str(e)}, room=job_id)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    socketio.start_background_task(_run_job)

    return jsonify({"ok": True, "job_id": job_id})



from flask import request, redirect, url_for, flash
from models_saas import mark_followup_done_by_id
from chase import build_message_preview
@app.post("/bulk-action")
def bulk_action():
    from flask import session

    user_id = int(session.get("user_id") or 0)
    if not user_id:
        flash("Please log in again.", "warning")
        return redirect(url_for("login"))

    ids = request.form.getlist("followup_ids")
    ids = [int(x) for x in ids if str(x).isdigit()]

    if not ids:
        flash("No followups selected.", "warning")
        return redirect(url_for("dashboard"))

    action = (request.form.get("action") or "").strip().lower()

    if action == "done":
        n = bulk_mark_done(user_id, ids)
        flash(f"Marked {n} as done.", "success")
        return redirect(url_for("dashboard"))

    if action == "delete":
        n = bulk_delete_followups(user_id, ids)
        flash(f"Deleted {n} followups.", "success")
        return redirect(url_for("dashboard"))

    if action == "send":
        user = get_user_by_id(user_id)
        if not user:
            flash("User not found. Please log in again.", "danger")
            return redirect(url_for("login"))

        if not (user.get("gmail_token") or "").strip():
            flash("Gmail not connected. Go to Settings and connect Gmail first.", "danger")
            return redirect(url_for("dashboard"))

        sent = 0
        failed = 0

        for fid in ids:
            f = get_followup(fid, user_id)
            if not f:
                failed += 1
                continue

            if f.get("status") in ("done", "replied"):
                # already handled; skip silently
                continue

            to_email = (f.get("email") or "").strip()
            if not to_email:
                failed += 1
                mark_send_failed(fid, user_id, "Missing email")
                continue

            subject = f"Follow-up: {f.get('followup_type') or 'follow-up'}"
            message = (f.get("message_override") or "").strip() or build_message_preview(f, user_id)

            mark_send_attempt(fid, user_id)
            try:
                send_email(user, to_email, subject, message)
                mark_send_success(fid, user_id)
                update_chase_stage(fid, user_id)
                add_notification(user_id, f"Sent email to {f.get('client_name', '')}")
                sent += 1
            except Exception as e:
                mark_send_failed(fid, user_id, str(e))
                failed += 1

        flash(
            f"Bulk send complete ✅ Sent {sent}, Failed {failed}.",
            "success" if sent else "warning",
        )
        return redirect(url_for("dashboard"))

    flash("Unknown bulk action.", "danger")
    return redirect(url_for("dashboard"))




from models_saas import add_followup_draft
@app.post("/followups/draft")
def add_followup_draft_route():
    from flask import session, jsonify

    user_id = int(session.get("user_id") or 0)
    if not user_id:
        return jsonify({"ok": False, "error": "not_logged_in"}), 401

    client_name = (request.form.get("client_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    followup_type = (request.form.get("followup_type") or "").strip()
    description = (request.form.get("description") or "").strip()

    if not client_name or not email or not followup_type:
        return jsonify({"ok": False, "error": "missing_required"}), 400

    try:
        fid = add_followup_draft(
            user_id=user_id,
            client_name=client_name,
            email=email,
            followup_type=followup_type,
            description=description,
            preferred_channel="email",
        )
        return jsonify({"ok": True, "id": fid})
    except Exception as e:
        current_app.logger.exception("Draft create failed")
        return jsonify({"ok": False, "error": str(e)}), 400


@app.post("/billing/portal")
def billing_portal():
    # TODO: create Stripe billing portal session + redirect
    # return redirect(portal_url)
    return redirect(url_for("billing"))


from datetime import datetime, timezone
from flask import request, redirect, url_for, flash, session

PUBLIC_PATH_PREFIXES = (
    "/static",
    "/login",
    "/register",
    "/logout",
    "/verify",                 # email verify page
    "/forgot",                 # ✅ covers /forgot-password and /forgot_password
    "/reset",                  # ✅ covers /reset-password and /reset_password
    "/auth/google",
    "/stripe/webhook",
    "/webhooks/paystack",
)

@app.before_request
def billing_gate():
    path = request.path or "/"

    # allow public paths
    for p in PUBLIC_PATH_PREFIXES:
        if path.startswith(p):
            return None

    # must be logged in (auth gate handles this too, but safe)
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login"))

    user = get_user_by_id(int(uid))
    if not user:
        session.clear()
        return redirect(url_for("login"))

    if _has_access(user):
        return None

    flash("Your trial ended. Subscribe to continue.", "danger")
    return redirect(url_for("billing"))




BILLING_OPEN_ENDPOINTS = {
    "login",
    "register",
    "logout",

    "verify_email",
    "verify_email_submit",
    "verify_email_resend",

    "auth_google",
    "auth_google_callback",

    "forgot_password",
    "forgot_password_verify",
    "reset_password_submit",
    "reset_password",

    "static",
}

OPEN_ENDPOINTS = {
    "login", "register", "logout",
    "verify_email", "verify_email_submit", "verify_email_resend",
    "auth_google", "auth_google_callback",
    "forgot_password", "forgot_password_verify",
    "reset_password_submit",      # ✅ add this
    "reset_password",             # ✅ if you have a GET page
    "static",
}

# @app.before_request
# def block_unverified_users():
#     endpoint = request.endpoint or ""
#     if endpoint in OPEN_ENDPOINTS:
#         return None

#     uid = session.get("user_id")
#     if not uid:
#         return None  # let auth guard handle it

#     user = get_user_by_id(int(uid))
#     if not user:
#         session.clear()
#         return redirect(url_for("login"))

#     if int(user.get("email_verified") or 0) != 1:
#         flash("Verify your email to continue.", "danger")
#         return redirect(url_for("verify_email"))

#     return None


import stripe
from flask import request, abort

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

@app.post("/stripe/webhook")
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception:
        return abort(400)

    etype = event["type"]
    obj = event["data"]["object"]

    # 1) Checkout completed: attach customer/subscription to user
    if etype == "checkout.session.completed":
        user_id = (obj.get("metadata") or {}).get("user_id")
        if user_id:
            stripe_customer_id = obj.get("customer")
            stripe_subscription_id = obj.get("subscription")
            _set_user_subscription_ids(
                int(user_id),
                stripe_customer_id,
                stripe_subscription_id,
            )

    # 2) Subscription updates: turn access on/off
    if etype in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"):
        sub = obj
        customer_id = sub.get("customer")
        status = (sub.get("status") or "").lower()   # active, trialing, past_due, canceled, unpaid...
        sub_id = sub.get("id")

        uid = _find_user_id_by_customer(customer_id)
        if uid:
            active = 1 if status in ("active", "trialing") else 0
            _update_subscription_state(int(uid), active, sub_id, status)

    return {"ok": True}



@app.context_processor
def inject_globals():
    uid = session.get("user_id")
    user = get_user_by_id(uid) if uid else None

    if not user:
        branding = {"color": "#36A2EB", "logo": url_for("static", filename="logo.png")}
        is_admin = False
    else:
        logo = (user.get("brand_logo") or "").strip() or url_for("static", filename="logo.png")
        branding = {
            "color": (user.get("brand_color") or "#36A2EB").strip() or "#36A2EB",
            "logo": logo,
        }
        is_admin = (user.get("email") or "").strip().lower() == ADMIN_EMAIL

    raw_items = [
        ("Dashboard", "dashboard", "🏠"),
        ("Add Follow-up", "add", "➕"),
        ("Schedule", "schedule", "📅"),
        ("Templates", "templates", "🧩"),
        ("Settings", "settings", "⚙️"),
        ("Analytics", "analytics", "📊"),
        ("Branding", "branding", "🎨"),
        ("Email Templates", "email_templates", "✉️"),
        ("Billing", "billing", "💳"),
        ("Admin", "admin", "🛡️"),
        ("Logout", "logout", "🚪"),
    ]

    nav_items = []
    for label, endpoint, icon in raw_items:
        if endpoint == "admin" and not is_admin:
            continue
        if _endpoint_exists(endpoint):
            nav_items.append({
                "label": label,
                "endpoint": endpoint,
                "icon": icon,
                "active": (request.endpoint == endpoint),
            })

    return {
        "branding": branding,
        "nav_items": nav_items,
        "is_admin": is_admin,
        "current_user": user,
    }


def send_email(user: dict, to_email: str, subject: str, body_html: str) -> None:
    msg_id = send_email_gmail(user, to_email, subject, body_html)
    current_app.logger.warning(f"[GMAIL] sent message id={msg_id}")

def _utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()

# -----------------------------
# AUTH
# -----------------------------
from datetime import datetime, timedelta
from flask import request, render_template, flash, redirect, url_for, session, current_app
from werkzeug.security import generate_password_hash

def _utc_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat()

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password required.", "danger")
            return render_template("register.html")

        # don’t allow duplicates
        existing = get_user_by_email(email)
        if existing:
            flash("Email already registered.", "danger")
            return redirect(url_for("login"))

        pw_hash = generate_password_hash(password)
        now = _utc_iso()
        trial_end = (datetime.utcnow() + timedelta(days=14)).replace(microsecond=0).isoformat()

        conn = get_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO users (
                name, email, password_hash,
                created_at, trial_start, trial_end,
                email_verified
            )
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (name or email.split("@")[0], email, pw_hash, now, now, trial_end),
        )
        conn.commit()
        uid = c.lastrowid
        conn.close()

        # store pending verification
        session["pending_verify_user_id"] = int(uid)

        try:
            # NOTE: this assumes your new send_verification_code signature is (user_id, email)
            send_verification_code(int(uid), email)
        except Exception:
            current_app.logger.exception("Verification email failed")
            flash("Could not send verification email. Check SMTP settings.", "danger")
            return redirect(url_for("register"))

        flash("Verification code sent. Check your email.", "success")
        return redirect(url_for("verify_email"))

    return render_template("register.html")



# @app.route("/verify-email", methods=["GET", "POST"])
# def verify_email():
#     uid = session.get("pending_verify_user_id")
#     if not uid:
#         flash("No verification in progress.", "danger")
#         return redirect(url_for("login"))

#     if request.method == "POST":
#         code = (request.form.get("otp") or "").strip()

#         conn = get_connection()
#         conn.row_factory = sqlite3.Row
#         c = conn.cursor()
#         c.execute("SELECT email_verify_code, email_verify_expires FROM users WHERE id=?", (int(uid),))
#         row = c.fetchone()

#         if not row:
#             conn.close()
#             flash("User not found.", "danger")
#             return redirect(url_for("login"))

#         saved = (row["email_verify_code"] or "").strip()
#         exp = (row["email_verify_expires"] or "").strip()
#         conn.close()

#         if not saved or code != saved:
#             flash("Invalid code.", "danger")
#             return render_template("verify_email.html")

#         try:
#             exp_dt = datetime.fromisoformat(exp)
#         except Exception:
#             exp_dt = datetime.utcnow() - timedelta(seconds=1)

#         if datetime.utcnow() > exp_dt:
#             flash("Code expired. Request a new one.", "danger")
#             return redirect(url_for("resend_verification"))

#         conn = get_connection()
#         c = conn.cursor()
#         c.execute("""
#             UPDATE users
#             SET email_verified=1, email_verify_code=NULL, email_verify_expires=NULL
#             WHERE id=?
#         """, (int(uid),))
#         conn.commit()
#         conn.close()

#         session.pop("pending_verify_user_id", None)
#         session["user_id"] = int(uid)

#         flash("Email verified ✅", "success")
#         return redirect(url_for("dashboard"))

#     return render_template("verify_email.html")


from flask import redirect, url_for, session, flash, request
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import secrets

import secrets
from flask import session, url_for

@app.get("/auth/google")
def auth_google():
    session.pop("google_oauth_done", None)
    redirect_uri = url_for("auth_google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

from flask import redirect, url_for, session, flash

from authlib.integrations.base_client.errors import OAuthError
from datetime import datetime, timedelta
from flask import redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
import secrets

from datetime import datetime, timedelta
import secrets
from werkzeug.security import generate_password_hash

from datetime import datetime

@app.get("/auth/google/callback")
def auth_google_callback():
    # guard against duplicate callback hits
    if session.get("google_oauth_done"):
        return redirect(url_for("dashboard"))

    try:
        oauth.google.authorize_access_token()
    except OAuthError as e:
        session.pop("google_oauth_done", None)
        flash(f"Google OAuth failed: {getattr(e, 'error', 'oauth_error')}", "danger")
        return redirect(url_for("login"))

    # fetch user profile
    resp = oauth.google.get("https://openidconnect.googleapis.com/v1/userinfo")
    userinfo = resp.json() if resp else {}

    email = (userinfo.get("email") or "").strip().lower()
    name = (userinfo.get("name") or (email.split("@")[0] if email else "User")).strip()

    if not email:
        session.pop("google_oauth_done", None)
        flash("Google login failed (missing email).", "danger")
        return redirect(url_for("login"))

    existing = get_user_by_email(email)
    if existing:
        uid = int(existing["id"])
    else:
        uid = int(create_user(
            name,
            email,
            generate_password_hash(secrets.token_urlsafe(32)),
        ))

    # ✅ IMPORTANT: mark Google users as verified in DB
    now = datetime.utcnow().replace(microsecond=0).isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET email_verified=1,
            email_verified_at=COALESCE(email_verified_at, ?),
            email_verify_code=NULL,
            email_verify_expires_at=NULL
        WHERE id=?
    """, (now, uid))
    conn.commit()
    conn.close()

    # ✅ IMPORTANT: clear anything that forces verify flow
    session.pop("pending_verify_user_id", None)

    session["google_oauth_done"] = True
    session["user_id"] = uid
    flash("Logged in with Google ✅", "success")
    return redirect(url_for("dashboard"))




@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email + password required.", "danger")
            return render_template("signup.html")

        conn = dict_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE lower(email)=?", (email,))
        exists = c.fetchone()
        if exists:
            conn.close()
            flash("Account already exists. Login instead.", "danger")
            return redirect(url_for("login"))

        now = datetime.utcnow().isoformat()
        trial_end = (datetime.utcnow() + timedelta(days=14)).isoformat()
        pw_hash = generate_password_hash(password)

        if not name:
            name = email.split("@")[0] or "User"

        c.execute("""
            INSERT INTO users (name, email, password_hash, created_at, trial_start, trial_end, email_verified)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (name, email, pw_hash, now, now, trial_end))
        conn.commit()
        user_id = c.lastrowid
        conn.close()

        # send verify code
        code = _make_6digit_code()
        _store_email_verify_code(user_id, code, minutes=15)
        _send_verify_code_email(email, code)

        flash("Verification code sent. Check your inbox.", "success")
        return redirect(url_for("verify_email", email=email))

    return render_template("signup.html")



import random
from werkzeug.security import generate_password_hash, check_password_hash

def _make_6digit_code() -> str:
    return f"{random.randint(0, 999999):06d}"

def _store_email_verify_code(user_id: int, code: str, minutes: int = 15):
    expires = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()
    code_hash = generate_password_hash(code)

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET email_verify_code_hash=?, email_verify_expires_at=?
        WHERE id=?
    """, (code_hash, expires, int(user_id)))
    conn.commit()
    conn.close()

def _send_verify_code_email(to_email: str, code: str):
    send_email_smtp(
        to_email,
        "Your verification code",
        f"Your verification code is: {code}\n\nExpires in 15 minutes."
    )

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def send_email_smtp(to_email, subject, body_text, body_html=None):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")

    if not all([host, port, user, password]):
        raise RuntimeError("SMTP credentials not configured")

    msg = MIMEMultipart("alternative")
    msg["From"] = user
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body_text, "plain"))

    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    # 🔒 SSL — REQUIRED
    with smtplib.SMTP_SSL(host, port, timeout=30) as server:
        server.login(user, password)
        server.sendmail(user, to_email, msg.as_string())


# def send_email_smtp(to_email: str, subject: str, body_text: str, body_html: str | None = None) -> None:
#     host = os.getenv("SMTP_HOST", "smtp.gmail.com")
#     port = int(os.getenv("SMTP_PORT", "465"))
#     user = os.getenv("SMTP_USER")
#     pw = os.getenv("SMTP_PASS")

#     if not user or not pw:
#         raise RuntimeError("SMTP_USER / SMTP_PASS not set")

#     msg = MIMEMultipart("alternative")
#     msg["From"] = user
#     msg["To"] = to_email
#     msg["Subject"] = subject

#     msg.attach(MIMEText(body_text or "", "plain", "utf-8"))
#     if body_html:
#         msg.attach(MIMEText(body_html, "html", "utf-8"))

#     import smtplib, ssl
#     context = ssl.create_default_context()
#     with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
#         server.login(user, pw)
#         server.sendmail(user, [to_email], msg.as_string())


@app.route("/preview/<int:fid>/reset", methods=["POST"])
def preview_reset(fid):
    user, block = require_user()
    if block:
        return block

    ok = update_followup_message_override(fid, user["id"], None)
    flash("Message reset ✅" if ok else "Could not reset message.", "success" if ok else "danger")
    return redirect(url_for("preview", fid=fid))


def build_verify_email_html(code: str, app_name: str, support_email: str | None = None) -> str:
    support = support_email or "followuptracker.mail@gmail.com"

    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f7fb;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f7fb;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;">
            <tr>
              <td style="padding:20px 24px;background:#0b1220;color:#fff;font-family:Arial,sans-serif;">
                <div style="font-size:16px;font-weight:700;">{app_name}</div>
                <div style="opacity:.8;font-size:12px;margin-top:4px;">Email verification</div>
              </td>
            </tr>

            <tr>
              <td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a;">
                <h2 style="margin:0 0 10px 0;font-size:18px;">Verify your email</h2>
                <p style="margin:0 0 14px 0;font-size:14px;line-height:1.5;color:#334155;">
                  Use the code below to finish signing in. This code expires soon.
                </p>

                <div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:12px;padding:16px;text-align:center;">
                  <div style="font-size:28px;letter-spacing:6px;font-weight:800;color:#0f172a;">{code}</div>
                </div>

                <p style="margin:14px 0 0 0;font-size:12px;line-height:1.5;color:#64748b;">
                  If you didn’t request this, you can ignore this email.
                </p>
              </td>
            </tr>

            <tr>
              <td style="padding:16px 24px;background:#f8fafc;border-top:1px solid #e5e7eb;font-family:Arial,sans-serif;">
                <div style="font-size:12px;color:#64748b;">
                  Need help? Contact <a href="mailto:{support}" style="color:#0f172a;text-decoration:underline;">{support}</a>
                </div>
              </td>
            </tr>
          </table>

          <div style="width:600px;text-align:center;font-family:Arial,sans-serif;color:#94a3b8;font-size:11px;margin-top:10px;">
            © {app_name}. All rights reserved.
          </div>
        </td>
      </tr>
    </table>
  </body>
</html>
"""






@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = dict_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE lower(email)=?", (email,))
        user = c.fetchone()
        conn.close()

        if not user:
            flash("Invalid email or password", "danger")
            return render_template("login.html")

        user = dict(user)
        if not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password", "danger")
            return render_template("login.html")

        # 👇 email not verified? stop them here
        if int(user.get("email_verified") or 0) != 1:
            session["pending_verify_user_id"] = user["id"]
            flash("Verify your email to continue.", "danger")
            return redirect(url_for("verify_email"))

        # ✅ verified → log them in
        session["user_id"] = user["id"]
        flash("Welcome back!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("login"))

        user = get_user_by_id(int(uid))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        if int(user.get("email_verified") or 0) != 1:
            session["pending_verify_user_id"] = int(uid)
            flash("Verify your email to continue.", "danger")
            return redirect(url_for("verify_email"))

        return view(*args, **kwargs)
    return wrapper



@app.route("/logout", endpoint="logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("login"))


# -----------------------------
# DASHBOARD
# -----------------------------
@app.route("/")
def dashboard():
    user, block = require_user()
    if block:
        return block

    followups = get_user_followups(user["id"])
    done = count_done(user["id"])
    return render_template("dashboard.html", due_soon=followups, done=done)


# -----------------------------
# FOLLOWUPS (EMAIL ONLY)
# -----------------------------
@app.route("/add", methods=["GET", "POST"])
def add():
    user, block = require_user()
    if block:
        return block
    if request.method == "POST":
        due_date_raw = (request.form.get("due_date") or "").strip()

        # ✅ If no due_date yet, create a draft and send user to Schedule
        if not due_date_raw:
            try:
                fid = add_followup_draft(
                    user_id=int(user["id"]),
                    client_name=(request.form.get("client_name") or "").strip(),
                    email=(request.form.get("email") or "").strip(),
                    followup_type=(request.form.get("followup_type") or "other").strip(),
                    description=(request.form.get("description") or "").strip(),
                    preferred_channel="email",
                )

                msg_override = (request.form.get("message_override") or "").strip()
                if msg_override:
                    update_followup_message_override(int(fid), int(user["id"]), msg_override)

                flash("Draft created. Now set the schedule ✅", "success")
                return redirect(url_for("schedule", fid=fid))

            except Exception as e:
                current_app.logger.exception("Draft create failed")
                flash(f"Add failed: {str(e)}", "danger")
                return render_template("add.html", f={})

        # ✅ Normal flow: due_date is present
        due_date, err = parse_yyyy_mm_dd(due_date_raw)
        if err:
            flash(err, "danger")
            return render_template("add.html", f={})

        try:
            fid = add_followup(
                user_id=int(user["id"]),
                client_name=(request.form.get("client_name") or "").strip(),
                email=(request.form.get("email") or "").strip(),
                followup_type=(request.form.get("followup_type") or "other").strip(),
                description=(request.form.get("description") or "").strip(),
                due_date=due_date,
                recurring_interval=int(request.form.get("recurring_interval", 0) or 0),
            )

            msg_override = (request.form.get("message_override") or "").strip()
            if msg_override:
                update_followup_message_override(int(fid), int(user["id"]), msg_override)

        except Exception as e:
            current_app.logger.exception("Add follow-up failed")
            flash(f"Add failed: {str(e)}", "danger")
            return render_template("add.html", f={})

        flash("Follow-up added ✅", "success")
        return redirect(url_for("dashboard"))

    return render_template("add.html", f={})


# @app.post("/schedule/<int:fid>/set")
# def schedule_set(fid):
#     user, block = require_user()
#     if block:
#         return block

#     start_date = (request.form.get("start_date") or "").strip() or None
#     end_date = (request.form.get("end_date") or "").strip() or None
#     send_time = (request.form.get("send_time") or "09:00").strip()
#     send_time_2 = (request.form.get("send_time_2") or "").strip() or None
#     repeat = (request.form.get("repeat") or "once").strip().lower()
#     interval = int(request.form.get("interval") or 1)
#     byweekday = ",".join([x.strip().upper() for x in request.form.getlist("byweekday") if x.strip()]) or None

#     scheduled_for_raw = (request.form.get("scheduled_for") or "").strip()
#     next_send_at = (scheduled_for_raw + ":00") if scheduled_for_raw and len(scheduled_for_raw) == 16 else (scheduled_for_raw or None)

#     if not next_send_at:
#         if not start_date:
#             flash("Pick a start date.", "danger")
#             return redirect(url_for("schedule"))
#         next_send_at = f"{start_date}T{send_time}:00"

#     rule = {
#         "schedule_enabled": 1,
#         "schedule_repeat": repeat,
#         "schedule_start_date": start_date,
#         "schedule_end_date": end_date,
#         "schedule_send_time": send_time,
#         "schedule_send_time_2": send_time_2,
#         "schedule_interval": interval,
#         "schedule_byweekday": byweekday,
#         "schedule_rel_value": request.form.get("rel_value"),
#         "schedule_rel_unit": request.form.get("rel_unit"),
#         "next_send_at": next_send_at,
#     }

#     ok = set_followup_schedule_rule(fid, user["id"], rule)

#     flash("Scheduled ✅" if ok else "Schedule failed.", "success" if ok else "danger")
#     return redirect(url_for("schedule"))

@app.route("/forgot-password", methods=["GET", "POST"])
@app.route("/forgot_password", methods=["GET", "POST"]) 
def forgot_password():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if not email:
            flash("Enter your email.", "danger")
            return redirect(url_for("forgot_password"))

        user = get_user_by_email(email)
        if not user:
            # don’t leak existence
            session["reset_uid"] = None
            session["reset_email"] = email
            flash("If the email exists, a reset code was sent.", "success")
            return redirect(url_for("forgot_password_verify"))

        try:
            send_password_reset_code(user["id"], email)
        except Exception:
            flash("Could not send reset email. Check SMTP.", "danger")
            return redirect(url_for("forgot_password"))

        session["reset_uid"] = user["id"]
        flash("Reset code sent. Check your email.", "success")
        return redirect(url_for("forgot_password_verify"))

    return render_template("forgot_password.html")


def send_password_reset_code(uid: int, email: str):
    code = gen_otp6()
    now = datetime.utcnow()
    expires = now + timedelta(minutes=15)

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET password_reset_code=?,
            password_reset_expires_at=?
        WHERE id=?
    """, (code, expires.isoformat(), uid))
    conn.commit()
    conn.close()

    subject = "Reset your password"
    html = f"""
    <div style="font-family:Arial,sans-serif">
      <h2>Password reset</h2>
      <p>Your verification code is:</p>
      <h1 style="letter-spacing:4px">{code}</h1>
      <p>This code expires in 15 minutes.</p>
    </div>
    """

    send_email_smtp(
        to_email=email,
        subject=subject,
        body_text=f"Your password reset code is {code}",
        body_html=html,
    )


def require_user_fresh():
    uid = session.get("user_id")
    if not uid:
        flash("Please log in.", "warning")
        return None, redirect(url_for("login"))

    user = get_user_by_id(int(uid))
    if not user:
        session.clear()
        flash("Session expired. Login again.", "warning")
        return None, redirect(url_for("login"))

    return user, None


@app.route("/forgot-password/verify", methods=["GET", "POST"])
def forgot_password_verify():
    uid = session.get("reset_uid")
    if not uid:
        return redirect(url_for("forgot_password"))

    user = get_user_by_id(int(uid))
    if not user:
        session.pop("reset_uid", None)
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        code = (request.form.get("otp") or "").strip()

        saved = (user.get("password_reset_code") or "").strip()
        exp = (user.get("password_reset_expires_at") or "").strip()

        if not saved or not exp:
            flash("No active reset code.", "danger")
            return redirect(url_for("forgot_password"))

        try:
            exp_dt = datetime.fromisoformat(exp)
        except Exception:
            exp_dt = datetime.utcnow() - timedelta(days=1)

        if datetime.utcnow() > exp_dt:
            flash("Code expired. Request a new one.", "danger")
            return redirect(url_for("forgot_password"))

        if code != saved:
            flash("Invalid code.", "danger")
            return redirect(url_for("forgot_password_verify"))

        session["reset_ok"] = True
        return redirect(url_for("reset_password_submit"))  # ✅ GET page

    return render_template("forgot_password_verify.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password_submit():
    # must come from successful OTP verify
    if not session.get("reset_ok"):
        flash("Verify the reset code first.", "danger")
        return redirect(url_for("forgot_password_verify"))

    uid = session.get("reset_uid")
    if not uid:
        flash("Reset session expired. Start again.", "danger")
        return redirect(url_for("forgot_password"))

    user = get_user_by_id(int(uid))
    if not user:
        flash("Reset session expired. Start again.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        p1 = request.form.get("password") or ""
        p2 = request.form.get("confirm_password") or ""

        if len(p1) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("reset_password_submit"))

        if p1 != p2:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("reset_password_submit"))

        pw_hash = generate_password_hash(p1)

        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE users
            SET password_hash=?,
                password_reset_code=NULL,
                password_reset_expires_at=NULL
            WHERE id=?
        """, (pw_hash, int(uid)))
        conn.commit()
        conn.close()

        # cleanup reset session
        session.pop("reset_ok", None)
        session.pop("reset_uid", None)

        flash("Password reset successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")



@app.get("/reset-password")
def reset_password():
    print("RESET PAGE HIT. endpoint=", request.endpoint, "path=", request.path, "uid=", session.get("user_id"))
    if not session.get("reset_uid"):
        return redirect(url_for("forgot_password"))
    if not session.get("reset_ok"):
        return redirect(url_for("forgot_password_verify"))

    return render_template("reset_password.html")



@app.route("/forgot-password/new", methods=["GET", "POST"])
def forgot_password_new():
    if not session.get("reset_ok"):
        return redirect(url_for("forgot_password"))

    uid = session.get("reset_uid")
    user = get_user_by_id(uid)
    if not user:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        pw = request.form.get("password")
        if not pw or len(pw) < 6:
            flash("Password too short.", "danger")
            return redirect(url_for("forgot_password_new"))

        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE users
            SET password_hash=?,
                password_reset_code=NULL,
                password_reset_expires_at=NULL
            WHERE id=?
        """, (generate_password_hash(pw), uid))
        conn.commit()
        conn.close()

        session.clear()
        flash("Password reset successful. Login now.", "success")
        return redirect(url_for("login"))

    return render_template("forgot_password_new.html")



@app.route("/edit/<int:fid>", methods=["GET", "POST"])
def edit_followup(fid):
    user, block = require_user()
    if block:
        return block

    f = get_followup(fid, user["id"])
    if not f:
        flash("Follow-up not found.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        due_date, err = parse_yyyy_mm_dd(request.form.get("due_date"))
        if err:
            flash(err, "danger")
            return render_template("edit.html", f=f)

        try:
            ok = update_followup(
                fid=fid,
                user_id=user["id"],
                client_name=(request.form.get("client_name") or "").strip(),
                email=(request.form.get("email") or "").strip(),
                followup_type=(request.form.get("followup_type") or "other").strip(),
                description=(request.form.get("description") or "").strip(),
                due_date=due_date,
            )
        except Exception as e:
            flash(str(e), "danger")
            return render_template("edit.html", f=f)

        if not ok:
            flash("Update failed (not found).", "danger")
            return redirect(url_for("dashboard"))

        msg_override = (request.form.get("message_override") or "").strip()
        update_followup_message_override(fid, user["id"], msg_override if msg_override else None)

        flash("Follow-up updated ✅", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit.html", f=f)


@app.route("/delete/<int:fid>", methods=["POST"], endpoint="delete_followup")
def delete_followup_route(fid):
    user, block = require_user()
    if block:
        return block
    ok = delete_followup(fid, user["id"])
    flash("Follow-up deleted." if ok else "Delete failed.", "success" if ok else "danger")
    return redirect(url_for("dashboard"))


@app.route("/done/<int:fid>")
def done(fid):
    user, block = require_user()
    if block:
        return block
    ok = mark_followup_done_by_id(fid, user["id"])
    flash("Marked as done ✅" if ok else "Not found.", "success" if ok else "danger")
    return redirect(url_for("dashboard"))


@app.route("/replied/<int:fid>", methods=["POST"])
def mark_replied(fid):
    user, block = require_user()
    if block:
        return block
    ok = mark_followup_replied(fid, user["id"])
    flash("Marked as replied ✅" if ok else "Not found.", "success" if ok else "danger")
    return redirect(url_for("dashboard"))


# -----------------------------
# PREVIEW + SEND (EMAIL ONLY)
# -----------------------------
@app.route("/preview/<int:fid>", methods=["GET"])
def preview(fid):
    user, block = require_user()
    if block:
        return block

    followup = get_followup(fid, user["id"])
    if not followup:
        abort(404)

    message = build_message_preview(followup, user["id"])
    override = (followup.get("message_override") or "").strip()
    if override:
        message = override

    return render_template("preview.html", followup=followup, message=message)


@app.route("/send/<int:fid>", methods=["POST"])
def send_followup(fid):
    user, block = require_user()
    if block:
        return block

    f = get_followup(fid, user["id"])
    if not f:
        flash("Follow-up not found.", "danger")
        return redirect(url_for("dashboard"))

    # 🔒 prevent manual send if scheduled
    if int(f.get("schedule_enabled") or 0) == 1 and (f.get("next_send_at") or "").strip():
        flash(
            "This follow-up is scheduled. Clear the schedule before sending manually.",
            "warning",
        )
        return redirect(url_for("schedule"))

    if f.get("status") in ("done", "replied"):
        flash(f"Not sent. This follow-up is already {f['status']}.", "warning")
        return redirect(url_for("dashboard"))

    message = (f.get("message_override") or "").strip() or build_message_preview(
        f, user["id"]
    )
    subject = f"Follow-up: {f.get('followup_type') or 'follow-up'}"

    mark_send_attempt(fid, user["id"])

    try:
        if not (user.get("gmail_token") or "").strip():
            raise RuntimeError("Gmail not connected")

        send_email(
            user,
            (f.get("email") or "").strip(),
            subject,
            message,
        )

        mark_send_success(fid, user["id"])
        update_chase_stage(fid, user["id"])
        add_notification(user["id"], f"Sent email to {f.get('client_name','')}")
        flash("Email sent ✅", "success")
        return redirect(url_for("dashboard"))

    except Exception as e:
        mark_send_failed(fid, user["id"], str(e))
        current_app.logger.exception("Send failed")
        flash(f"Send failed: {str(e)}", "danger")
        return redirect(url_for("dashboard"))

# -----------------------------
# SCHEDULE (RULE-BASED)
# -----------------------------
@app.route("/schedule")
def schedule():
    user, block = require_user()
    if block:
        return block

    followups = get_user_followups(user["id"])
    scheduler = get_scheduler_settings(user["id"])
    return render_template("schedule.html", followups=followups, scheduler=scheduler)


def _iso_local_picker(dt: str) -> str:
    dt = (dt or "").strip()
    if not dt:
        return ""
    return dt + ":00" if len(dt) == 16 else dt


@app.post("/schedule/set")
def schedule_set():
    user, block = require_user()
    if block:
        return block

    fid = int(request.form.get("fid") or 0)
    if not fid:
        flash("Missing followup id.", "danger")
        return redirect(url_for("schedule"))

    start_date = (request.form.get("start_date") or "").strip()
    send_time = (request.form.get("send_time") or "09:00").strip()
    repeat = (request.form.get("repeat") or "once").strip().lower()

    if not start_date:
        flash("Start date is required.", "danger")
        return redirect(url_for("schedule"))

    # if frontend sends a direct datetime picker value (optional)
    scheduled_for_raw = (request.form.get("scheduled_for") or "").strip()
    if scheduled_for_raw:
        next_send_at = scheduled_for_raw + ":00" if len(scheduled_for_raw) == 16 else scheduled_for_raw
    else:
        next_send_at = f"{start_date}T{send_time}:00"

    rule = {
        "schedule_enabled": 1,
        "schedule_repeat": repeat,
        "schedule_start_date": start_date,
        "schedule_end_date": (request.form.get("end_date") or "").strip() or None,
        "schedule_send_time": send_time,
        "schedule_send_time_2": (request.form.get("send_time_2") or "").strip() or None,
        "schedule_interval": int(request.form.get("interval") or 1),
        "schedule_byweekday": ",".join(request.form.getlist("byweekday")) or None,
        "schedule_rel_value": request.form.get("rel_value"),
        "schedule_rel_unit": request.form.get("rel_unit"),
        "next_send_at": next_send_at,
        "scheduled_for": next_send_at,
        "scheduled_at": datetime.now().isoformat(timespec="seconds"),
    }

    try:
        ok = set_followup_schedule_rule(fid, user["id"], rule)
        if not ok:
            flash("Could not schedule this follow-up (not found).", "danger")
        else:
            flash("Scheduled ✅", "success")
    except ValueError as e:
        # 🔥 This is where your 'sent cannot be scheduled' message shows
        flash(str(e), "warning")

    return redirect(url_for("schedule"))



# @app.post("/schedule/<int:fid>/set")
# def schedule_set(fid):
#     user, block = require_user()
#     if block:
#         return block

#     start_date = (request.form.get("start_date") or "").strip() or None
#     end_date = (request.form.get("end_date") or "").strip() or None
#     send_time = (request.form.get("send_time") or "09:00").strip()
#     send_time_2 = (request.form.get("send_time_2") or "").strip() or None
#     repeat = (request.form.get("repeat") or "once").strip().lower()
#     interval = int(request.form.get("interval") or 1)
#     byweekday_list = request.form.getlist("byweekday")
#     byweekday = ",".join([x.strip().upper() for x in byweekday_list if x.strip()]) or None

#     scheduled_for_raw = (request.form.get("scheduled_for") or "").strip()
#     next_send_at = _iso_local_picker(scheduled_for_raw) if scheduled_for_raw else None

#     if not next_send_at:
#         if not start_date or not send_time:
#             flash("Pick start date + send time.", "danger")
#             return redirect(url_for("schedule"))
#         next_send_at = f"{start_date}T{send_time}:00"

#     ok = set_followup_schedule(
#         fid, user["id"],
#         enabled=1,
#         start_date=start_date,
#         end_date=end_date,
#         send_time=send_time,
#         send_time_2=send_time_2,
#         repeat=repeat,
#         interval=interval,
#         byweekday=byweekday,
#         next_send_at=next_send_at,
#     )

#     flash("Scheduled ✅" if ok else "Schedule failed.", "success" if ok else "danger")
#     return redirect(url_for("schedule"))


@app.post("/schedule/<int:fid>/clear")
def schedule_clear(fid):
    user, block = require_user()
    if block:
        return block
    ok = clear_followup_schedule(fid, user["id"])
    flash("Schedule cleared ✅" if ok else "Clear failed.", "success" if ok else "danger")
    return redirect(url_for("schedule"))

import os
from models_saas import DB_PATH

# @app.post("/schedule/bulk")
# def bulk_schedule():
#     user, block = require_user()
#     if block:
#         return block

#     ids = request.form.getlist("followup_ids")
#     ids = [int(x) for x in ids if str(x).isdigit()]
#     if not ids:
#         flash("Select followups first.", "danger")
#         return redirect(url_for("schedule"))

#     start_date = (request.form.get("start_date") or "").strip()
#     send_time = (request.form.get("send_time") or "09:00").strip()
#     repeat = (request.form.get("repeat") or "once").strip().lower()

#     if not start_date:
#         flash("Start date is required.", "danger")
#         return redirect(url_for("schedule"))

#     scheduled_for_raw = (request.form.get("scheduled_for") or "").strip()
#     if scheduled_for_raw:
#         next_send_at = scheduled_for_raw + ":00" if len(scheduled_for_raw) == 16 else scheduled_for_raw
#     else:
#         next_send_at = f"{start_date}T{send_time}:00"

#     rule = {
#         "schedule_enabled": 1,
#         "schedule_repeat": repeat,
#         "schedule_start_date": start_date,
#         "schedule_end_date": (request.form.get("end_date") or "").strip() or None,
#         "schedule_send_time": send_time,
#         "schedule_send_time_2": (request.form.get("send_time_2") or "").strip() or None,
#         "schedule_interval": int(request.form.get("interval") or 1),
#         "schedule_byweekday": ",".join(request.form.getlist("byweekday")) or None,
#         "schedule_rel_value": request.form.get("rel_value"),
#         "schedule_rel_unit": request.form.get("rel_unit"),
#         "next_send_at": next_send_at,
#         "scheduled_for": next_send_at,
#         "scheduled_at": datetime.now().isoformat(timespec="seconds"),
#     }

#     n = bulk_set_followup_schedule_rule(user["id"], ids, rule)

#     if n == 0:
#         flash("Nothing scheduled. Sent follow-ups can’t be scheduled again. Use the clear button then rescheduled", "warning")
#     else:
#         flash(f"Scheduled {n} followup(s) ✅", "success")

#     return redirect(url_for("schedule"))
from web.compute_next import compute_next_send_at
@app.post("/schedule/bulk")
def bulk_schedule():
    user, block = require_user()
    if block:
        return block

    ids = request.form.getlist("followup_ids")
    if not ids:
        flash("Select followups first.", "danger")
        return redirect(url_for("schedule"))

    start_date = (request.form.get("start_date") or "").strip()
    send_time = (request.form.get("send_time") or "09:00").strip()
    repeat = (request.form.get("repeat") or "once").strip().lower()

    end_date = (request.form.get("end_date") or "").strip() or None
    send_time_2 = (request.form.get("send_time_2") or "").strip() or None
    interval = int(request.form.get("interval") or 1)
    byweekday = ",".join(request.form.getlist("byweekday")) or None
    rel_value = request.form.get("rel_value")
    rel_unit = request.form.get("rel_unit")

    # ✅ compute next_send_at safely (never in the past)
    try:
        next_send_at = compute_next_send_at(
            start_date=start_date,
            send_time=send_time,
            repeat=repeat,
            rel_value=rel_value,
            rel_unit=rel_unit,
            input_tz="Africa/Lagos",
            send_time_2=send_time_2,
            interval=interval,
            byweekday=byweekday,
        )
    except Exception as e:
        flash(f"Schedule rule error: {type(e).__name__}: {e}", "danger")
        return redirect(url_for("schedule"))

    rule = {
        "schedule_enabled": 1,
        "schedule_repeat": repeat,
        "schedule_start_date": start_date,
        "schedule_end_date": end_date,
        "schedule_send_time": send_time,
        "schedule_send_time_2": send_time_2,
        "schedule_interval": interval,
        "schedule_byweekday": byweekday,
        "schedule_rel_value": rel_value,
        "schedule_rel_unit": rel_unit,
        "next_send_at": next_send_at,
        "scheduled_for": next_send_at,
        "scheduled_at": datetime.now().isoformat(timespec="seconds"),
    }

    n = bulk_set_followup_schedule_rule(user["id"], ids, rule)
    if n <= 0:
        flash("Nothing scheduled. Those follow-ups were already sent.", "warning")
    else:
        flash(f"Scheduled {n} followup(s) ✅", "success")
    return redirect(url_for("schedule"))




@app.post("/scheduler/settings")
def save_scheduler_settings():
    user, block = require_user()
    if block:
        return block

    enabled = 1 if request.form.get("enabled") == "1" else 0
    start_date = (request.form.get("start_date") or "").strip() or None
    end_date = (request.form.get("end_date") or "").strip() or None
    send_time = (request.form.get("send_time") or "09:00").strip()
    mode = (request.form.get("mode") or "both").strip()

    upsert_scheduler_settings(user["id"], enabled, start_date or "", end_date or "", send_time, mode)
    flash("Scheduler settings saved ✅", "success")
    return redirect(url_for("schedule"))


# -----------------------------
# GMAIL CONNECT
# -----------------------------
# @app.route("/gmail/connect")
# def gmail_connect():
#     user, block = require_user()
#     if block:
#         return block

#     flow = Flow.from_client_secrets_file(
#         CREDS_PATH,
#         scopes=SCOPES,
#         redirect_uri=url_for("gmail_callback", _external=True),
#     )

#     auth_url, state = flow.authorization_url(
#         access_type="offline",
#         include_granted_scopes="true",
#         prompt="consent",
#     )

#     session["gmail_oauth_state"] = state
#     return redirect(auth_url)

# routes_gmail.py (or inside app.py)

from google_auth_oauthlib.flow import Flow
from flask import session, redirect, url_for
import os

CLIENT_SECRETS = os.getenv("GOOGLE_CLIENT_SECRETS", "credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]

@app.get("/gmail/connect")
def gmail_connect():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS,
        scopes=SCOPES,
    )

    flow.redirect_uri = os.getenv("APP_BASE_URL") + "/auth/google/callback"

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes=False,  # 🔥 MUST BE FALSE
        prompt="consent",              # 🔥 forces fresh refresh token
    )
    

    session["gmail_oauth_state"] = state
    return redirect(auth_url)


from googleapiclient.discovery import build

def _gmail_get_profile_email(creds) -> str | None:
    try:
        svc = build("gmail", "v1", credentials=creds)
        prof = svc.users().getProfile(userId="me").execute()
        return (prof.get("emailAddress") or "").strip().lower() or None
    except Exception:
        return None


from models_saas import get_user_by_id, save_gmail_email, save_gmail_token

# make sure these exist in your module
# CLIENT_SECRETS = "path/to/client_secret.json"
# GMAIL_SCOPES = [...]
# def _gmail_get_profile_email(creds): ...
# def save_gmail_token(user_id, token_json, gmail_email): ...


from flask import session, redirect, url_for, request, flash
from google_auth_oauthlib.flow import Flow
from google.auth.exceptions import RefreshError

@app.get("/gmail/callback")
def gmail_callback():
    user, block = require_user()
    if block:
        return block

    state = session.get("gmail_oauth_state")
    if not state:
        flash("OAuth state missing. Try again.", "danger")
        return redirect(url_for("settings"))

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS,
        scopes=SCOPES,  # ONLY gmail.send
        state=state,
    )
    # flow.redirect_uri = url_for("gmail_callback", _external=True)
    flow.redirect_uri = os.getenv("APP_BASE_URL") + "/gmail/callback"
    
    try:
        flow.fetch_token(authorization_response=request.url)
    except RefreshError:
        flash("Gmail authorization failed. Please reconnect.", "danger")
        return redirect(url_for("settings"))
    except Exception as e:
        flash(f"Gmail auth failed: {type(e).__name__}", "danger")
        return redirect(url_for("settings"))

    creds = flow.credentials

    if not creds or not creds.refresh_token:
        flash("Failed to obtain Gmail credentials.", "danger")
        return redirect(url_for("settings"))

    # ✅ SAVE TOKEN (THIS is what actually matters)
    save_gmail_token(
        user_id=user["id"],
        token_json=creds.to_json(),
    )

    # ✅ DO NOT TOUCH id_token
    # Just use your app’s user email
    save_gmail_email(user["id"], user["email"])

    flash("Gmail connected ✅", "success")
    return redirect(url_for("settings"))


# @app.route("/gmail/callback")
# def gmail_callback():
#     uid = session.get("user_id")
#     if not uid:
#         flash("Please log in first.", "warning")
#         return redirect(url_for("login"))

#     user = get_user_by_id(int(uid))
#     if not user:
#         session.clear()
#         flash("Session expired. Login again.", "warning")
#         return redirect(url_for("login"))

#     flow = Flow.from_client_secrets_file(
#         CLIENT_SECRETS,
#         scopes=["https://www.googleapis.com/auth/gmail.send"],
#         redirect_uri=url_for("gmail_callback", _external=True),
#     )

#     try:
#         flow.fetch_token(authorization_response=request.url)
#     except Exception as e:
#         flash(f"Gmail auth failed: {type(e).__name__}", "danger")
#         return redirect(url_for("settings"))

#     creds = flow.credentials
#     if not creds or not creds.token:
#         flash("Gmail auth failed: no token returned.", "danger")
#         return redirect(url_for("settings"))

#     # ✅ Store full Google creds JSON string
#     token_json = creds.to_json()

#     conn = get_connection()
#     c = conn.cursor()
#     c.execute("UPDATE users SET gmail_token=? WHERE id=?", (token_json, int(user["id"])))
#     conn.commit()
#     conn.close()

#     # ✅ Verify immediately (your exact debug)
#     u2 = get_user_by_id(int(user["id"]))
#     print("CALLBACK DB gmail_token exists?:", bool(u2.get("gmail_token")))

#     flash("Gmail connected ✅", "success")
#     return redirect(url_for("settings"))


@app.post("/gmail/disconnect")
def gmail_disconnect():
    user, block = require_user_fresh()
    if block:
        return block

    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET gmail_token=NULL WHERE id=?", (int(user["id"]),))
    conn.commit()
    conn.close()

    flash("Gmail disconnected ✅", "success")
    return redirect(url_for("settings"))



# @app.route("/gmail/callback")
# def gmail_callback():
#     user, block = require_user()
#     if block:
#         return block

#     state = session.get("gmail_oauth_state")
#     if not state:
#         flash("OAuth state missing. Try connecting again.", "danger")
#         return redirect(url_for("settings"))

#     flow = Flow.from_client_secrets_file(
#         CREDS_PATH,
#         scopes=SCOPES,
#         state=state,
#         redirect_uri=url_for("gmail_callback", _external=True),
#     )

#     flow.fetch_token(authorization_response=request.url)
#     creds = flow.credentials
#     update_gmail_token(user["id"], creds.to_json())

#     flash("Gmail connected ✅", "success")
#     return redirect(url_for("settings"))





@app.post("/gmail/sync-now")
def gmail_sync_now():
    user, block = require_user()
    if block:
        return block
    try:
        from gmail_sync import check_replies_for_user
        check_replies_for_user(user)
        flash("Checked replies ✅", "success")
    except Exception as e:
        flash(f"Reply check failed: {e}", "danger")
    return redirect(url_for("dashboard"))

@app.route("/login/email", methods=["POST"], endpoint="start_email_login")
def start_email_login():
    email = (request.form.get("email") or "").strip().lower()
    if not email:
        flash("Enter your email.", "danger")
        return redirect(url_for("login"))

    # 🔁 REPLACEMENT BLOCK (this is the change)
    existing = get_user_by_email(email)
    if existing:
        uid = existing["id"]
    else:
        uid = create_user(
            placeholder_name,
            email,
            generate_password_hash(secrets.token_urlsafe(32)),
        )

    otp = str(secrets.randbelow(1000000)).zfill(6)
    expires = datetime.utcnow() + timedelta(minutes=10)

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS email_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            otp TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    c.execute("""
        INSERT INTO email_otps (user_id, otp, expires_at, used, created_at)
        VALUES (?, ?, ?, 0, ?)
    """, (uid, otp, expires.isoformat(), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    current_app.logger.warning(f"[LOGIN OTP] {email} -> {otp}")

    session["pending_email_user_id"] = uid
    flash("We sent a code to your email (check terminal log for now).", "success")
    return redirect(url_for("verify_email_login"))

# -----------------------------
# TEMPLATES / SETTINGS / BRANDING / EMAIL TEMPLATES / ANALYTICS / ADMIN
# -----------------------------
# @app.route("/templates", methods=["GET", "POST"])
# def templates():
#     user, block = require_user()
#     if block:
#         return block

#     uid = user["id"]
#     if request.method == "POST":
#         for stage in range(4):
#             content = request.form.get(f"stage_{stage}")
#             if content is not None:
#                 save_template(uid, stage, content)
#         flash("Templates saved ✅", "success")
#         return redirect(url_for("templates"))

#     return render_template("templates.html", templates=get_templates(uid))


@app.route("/templates/scheduler", methods=["GET", "POST"])
def template_scheduler():
    user, block = require_user()
    if block:
        return block

    from models_saas import get_scheduler_template, save_scheduler_template, get_branding
    from scheduler_render import render_scheduler_html

    uid = user["id"]

    # Load existing
    html_content = get_scheduler_template(uid) or ""

    # Save
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        if action == "reset":
            html_content = ""  # force default below
        else:
            html_content = request.form.get("html_content") or ""

        save_scheduler_template(uid, html_content)
        # reload from DB to confirm persisted
        html_content = get_scheduler_template(uid) or ""

    # Default fallback if empty
    if not html_content.strip():
        html_content = """
<div style="font-family:Arial,sans-serif; font-size:14px; color:#111;">
  {% if brand_logo %}
    <div style="margin-bottom:10px;">
      <img src="{{brand_logo}}" alt="{{company_name}}" style="height:36px">
    </div>
  {% endif %}

  <p>Hi {{name}},</p>
  <p>Just a quick reminder about {{type}}.</p>

  {% if description %}
    <p>{{description}}</p>
  {% endif %}

  {% if due_date %}
    <p><b>Due date:</b> {{due_date}}</p>
  {% endif %}

  <p>Thanks,<br>{{sender}}</p>

  {% if footer %}
    <hr>
    <small style="color:#64748b;">{{footer}}</small>
  {% endif %}
</div>
""".strip()

    branding = get_branding(uid)

    sample_followup = {
        "client_name": "Nelly",
        "followup_type": "proposal",
        "description": "Please confirm payment timeline.",
        "message_override": "",
        "due_date": "2026-02-02",
    }

    preview_html = render_scheduler_html(html_content, user, sample_followup, branding)

    return render_template(
        "template_scheduler.html",
        html_content=html_content,
        preview_html=preview_html,
    )



@app.post("/templates/scheduler")
def template_scheduler_save():
    user, block = require_user()
    if block:
        return block

    html_content = (request.form.get("html_content") or "").strip()

    from models_saas import upsert_scheduler_template
    upsert_scheduler_template(user["id"], html_content)

    flash("Scheduler template saved ✅", "success")
    return redirect(url_for("template_scheduler"))



@app.get("/settings")
def settings():
    user, block = require_user()
    if block:
        return block

    fresh_user = get_user_by_id(user["id"])

    gmail_connected = bool((fresh_user.get("gmail_token") or "").strip())

    return render_template(
        "settings.html",
        daily_limit=fresh_user.get("daily_limit", 10),
        default_country=fresh_user.get("default_country", "US"),
        gmail_connected=gmail_connected,
        gmail_email=fresh_user.get("email"),
    )


@app.route("/branding", methods=["GET", "POST"])
def branding():
    user, block = require_user()
    if block:
        return block

    from models_saas import get_branding, set_branding

    uid = user["id"]

    if request.method == "POST":
        logo = request.form.get("logo", "")
        color = request.form.get("color", "#111827")
        company_name = request.form.get("company_name", "")
        support_email = request.form.get("support_email", "")
        footer = request.form.get("footer", "")

        set_branding(
            user_id=uid,
            logo_url=logo,
            color=color,
            company_name=company_name,
            support_email=support_email,
            footer=footer,
        )
        flash("Branding saved ✅", "success")
        return redirect(url_for("branding"))

    b = get_branding(uid)
    return render_template("branding.html", branding=b)


@app.route("/email-templates")
def email_templates():
    user, block = require_user()
    if block:
        return block
    return render_template("email_template.html", templates=get_email_templates(user["id"]))


@app.route("/email-templates/new", methods=["GET", "POST"])
def new_email_template():
    user, block = require_user()
    if block:
        return block

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        subject = (request.form.get("subject") or "").strip()
        html_content = (request.form.get("html_content") or "").strip()
        add_email_template(user["id"], name, subject, html_content)
        flash("Template saved ✅", "success")
        return redirect(url_for("email_templates"))

    return render_template("email_template_form.html", template=None)


@app.route("/email-templates/<int:tid>/edit", methods=["GET", "POST"])
def edit_email_template(tid):
    user, block = require_user()
    if block:
        return block

    templates = get_email_templates(user["id"])
    template = next((t for t in templates if int(t["id"]) == int(tid)), None)
    if not template:
        flash("Template not found.", "danger")
        return redirect(url_for("email_templates"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        subject = (request.form.get("subject") or "").strip()
        html_content = (request.form.get("html_content") or "").strip()
        update_email_template(tid, name, subject, html_content)
        flash("Template updated ✅", "success")
        return redirect(url_for("email_templates"))

    return render_template("email_template_form.html", template=template)


@app.route("/email-templates/<int:tid>/delete", methods=["POST"])
def delete_email_template_route(tid):
    user, block = require_user()
    if block:
        return block
    delete_email_template(tid)
    flash("Template deleted.", "success")
    return redirect(url_for("email_templates"))


@app.route("/analytics")
def analytics():
    user, block = require_user()
    if block:
        return block
    stats = get_analytics_data()
    return render_template("analytics.html", stats=stats)


@app.route("/analytics/export/csv")
def export_analytics_csv():
    user, block = require_user()
    if block:
        return block
    stats = get_analytics_data()
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(["Date", "Follow-ups Sent"])
    for day, count in stats["sent_per_day"]:
        cw.writerow([day, count])
    return Response(si.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=analytics.csv"})


@app.route("/analytics/export/pdf")
def export_analytics_pdf():
    user, block = require_user()
    if block:
        return block
    stats = get_analytics_data()
    html = render_template("analytics_pdf.html", stats=stats)
    result = BytesIO()
    pisa.CreatePDF(html, dest=result)
    return Response(result.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment;filename=analytics.pdf"})


@app.route("/notifications")
def notifications():
    user, block = require_user()
    if block:
        return ""
    notes = get_notifications(user["id"], unread_only=True)
    return render_template("notifications.html", notifications=notes)


@app.get("/api/notifications/count")
def notifications_count():
    user, block = require_user()
    if block:
        return jsonify({"count": 0})
    notes = get_notifications(user["id"], unread_only=True)
    return jsonify({"count": len(notes)})


@app.route("/notifications/read/<int:nid>", methods=["POST"])
def read_notification(nid):
    user, block = require_user()
    if block:
        return block
    mark_notification_read(nid)
    return "OK"


@app.route("/admin")
def admin():
    user, block = require_user()
    if block:
        return block

    if (user.get("email") or "").strip().lower() != ADMIN_EMAIL:
        flash("Not authorized.", "danger")
        return redirect(url_for("dashboard"))

    stats = stats_overview()
    users = get_all_users()
    return render_template("admin.html", stats=stats, users=users)


# @app.route("/auto_chase", methods=["POST", "GET"])
# def auto_chase():
#     user, block = require_user()
#     if block:
#         return block
#     try:
#         result = process_auto_chase(user_id=user["id"])
#         sent = int((result or {}).get("sent", 0)) if isinstance(result, dict) else int(result or 0)
#         flash(f"Auto-chase done ✅ Sent {sent}.", "success")
#     except Exception as e:
#         current_app.logger.exception("Auto-chase failed")
#         flash(f"Auto-chase failed: {str(e)}", "danger")
#     return redirect(url_for("dashboard"))


@app.route("/routes")
def routes():
    return "<br>".join(sorted([r.endpoint + " -> " + str(r) for r in app.url_map.iter_rules()]))


import secrets
from datetime import datetime, timedelta

def gen_otp6() -> str:
    return str(secrets.randbelow(900000) + 100000)

def utc_now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat()

def utc_plus_minutes_iso(m: int):
    return (datetime.utcnow() + timedelta(minutes=m)).replace(microsecond=0).isoformat()


from datetime import datetime

def cleanup_expired_otps():
    now = datetime.utcnow().replace(microsecond=0).isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET email_verify_code=NULL,
            email_verify_expires_at=NULL
        WHERE email_verify_expires_at IS NOT NULL
          AND email_verify_expires_at < ?
    """, (now,))
    conn.commit()
    conn.close()


@app.route("/account/email", methods=["GET", "POST"])
@login_required
def change_email():
    uid = int(session["user_id"])
    user = get_user_by_id(uid)

    if request.method == "POST":
        new_email = (request.form.get("email") or "").strip().lower()
        if not new_email or "@" not in new_email:
            flash("Enter a valid email.", "danger")
            return redirect(url_for("change_email"))

        # prevent duplicates
        existing = get_user_by_email(new_email)
        if existing and int(existing["id"]) != uid:
            flash("That email is already in use.", "danger")
            return redirect(url_for("change_email"))

        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE users
            SET email=?,
                email_verified=0,
                email_verified_at=NULL,
                email_verify_code=NULL,
                email_verify_expires_at=NULL,
                email_verify_last_sent_at=NULL
            WHERE id=?
        """, (new_email, uid))
        conn.commit()
        conn.close()

        session["pending_verify_user_id"] = uid

        try:
            send_verification_code(uid, new_email)
        except Exception:
            flash("Could not send verification email. Check SMTP settings.", "danger")
            return redirect(url_for("change_email"))

        flash("Verification code sent to your new email.", "success")
        return redirect(url_for("verify_email"))

    return render_template("change_email.html", user=user)




import secrets
from datetime import datetime, timedelta

# def send_verification_code(uid: int, email: str):
#     cleanup_expired_otps()

#     conn = get_connection()
#     c = conn.cursor()
#     c.execute("SELECT email_verify_last_sent_at FROM users WHERE id=?", (uid,))
#     row = c.fetchone()
#     last_sent = (row[0] if row else None) or ""

#     now = datetime.utcnow().replace(microsecond=0)
#     if last_sent:
#         try:
#             last_dt = datetime.fromisoformat(last_sent)
#             if (now - last_dt).total_seconds() < 60:
#                 raise RuntimeError("Please wait 60 seconds before resending.")
#         except ValueError:
#             pass

#     code = f"{secrets.randbelow(1000000):06d}"
#     expires = (now + timedelta(minutes=15)).isoformat()

#     c.execute("""
#         UPDATE users
#         SET email_verify_code=?,
#             email_verify_expires_at=?,
#             email_verify_last_sent_at=?
#         WHERE id=?
#     """, (code, expires, now.isoformat(), uid))
#     conn.commit()
#     conn.close()

#     send_email_smtp(
#         email,
#         "Your verification code",
#         f"Your code is: {code}\n\nExpires in 15 minutes."
#     )
# from auth_utils import _gen_otp6
import os, secrets
from datetime import datetime, timedelta
from database import get_connection
from mailer import send_email_smtp  # whatever your SMTP sender is

def _gen_otp6() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"

def send_verification_code(uid: int, email: str, minutes: int = 15) -> None:
    code = _gen_otp6()
    now = datetime.utcnow().replace(microsecond=0)
    exp = (now + timedelta(minutes=minutes)).isoformat()

    # store in DB
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET email_verify_code=?,
            email_verify_expires_at=?,
            email_verify_last_sent_at=?
        WHERE id=?
    """, (code, exp, now.isoformat(), int(uid)))
    conn.commit()
    conn.close()

    app_name = os.getenv("APP_NAME", "Your App")
    subject = f"{app_name} verification code: {code}"
    body_text = f"Your verification code is: {code}\n\nThis code expires in {minutes} minutes."

    # optional html
    body_html = f"""
    <div style="font-family:Arial,sans-serif; font-size:14px; color:#111;">
      <h2 style="margin:0 0 10px;">Verify your email</h2>
      <p>Your verification code is:</p>
      <div style="font-size:28px; font-weight:800; letter-spacing:4px; padding:12px 16px; background:#f3f4f6; display:inline-block; border-radius:10px;">
        {code}
      </div>
      <p style="margin-top:14px; color:#555;">Expires in {minutes} minutes.</p>
    </div>
    """.strip()

    send_email_smtp(
        to_email=email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )



@app.post("/verify/resend")
def resend_verify_code():
    cleanup_expired_otps()
    uid = session.get("pending_verify_user_id")
    if not uid:
        return redirect(url_for("login"))

    user = get_user_by_id(int(uid))
    if not user:
        session.clear()
        return redirect(url_for("login"))

    try:
        send_verification_code(int(uid), user["email"])
        flash("Code resent ✅", "success")
    except Exception as e:
        flash(str(e), "danger")

    return redirect(url_for("verify_email"))


from flask import render_template, request

@app.get("/verify")
def verify_email():
    cleanup_expired_otps()
    uid = session.get("pending_verify_user_id") or session.get("user_id")
    if not uid:
        return redirect(url_for("login"))

    user = get_user_by_id(uid)
    if not user:
        return redirect(url_for("login"))

    # If already verified, just go dashboard
    if int(user.get("email_verified") or 0) == 1:
        return redirect(url_for("dashboard"))

    return render_template("verify_email.html", email=user.get("email", ""))


@app.post("/verify")
def verify_email_submit():
    uid = session.get("user_id") or session.get("pending_verify_user_id")
    if not uid:
        return redirect(url_for("login"))

    user = get_user_by_id(uid)
    if not user:
        return redirect(url_for("login"))

    otp = (request.form.get("otp") or "").strip()
    if not otp:
        flash("Enter the 6-digit code.", "danger")
        return redirect(url_for("verify_email"))

    saved = (user.get("email_verify_code") or "").strip()
    exp = (user.get("email_verify_expires_at") or "").strip()

    if not saved or not exp:
        flash("No active code. Resend a new one.", "danger")
        return redirect(url_for("verify_email"))

    try:
        exp_dt = datetime.fromisoformat(exp)
    except Exception:
        exp_dt = datetime.utcnow() - timedelta(days=1)

    if datetime.utcnow() > exp_dt:
        flash("Code expired. Resend a new one.", "danger")
        return redirect(url_for("verify_email"))

    if otp != saved:
        flash("Wrong code.", "danger")
        return redirect(url_for("verify_email"))

    # ✅ mark verified
    now = utc_now_iso()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET email_verified=1,
            email_verified_at=?,
            email_verify_code=NULL,
            email_verify_expires_at=NULL
        WHERE id=?
    """, (now, int(uid)))
    conn.commit()
    conn.close()

    session["user_id"] = int(uid)
    session.pop("pending_verify_user_id", None)

    flash("Email verified ✅", "success")
    return redirect(url_for("dashboard"))


@app.post("/verify/resend")
def verify_email_resend():
    uid = session.get("user_id") or session.get("pending_verify_user_id")
    if not uid:
        return redirect(url_for("login"))

    user = get_user_by_id(uid)
    if not user:
        return redirect(url_for("login"))

    if int(user.get("email_verified") or 0) == 1:
        return redirect(url_for("dashboard"))

    last = (user.get("email_verify_last_sent_at") or "").strip()
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if (datetime.utcnow() - last_dt).total_seconds() < 60:
                flash("Too fast. Wait 60 seconds then resend.", "danger")
                return redirect(url_for("verify_email"))
        except Exception:
            pass

    try:
        send_verification_code(int(uid), user["email"])
    except Exception:
        flash("Could not resend code. Check SMTP settings.", "danger")
        return redirect(url_for("verify_email"))

    flash("New code sent ✅", "success")
    return redirect(url_for("verify_email"))


# -----------------------------
# BILLING
# -----------------------------


from models_saas import get_user_subscription

@app.route("/billing")
def billing():
    user, block = require_user()
    if block:
        return block

    sub = get_user_subscription(int(user["id"]))

    return render_template(
        "billing.html",
        trial_active=is_trial_active(user),
        trial_end=user.get("trial_end"),
        subscription_active=sub["active"],
        subscription_plan=sub.get("plan", ""),
    )


from datetime import datetime, timezone

def _utc_now():
    return datetime.now(timezone.utc)

def _parse_iso(dt_str: str):
    dt_str = (dt_str or "").strip()
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _is_subscription_active(user: dict) -> bool:
    status = (user.get("subscription_status") or "").strip().lower()
    if status not in ("active", "trialing"):
        return False

    # If you set a period end, enforce it
    pe = _parse_iso(user.get("current_period_end"))
    if pe and _utc_now() > pe:
        return False

    return True

def _has_access(user: dict) -> bool:
    if not user:
        return False

    if int(user.get("is_admin") or 0) == 1:
        return True

    # ✅ pay success sets is_subscribed=1
    if int(user.get("is_subscribed") or 0) == 1:
        return True

    # ✅ stripe/paystack status
    status = (user.get("subscription_status") or "").strip().lower()
    if status == "active":
        return True

    return _is_trial_active(user)



import stripe
from flask import redirect, url_for, flash
from models_saas import get_user_subscription
from database import get_connection

@app.post("/billing/cancel-subscription")
def cancel_subscription():
    user, block = require_user()
    if block:
        return block

    sub = get_user_subscription(int(user["id"]))
    sub_id = (sub.get("stripe_subscription_id") or "").strip()

    if not sub_id:
        flash("No active subscription found to cancel.", "warning")
        return redirect(url_for("billing"))

    try:
        # Cancel immediately. (If you prefer cancel at period end, tell me)
        stripe.Subscription.delete(sub_id)
    except Exception as e:
        flash(f"Cancel failed: {type(e).__name__}: {e}", "danger")
        return redirect(url_for("billing"))

    # Update DB
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET subscription_status='canceled'
        WHERE id=?
    """, (int(user["id"]),))
    conn.commit()
    conn.close()

    flash("Subscription canceled ✅", "success")
    return redirect(url_for("billing"))


def _is_trial_active(user: dict) -> bool:
    end = (user.get("trial_end") or "").strip()
    if not end:
        return False
    try:
        dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return _utc_now() < dt
    except Exception:
        return False

import os
import stripe
from flask import request, redirect, url_for, flash, abort

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5001")

def _price_for_plan(plan: str) -> str:
    plan = (plan or "").strip().lower()
    if plan == "monthly":
        price_id = os.getenv("STRIPE_PRICE_MONTHLY", "")
    elif plan == "yearly":
        price_id = os.getenv("STRIPE_PRICE_YEARLY", "")
    else:
        price_id = ""
    if not price_id:
        raise RuntimeError(f"Missing Stripe price for plan={plan!r}. Check env STRIPE_PRICE_MONTHLY/STRIPE_PRICE_YEARLY.")
    return price_id

def activate_subscription(user_id, plan):
    now = datetime.utcnow()

    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET
          subscription_status='active',
          plan=?,
          trial_end=NULL,
          current_period_end=?,
          is_subscribed=1
        WHERE id=?
    """, (
        plan,
        (now + timedelta(days=30 if plan == "monthly" else 365)).isoformat(),
        user_id
    ))

    conn.commit()
    conn.close()

from models_saas import deactivate_subscription, mark_payment_failed

import hmac, hashlib

@app.post("/webhooks/paystack")
def paystack_webhook():
    payload = request.data
    signature = request.headers.get("X-Paystack-Signature")

    expected = hmac.new(
        os.getenv("PAYSTACK_SECRET_KEY").encode(),
        payload,
        hashlib.sha512
    ).hexdigest()

    if signature != expected:
        return "Invalid signature", 401

    event = request.json
    etype = event.get("event")
    data = event.get("data", {})

    if etype == "subscription.disable":
        user_id = data.get("metadata", {}).get("user_id")
        if user_id:
            deactivate_subscription(user_id)

    elif etype == "invoice.payment_failed":
        user_id = data.get("metadata", {}).get("user_id")
        if user_id:
            mark_payment_failed(user_id)

    return "ok", 200



import requests
import uuid

@app.post("/subscribe")
def subscribe():
    user, block = require_user()
    if block:
        return block

    plan = (request.form.get("plan") or "monthly").lower()

    if plan == "monthly":
        plan_code = os.getenv("PAYSTACK_PLAN_MONTHLY")
        amount = 900 * 100  # kobo
    elif plan == "yearly":
        plan_code = os.getenv("PAYSTACK_PLAN_YEARLY")
        amount = 9000 * 100
    else:
        flash("Invalid plan.", "danger")
        return redirect(url_for("billing"))

    ref = f"sub_{uuid.uuid4().hex}"

    payload = {
        "email": user["email"],
        "amount": amount,
        "reference": ref,
        "plan": plan_code,
        "callback_url": url_for("paystack_callback", _external=True),
        "metadata": {
            "user_id": user["id"],
            "plan": plan,
        }
    }

    headers = {
        "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
        "Content-Type": "application/json",
    }

    res = requests.post(
        "https://api.paystack.co/transaction/initialize",
        json=payload,
        headers=headers,
        timeout=15,
    )

    data = res.json()
    if not data.get("status"):
        flash("Payment initialization failed.", "danger")
        return redirect(url_for("billing"))

    return redirect(data["data"]["authorization_url"])



from datetime import datetime, timedelta

@app.get("/billing/paystack/callback")
def paystack_callback():
    user, block = require_user()
    if block:
        return block

    reference = (request.args.get("reference") or "").strip()
    if not reference:
        flash("Missing payment reference.", "danger")
        return redirect(url_for("billing"))

    secret = (os.getenv("PAYSTACK_SECRET_KEY") or "").strip()
    if not secret:
        flash("Paystack is not configured (missing PAYSTACK_SECRET_KEY).", "danger")
        return redirect(url_for("billing"))

    headers = {"Authorization": f"Bearer {secret}"}

    try:
        res = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=headers,
            timeout=15,
        )
        res.raise_for_status()
        payload = res.json()
    except Exception as e:
        flash(f"Payment verification failed: {type(e).__name__}", "danger")
        return redirect(url_for("billing"))

    if not payload.get("status"):
        flash("Payment verification failed.", "danger")
        return redirect(url_for("billing"))

    tx = payload.get("data") or {}
    if (tx.get("status") or "").lower() != "success":
        flash("Payment not successful.", "danger")
        return redirect(url_for("billing"))

    # ✅ ACTIVATE SUBSCRIPTION (set a REAL period end)
    plan = ((tx.get("metadata") or {}).get("plan") or "monthly").lower()
    days = 365 if plan == "yearly" else 30
    period_end = (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat()

    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        UPDATE users
        SET subscription_status='active',
            is_subscribed=1,
            plan=?,
            current_period_end=?
        WHERE id=?
        """,
        (plan, period_end, int(user["id"])),
    )
    conn.commit()
    conn.close()

    flash("Subscription active ✅", "success")
    return redirect(url_for("billing"))

from flask import request, flash, redirect, url_for

from flask import request, redirect, url_for, flash
import stripe
from database import get_connection

@app.route("/billing/success")
def billing_success():
    print("[BILLING] cust_id:", cust_id, "sub_id:", sub_id, "plan:", plan, "user:", user["id"])
    user, block = require_user()
    if block:
        return block

    session_id = request.args.get("session_id")
    if not session_id:
        flash("Missing session_id.", "danger")
        return redirect(url_for("billing"))

    try:
        sess = stripe.checkout.Session.retrieve(
            session_id,
            expand=["subscription", "customer"]
        )
    except Exception as e:
        flash(f"Stripe lookup failed: {type(e).__name__}: {e}", "danger")
        return redirect(url_for("billing"))

    # Stripe objects/ids
    cust_id = sess.get("customer")
    sub = sess.get("subscription")
    sub_id = sub["id"] if isinstance(sub, dict) else sub

    if not sub_id:
        flash("Checkout completed but no subscription found.", "danger")
        return redirect(url_for("billing"))

    # Optional: plan from metadata
    plan = (sess.get("metadata") or {}).get("plan") or ""

    # Mark user subscribed in DB
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET subscription_status='active',
            stripe_customer_id=?,
            stripe_subscription_id=?,
            plan=COALESCE(NULLIF(?, ''), plan)
        WHERE id=?
    """, (str(cust_id or ""), str(sub_id), plan, int(user["id"])))
    conn.commit()
    conn.close()

    flash("Subscription active ✅", "success")
    return redirect(url_for("billing"))



@app.route("/billing/cancel")
def billing_cancel():
    flash("Checkout cancelled.", "warning")
    return redirect(url_for("billing"))

@app.get("/debug/socketio")
def debug_socketio():
    return {"has_socketio": True}



import os
from web.scheduler import start_scheduler

def maybe_start_scheduler():
    # Development (Flask reloader)
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_scheduler(app)
        return

    # Production (gunicorn / Render)
    if not app.debug:
        start_scheduler(app)

maybe_start_scheduler()

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5001)),
        debug=False
    )
