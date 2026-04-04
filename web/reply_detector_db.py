# web/reply_detector_db.py

from __future__ import annotations

from typing import Any, Dict, List


def get_reply_tracked_followups(conn, user_id: int) -> List[Dict[str, Any]]:
    """
    Returns followups eligible for reply detection.
    Requires DB columns added below.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id,
            email,
            status,
            schedule_enabled,
            gmail_thread_id,
            last_sent_message_id,
            reply_detected_at,
            auto_stop_on_reply
        FROM followups
        WHERE user_id = ?
          AND COALESCE(email, '') <> ''
          AND COALESCE(gmail_thread_id, '') <> ''
          AND COALESCE(reply_detected_at, '') = ''
          AND COALESCE(auto_stop_on_reply, 1) = 1
        """,
        (int(user_id),),
    )
    rows = cur.fetchall()
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in rows]


def mark_followup_replied(
    conn,
    *,
    fid: int,
    user_id: int,
    reply_message_id: str,
    reply_from: str,
    reply_subject: str,
    reply_date: str,
) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE followups
        SET
            status = 'replied',
            reply_detected_at = ?,
            reply_message_id = ?,
            reply_from = ?,
            reply_subject = ?,
            reply_date = ?,
            stop_reason = 'reply_detected'
        WHERE id = ? AND user_id = ?
        """,
        (
            reply_date or "",
            reply_message_id or "",
            reply_from or "",
            reply_subject or "",
            reply_date or "",
            int(fid),
            int(user_id),
        ),
    )
    conn.commit()
    return cur.rowcount > 0


def disable_followup_schedule(conn, fid: int, user_id: int) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE followups
        SET
            schedule_enabled = 0,
            auto_stopped_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (int(fid), int(user_id)),
    )
    conn.commit()
    return cur.rowcount > 0


def save_outbound_gmail_metadata(
    conn,
    *,
    fid: int,
    user_id: int,
    gmail_thread_id: str,
    gmail_message_id: str,
) -> bool:
    """
    Call this right after Gmail send succeeds.
    """
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE followups
        SET
            gmail_thread_id = ?,
            last_sent_message_id = ?,
            last_reply_check_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (
            gmail_thread_id or "",
            gmail_message_id or "",
            int(fid),
            int(user_id),
        ),
    )
    conn.commit()
    return cur.rowcount > 0