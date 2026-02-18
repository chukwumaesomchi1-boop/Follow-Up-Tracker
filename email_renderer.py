import html
from datetime import datetime

def render_followup_email_html(
    *,
    brand_name: str = "FollowUp Tracker",
    brand_color: str = "#36A2EB",
    logo_url: str = "",
    headline: str = "Quick follow-up",
    message_html: str = "",
    client_name: str = "",
    footer_note: str = "If you already handled this, you can ignore it.",
) -> str:
    """
    Returns an HTML string safe for Gmail API send.
    - message_html can contain <br> etc. If you're passing plain text, use plain_to_html().
    """

    safe_brand_name = html.escape(brand_name)
    safe_headline = html.escape(headline)
    safe_client_name = html.escape(client_name)
    safe_footer_note = html.escape(footer_note)

    # Optional logo block
    logo_block = ""
    if (logo_url or "").strip():
        logo_block = f"""
          <tr>
            <td style="padding:0 0 12px 0; text-align:left;">
              <img src="{logo_url}" alt="{safe_brand_name}" height="28" style="display:block; height:28px; width:auto;">
            </td>
          </tr>
        """

    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_brand_name}</title>
  </head>

  <body style="margin:0; padding:0; background:#f6f7fb;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f7fb; padding:24px 0;">
      <tr>
        <td align="center" style="padding:0 12px;">
          <table role="presentation" width="600" cellspacing="0" cellpadding="0"
            style="max-width:600px; width:100%; background:#ffffff; border-radius:16px; overflow:hidden; border:1px solid #eef0f4;">
            
            <tr>
              <td style="padding:20px 22px; border-bottom:1px solid #eef0f4;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  {logo_block}
                  <tr>
                    <td style="font-family:Arial, Helvetica, sans-serif; font-size:18px; line-height:24px; font-weight:700; color:#0f172a;">
                      {safe_headline}{(" — " + safe_client_name) if safe_client_name else ""}
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-top:10px;">
                      <div style="height:4px; width:56px; background:{brand_color}; border-radius:999px;"></div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>

            <tr>
              <td style="padding:20px 22px; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:22px; color:#334155;">
                {message_html}
              </td>
            </tr>

            <tr>
              <td style="padding:0 22px 20px 22px;">
                <div style="border:1px solid #eef0f4; border-radius:12px; padding:12px 14px; background:#fbfdff;">
                  <div style="font-family:Arial, Helvetica, sans-serif; font-size:12px; line-height:18px; color:#64748b;">
                    {safe_footer_note}
                  </div>
                </div>
              </td>
            </tr>

            <tr>
              <td style="padding:14px 22px; background:#f8fafc; border-top:1px solid #eef0f4;">
                <div style="font-family:Arial, Helvetica, sans-serif; font-size:12px; color:#94a3b8; line-height:18px;">
                  Sent via <b>{safe_brand_name}</b> · {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
                </div>
              </td>
            </tr>

          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def plain_to_html(text: str) -> str:
    """
    Converts plain text to safe HTML with line breaks.
    """
    safe = html.escape(text or "")
    safe = safe.replace("\n", "<br>")
    return f"<div>{safe}</div>"
