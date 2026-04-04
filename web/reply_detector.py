# web/reply_detector.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, parseaddr
from typing import Any, Callable, Dict, Iterable, List, Optional

from googleapiclient.discovery import build


@dataclass
class ReplyDetectionResult:
    followup_id: int
    thread_id: str
    reply_message_id: str
    reply_from: str
    reply_subject: str
    reply_date: Optional[str]
    stopped: bool


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_lower(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def header_map(payload: Dict[str, Any]) -> Dict[str, str]:
    headers = payload.get("headers") or []
    out: Dict[str, str] = {}
    for h in headers:
        name = h.get("name")
        value = h.get("value")
        if isinstance(name, str) and isinstance(value, str):
            out[name.lower()] = value
    return out


def extract_email_address(header_value: str) -> str:
    _, addr = parseaddr(header_value or "")
    return safe_lower(addr)


def parse_gmail_date(date_header: str) -> Optional[datetime]:
    if not date_header:
        return None
    try:
        dt = parsedate_to_datetime(date_header)
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def is_inbound_reply_message(
    msg: Dict[str, Any],
    *,
    user_email: str,
    recipient_email: str,
    sent_message_id: Optional[str] = None,
) -> bool:
    """
    Returns True only for messages that look like an inbound reply from the recipient.

    Rules:
    - not from the user
    - from recipient_email
    - not the original sent message itself
    """
    payload = msg.get("payload") or {}
    headers = header_map(payload)

    gmail_message_id = msg.get("id") or ""
    from_email = extract_email_address(headers.get("from", ""))
    to_email = extract_email_address(headers.get("to", ""))

    user_email = safe_lower(user_email)
    recipient_email = safe_lower(recipient_email)

    if sent_message_id and gmail_message_id == sent_message_id:
        return False

    if not from_email:
        return False

    if from_email == user_email:
        return False

    if recipient_email and from_email != recipient_email:
        return False

    # Helpful but not required; some replies may have weird To headers.
    if to_email and user_email and to_email != user_email:
        # We do not hard-fail here because Gmail threads can have aliases/cc cases.
        pass

    return True


def extract_message_summary(msg: Dict[str, Any]) -> Dict[str, str]:
    payload = msg.get("payload") or {}
    headers = header_map(payload)

    return {
        "message_id": msg.get("id") or "",
        "thread_id": msg.get("threadId") or "",
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
    }


def get_gmail_service_for_user(
    user: Dict[str, Any],
    *,
    creds_from_user: Callable[[Dict[str, Any]], Any],
    save_refreshed_token: Optional[Callable[[int, Any], None]] = None,
):
    """
    Build Gmail API service from your existing credential helper.

    Assumes:
    - creds_from_user(user) -> google.oauth2.credentials.Credentials
    - optional save_refreshed_token(user_id, creds)
    """
    creds = creds_from_user(user)
    if save_refreshed_token and getattr(creds, "valid", False):
        try:
            save_refreshed_token(int(user["id"]), creds)
        except Exception:
            pass

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def fetch_thread_messages(service, thread_id: str) -> List[Dict[str, Any]]:
    thread = (
        service.users()
        .threads()
        .get(userId="me", id=thread_id, format="full")
        .execute()
    )
    return thread.get("messages") or []


def detect_reply_in_thread(
    service,
    *,
    user_email: str,
    recipient_email: str,
    thread_id: str,
    sent_message_id: Optional[str],
) -> Optional[Dict[str, str]]:
    """
    Find the first inbound reply from the intended recipient in the Gmail thread.
    """
    messages = fetch_thread_messages(service, thread_id)

    candidates: List[tuple[Optional[datetime], Dict[str, Any]]] = []
    for msg in messages:
        if is_inbound_reply_message(
            msg,
            user_email=user_email,
            recipient_email=recipient_email,
            sent_message_id=sent_message_id,
        ):
            payload = msg.get("payload") or {}
            headers = header_map(payload)
            candidates.append((parse_gmail_date(headers.get("date", "")), msg))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc))
    chosen = candidates[0][1]
    summary = extract_message_summary(chosen)

    return {
        "reply_message_id": summary["message_id"],
        "reply_from": summary["from"],
        "reply_subject": summary["subject"],
        "reply_date": summary["date"],
    }


def run_reply_detection_for_user(
    *,
    user: Dict[str, Any],
    user_email: str,
    followups: Iterable[Dict[str, Any]],
    creds_from_user: Callable[[Dict[str, Any]], Any],
    save_refreshed_token: Optional[Callable[[int, Any], None]] = None,
    mark_followup_replied: Callable[..., bool],
    disable_followup_schedule: Callable[[int, int], bool],
    add_notification: Optional[Callable[[int, str], None]] = None,
) -> List[ReplyDetectionResult]:
    """
    Scan tracked followups for replies and auto-stop scheduling.

    Each followup dict should contain at least:
    - id
    - email
    - gmail_thread_id
    - last_sent_message_id (optional)
    - status (optional)
    - schedule_enabled (optional)
    """
    service = get_gmail_service_for_user(
        user,
        creds_from_user=creds_from_user,
        save_refreshed_token=save_refreshed_token,
    )

    results: List[ReplyDetectionResult] = []
    uid = int(user["id"])

    for f in followups:
        fid = int(f["id"])
        status = safe_lower(f.get("status"))
        if status == "replied":
            continue

        thread_id = (f.get("gmail_thread_id") or "").strip()
        recipient_email = safe_lower(f.get("email"))
        sent_message_id = (f.get("last_sent_message_id") or "").strip() or None

        if not thread_id or not recipient_email:
            continue

        found = detect_reply_in_thread(
            service,
            user_email=user_email,
            recipient_email=recipient_email,
            thread_id=thread_id,
            sent_message_id=sent_message_id,
        )
        if not found:
            continue

        mark_followup_replied(
            fid=fid,
            user_id=uid,
            reply_message_id=found["reply_message_id"],
            reply_from=found["reply_from"],
            reply_subject=found["reply_subject"],
            reply_date=found["reply_date"],
        )

        stopped = disable_followup_schedule(fid, uid)

        if add_notification:
            try:
                add_notification(
                    uid,
                    f"Reply detected from {recipient_email}. Auto-stopped follow-up #{fid}."
                )
            except Exception:
                pass

        results.append(
            ReplyDetectionResult(
                followup_id=fid,
                thread_id=thread_id,
                reply_message_id=found["reply_message_id"],
                reply_from=found["reply_from"],
                reply_subject=found["reply_subject"],
                reply_date=found["reply_date"],
                stopped=bool(stopped),
            )
        )

    return results