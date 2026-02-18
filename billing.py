# billing.py (PAYSTACK VERSION — Stripe removed)
import os
import json
import hmac
import hashlib
import requests
from datetime import datetime, timezone

from flask import Blueprint, request, redirect, url_for, flash, render_template, session, abort

from database import get_connection
from models_saas import (
    get_user_by_id,
    is_trial_active,
)

# =========================
# CONFIG
# =========================
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5001").rstrip("/")

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "").strip()
PAYSTACK_WEBHOOK_SECRET = os.getenv("PAYSTACK_WEBHOOK_SECRET", "").strip()  # optional; if empty we use SECRET_KEY
PAYSTACK_BASE = "https://api.paystack.co"

# Plan codes (set these in .env)
PAYSTACK_PLAN_MONTHLY_NGN = os.getenv("PAYSTACK_PLAN_MONTHLY_NGN", "").strip()
PAYSTACK_PLAN_YEARLY_NGN  = os.getenv("PAYSTACK_PLAN_YEARLY_NGN", "").strip()
PAYSTACK_PLAN_MONTHLY_USD = os.getenv("PAYSTACK_PLAN_MONTHLY_USD", "").strip()
PAYSTACK_PLAN_YEARLY_USD  = os.getenv("PAYSTACK_PLAN_YEARLY_USD", "").strip()

# Amounts are in kobo/cent (Paystack wants lowest currency unit)
# NOTE: Your comments were wrong. ₦12,600 = 1,260,000 kobo (not 12,600,000)
PRICE_TABLE = {
    ("monthly", "NGN"): int(os.getenv("PRICE_MONTHLY_NGN", "1260000")),   # ₦12,600 => 1,260,000 kobo
    ("yearly",  "NGN"): int(os.getenv("PRICE_YEARLY_NGN",  "12600000")),  # ₦126,000 => 12,600,000 kobo
    ("monthly", "USD"): int(os.getenv("PRICE_MONTHLY_USD", "900")),       # $9.00 => 900 cents
    ("yearly",  "USD"): int(os.getenv("PRICE_YEARLY_USD",  "9000")),      # $90.00 => 9000 cents
}

billing_bp = Blueprint("billing", __name__)

# =========================
# AUTH / HELPERS
# =========================
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


def _paystack_headers():
    if not PAYSTACK_SECRET_KEY:
        raise RuntimeError("PAYSTACK_SECRET_KEY missing in .env")
    return {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def _plan_code_for(plan: str, currency: str) -> str:
    plan = (plan or "").strip().lower()
    currency = (currency or "NGN").strip().upper()

    if plan not in ("monthly", "yearly"):
        return ""

    if currency == "USD":
        return PAYSTACK_PLAN_MONTHLY_USD if plan == "monthly" else PAYSTACK_PLAN_YEARLY_USD

    return PAYSTACK_PLAN_MONTHLY_NGN if plan == "monthly" else PAYSTACK_PLAN_YEARLY_NGN


def _amount_for(plan: str, currency: str) -> int:
    plan = (plan or "").strip().lower()
    currency = (currency or "NGN").strip().upper()
    amt = PRICE_TABLE.get((plan, currency))
    if not amt:
        raise RuntimeError(f"Missing price for ({plan}, {currency}). Set PRICE_* in .env")
    return int(amt)


def _verify_paystack_signature(raw_body: bytes, signature: str) -> bool:
    secret = PAYSTACK_WEBHOOK_SECRET or PAYSTACK_SECRET_KEY
    if not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, (signature or "").strip())


def _iso_from_unix(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat(timespec="seconds")


# =========================
# DB WRITES (single source of truth = users table)
# =========================
def _db_set_subscription_state(
    user_id: int,
    status: str,
    plan: str | None = None,
    currency: str | None = None,
    paystack_customer_code: str | None = None,
    paystack_subscription_code: str | None = None,
    paystack_email_token: str | None = None,
    current_period_end: str | None = None,
):
    """
    Updates users table. Only overwrites fields you pass (others stay).
    """
    conn = get_connection()
    c = conn.cursor()

    # Fetch current to preserve when None
    c.execute("SELECT * FROM users WHERE id=? LIMIT 1", (int(user_id),))
    u = c.fetchone()
    if not u:
        conn.close()
        return

    # fetchone() returns a tuple → use indexes
    cur_plan = u[3]
    cur_currency = u[4]
    cur_ccode = u[5]
    cur_scode = u[6]
    cur_etok = u[7]
    cur_cpe = u[8]

    c.execute("""
        UPDATE users
        SET subscription_status=?,
            plan=?,
            currency=?,
            paystack_customer_code=?,
            paystack_subscription_code=?,
            paystack_email_token=?,
            current_period_end=?,
            is_subscribed=CASE WHEN ?='active' THEN 1 ELSE is_subscribed END
        WHERE id=?
    """, (
        (status or "inactive").strip().lower(),
        (plan if plan is not None else cur_plan),
        (currency if currency is not None else cur_currency),
        (paystack_customer_code if paystack_customer_code is not None else cur_ccode),
        (paystack_subscription_code if paystack_subscription_code is not None else cur_scode),
        (paystack_email_token if paystack_email_token is not None else cur_etok),
        (current_period_end if current_period_end is not None else cur_cpe),
        (status or "inactive").strip().lower(),
        int(user_id),
    ))

    conn.commit()
    conn.close()

def _db_mark_trial_upgraded(user_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET is_subscribed=1,
            subscription_status='active'
        WHERE id=?
    """, (int(user_id),))
    conn.commit()
    conn.close()


def _find_user_id_by_email(email: str) -> int | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE lower(email)=? LIMIT 1", (email,))
    row = c.fetchone()
    conn.close()
    return int(row["id"]) if row else None


# =========================
# ROUTES
# =========================
@billing_bp.get("/billing")
def billing():
    user, block = require_user()
    if block:
        return block

    # reload fresh
    u = get_user_by_id(int(user["id"])) or {}

    subscription_status = (u.get("subscription_status") or "inactive").lower()
    subscription_plan = (u.get("plan") or "").lower()
    currency = (u.get("currency") or "NGN").upper()
    current_period_end = u.get("current_period_end")

    subscription_active = 1 if subscription_status in ("active", "trialing") else 0
    trial_active = 1 if is_trial_active(u) else 0

    return render_template(
        "billing.html",
        trial_active=trial_active,
        trial_end=u.get("trial_end"),
        subscription_status=subscription_status,
        subscription_active=subscription_active,
        subscription_plan=subscription_plan,
        subscription_renews_at=current_period_end,
        currency=currency,
    )


@billing_bp.post("/billing/subscribe")
def subscribe():
    user, block = require_user()
    if block:
        return block

    plan = (request.form.get("plan") or "monthly").strip().lower()
    currency = (request.form.get("currency") or "NGN").strip().upper()

    if plan not in ("monthly", "yearly"):
        flash("Invalid plan.", "danger")
        return redirect(url_for("billing.billing"))

    if currency not in ("NGN", "USD"):
        currency = "NGN"

    plan_code = _plan_code_for(plan, currency)
    amount = _amount_for(plan, currency)

    if not plan_code:
        flash(f"Paystack plan code missing for {plan} {currency}.", "danger")
        return redirect(url_for("billing.billing"))

    payload = {
        "email": user["email"],
        "amount": amount,
        "currency": currency,
        "plan": plan_code,
        "callback_url": f"{APP_BASE_URL}/billing/paystack/success",
        "metadata": {
            "user_id": str(user["id"]),
            "plan": plan,
            "currency": currency,
        },
    }

    try:
        r = requests.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            headers=_paystack_headers(),
            data=json.dumps(payload),
            timeout=30,
        )
        data = r.json()
    except Exception as e:
        flash(f"Paystack init failed: {type(e).__name__}: {e}", "danger")
        return redirect(url_for("billing.billing"))

    if not data.get("status"):
        flash(f"Paystack init failed: {data.get('message') or 'Unknown error'}", "danger")
        return redirect(url_for("billing.billing"))

    auth_url = (data.get("data") or {}).get("authorization_url")
    if not auth_url:
        flash("Paystack init failed: missing authorization_url.", "danger")
        return redirect(url_for("billing.billing"))

    return redirect(auth_url)


@billing_bp.get("/billing/paystack/success")
def paystack_success():
    """
    This runs after Paystack redirects back.
    Webhook may arrive later, but we still mark user active here
    so UI unlocks instantly.
    """
    user, block = require_user()
    if block:
        return block

    reference = (request.args.get("reference") or "").strip()
    if not reference:
        flash("Missing Paystack reference.", "danger")
        return redirect(url_for("billing.billing"))

    try:
        r = requests.get(
            f"{PAYSTACK_BASE}/transaction/verify/{reference}",
            headers=_paystack_headers(),
            timeout=30,
        )
        payload = r.json()
    except Exception as e:
        flash(f"Paystack verify failed: {type(e).__name__}: {e}", "danger")
        return redirect(url_for("billing.billing"))

    if not payload.get("status"):
        flash(f"Paystack verify failed: {payload.get('message') or 'Unknown'}", "danger")
        return redirect(url_for("billing.billing"))

    d = payload.get("data") or {}
    status = (d.get("status") or "").lower()
    meta = d.get("metadata") or {}

    if status != "success":
        flash("Payment not successful.", "warning")
        return redirect(url_for("billing.billing"))

    plan = (meta.get("plan") or "").strip().lower() or "monthly"
    currency = (meta.get("currency") or d.get("currency") or "NGN").strip().upper()

    customer = d.get("customer") or {}
    customer_code = (customer.get("customer_code") or "").strip()

    _db_mark_trial_upgraded(int(user["id"]))
    _db_set_subscription_state(
        user_id=int(user["id"]),
        status="active",
        plan=plan,
        currency=currency,
        paystack_customer_code=(customer_code or None),
    )

    flash("Checkout complete ✅ If it doesn’t unlock instantly, refresh in a few seconds.", "success")
    return redirect(url_for("billing.billing"))


# @billing_bp.post("/billing/cancel-subscription")
# def cancel_subscription():
#     """
#     Paystack cancel needs subscription_code + email_token (from webhook).
#     """
#     user, block = require_user()
#     if block:
#         return block

#     u = get_user_by_id(int(user["id"])) or {}
#     sub_code = (u.get("paystack_subscription_code") or "").strip()
#     email_token = (u.get("paystack_email_token") or "").strip()

#     if not sub_code or not email_token:
#         flash("Can’t cancel yet: Paystack subscription tokens not received. Wait a minute or trigger webhook.", "warning")
#         return redirect(url_for("billing.billing"))

#     try:
#         r = requests.post(
#             f"{PAYSTACK_BASE}/subscription/disable",
#             headers=_paystack_headers(),
#             data=json.dumps({"code": sub_code, "token": email_token}),
#             timeout=30,
#         )
#         data = r.json()
#     except Exception as e:
#         flash(f"Cancel failed: {type(e).__name__}: {e}", "danger")
#         return redirect(url_for("billing.billing"))

#     if not data.get("status"):
#         flash(f"Cancel failed: {data.get('message') or 'Unknown'}", "danger")
#         return redirect(url_for("billing.billing"))

#     _db_set_subscription_state(
#         user_id=int(user["id"]),
#         status="canceling",
#     )

#     flash("Subscription will cancel at period end ✅", "success")
#     return redirect(url_for("billing.billing"))


@billing_bp.post("/paystack/webhook")
def paystack_webhook():
    """
    Paystack webhook handler.
    - Verifies signature
    - Stores subscription_code + email_token for cancellation
    - Updates state
    """
    raw = request.data or b""
    sig = request.headers.get("x-paystack-signature", "")

    if not _verify_paystack_signature(raw, sig):
        return abort(400)

    try:
        event = request.get_json(force=True, silent=False) or {}
    except Exception:
        return abort(400)

    etype = (event.get("event") or "").strip()
    data = event.get("data") or {}

    # These are the most useful for subscriptions
    # Paystack commonly sends: subscription.create, subscription.enable, subscription.disable
    if etype in ("subscription.create", "subscription.enable"):
        sub_code = (data.get("subscription_code") or "").strip()
        email_token = (data.get("email_token") or "").strip()
        status = (data.get("status") or "active").strip().lower()

        customer = data.get("customer") or {}
        customer_code = (customer.get("customer_code") or "").strip()
        email = (customer.get("email") or "").strip().lower()

        uid = _find_user_id_by_email(email)
        if uid:
            _db_mark_trial_upgraded(uid)
            _db_set_subscription_state(
                user_id=uid,
                status=("active" if status in ("active", "enabled") else status),
                paystack_customer_code=(customer_code or None),
                paystack_subscription_code=(sub_code or None),
                paystack_email_token=(email_token or None),
            )

    if etype in ("subscription.disable",):
        customer = data.get("customer") or {}
        email = (customer.get("email") or "").strip().lower()
        uid = _find_user_id_by_email(email)
        if uid:
            _db_set_subscription_state(user_id=uid, status="inactive")

    return {"ok": True}


@billing_bp.get("/billing/cancel")
def billing_cancel():
    flash("Checkout cancelled.", "warning")
    return redirect(url_for("billing.billing"))

def _paystack_get_json(path: str, params=None):
    r = requests.get(
        f"{PAYSTACK_BASE}{path}",
        headers=_paystack_headers(),
        params=params or {},
        timeout=30,
    )
    data = r.json()
    if not data.get("status"):
        raise RuntimeError(data.get("message") or "Paystack request failed")
    return data.get("data")

def sync_subscription_tokens_by_email(user_id: int, email: str):
    # list subscriptions, find active one for this email
    subs = _paystack_get_json("/subscription", params={"perPage": 50})
    email = (email or "").strip().lower()

    for s in subs:
        customer = (s.get("customer") or {})
        if (customer.get("email") or "").strip().lower() != email:
            continue

        status = (s.get("status") or "").strip().lower()
        # Paystack statuses vary; treat these as cancelable/active-ish
        if status in ("active", "enabled"):
            sub_code = (s.get("subscription_code") or "").strip()
            email_token = (s.get("email_token") or "").strip()

            _db_set_subscription_state(
                user_id=user_id,
                status="active",
                paystack_subscription_code=sub_code or None,
                paystack_email_token=email_token or None,
            )
            return True

    return False


@billing_bp.post("/billing/cancel-subscription")
def cancel_subscription():
    user, block = require_user()
    if block:
        return block

    # always reload fresh
    u = get_user_by_id(int(user["id"])) or {}

    sub_code = (u.get("paystack_subscription_code") or "").strip()
    email_token = (u.get("paystack_email_token") or "").strip()

    # If missing, try to sync from Paystack first
    if (not sub_code) or (not email_token):
        try:
            ok = sync_subscription_tokens_by_email(int(user["id"]), (u.get("email") or "").strip())
        except Exception as e:
            ok = False
            print("[PAYSTACK] sync tokens failed:", repr(e))

        if ok:
            u = get_user_by_id(int(user["id"])) or {}
            sub_code = (u.get("paystack_subscription_code") or "").strip()
            email_token = (u.get("paystack_email_token") or "").strip()

    if not sub_code or not email_token:
        flash("Can’t cancel yet: subscription tokens not found. Webhook/sync didn’t return them.", "warning")
        return redirect(url_for("billing.billing"))

    # Call Paystack disable endpoint
    try:
        r = requests.post(
            f"{PAYSTACK_BASE}/subscription/disable",
            headers=_paystack_headers(),
            data=json.dumps({"code": sub_code, "token": email_token}),
            timeout=30,
        )
        resp = r.json()
    except Exception as e:
        flash(f"Cancel failed: {type(e).__name__}: {e}", "danger")
        return redirect(url_for("billing.billing"))

    if not resp.get("status"):
        msg = resp.get("message") or "Unknown error"

        # If Paystack says it's already inactive, sync your DB and move on
        if "already inactive" in msg.lower() or "not found" in msg.lower():
            _db_set_subscription_state(
                user_id=int(user["id"]),
                status="inactive",
                plan=(u.get("plan") or ""),
                currency=(u.get("currency") or "NGN"),
            )
            flash("Subscription is already inactive (Paystack). Your account is now updated.", "warning")
            return redirect(url_for("billing.billing"))

        flash(f"Cancel failed: {msg}", "danger")
        return redirect(url_for("billing.billing"))

    # Success
    _db_set_subscription_state(
        user_id=int(user["id"]),
        status="canceling",
        plan=(u.get("plan") or ""),
        currency=(u.get("currency") or "NGN"),
    )
    flash("Subscription will cancel at period end ✅", "success")
    return redirect(url_for("billing.billing"))
