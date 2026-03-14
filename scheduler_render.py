# web/scheduler_render.py
from __future__ import annotations

import re
from typing import Any, Mapping

import bleach

# scheduler_render.py

PERSONAL_MESSAGE_WRAPPER = """
<div style="
  font-family: Arial, sans-serif;
  font-size: 14px;
  color: #111;
  line-height: 1.6;
">
  <div style="
    max-width: 600px;
    margin: 0 auto;
    padding: 16px;
  ">
    {{content}}
  </div>
</div>
""".strip()

# DEFAULT_SCHEDULER_TEMPLATE = """
# <div style="font-family:Arial,sans-serif; font-size:14px; color:#111;">
#   {% if brand_logo %}
#     <div style="margin-bottom:10px;">
#       "brand_logo": (branding.get("brand_logo") or "").strip(), style="height:36px">
#     </div>
#   {% endif %}

#   <p>Hi {{name}},</p>
#   <p>Just a quick reminder about {{type}}.</p>

#   {% if description %}
#     <p>{{description}}</p>
#   {% endif %}

#   {% if due_date %}
#     <p><b>Due date:</b> {{due_date}}</p>
#   {% endif %}

#   <p>Thanks,<br>{{sender}}</p>

#   {% if footer %}
#     <hr>
#     <small style="color:#64748b;">{{footer}}</small>
#   {% endif %}
# </div>
# """.strip()



DEFAULT_SCHEDULER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Notification</title>
</head>
<body style="margin:0; padding:0; background-color:#f8fafc; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">

<table width="100%" border="0" cellpadding="0" cellspacing="0" style="background-color:#f8fafc; padding: 40px 10px;">
  <tr>
    <td align="center">
      
      <table width="100%" border="0" cellpadding="0" cellspacing="0" style="max-width:600px; background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); border: 1px solid #e2e8f0;">
        
        <tr>
          <td style="padding: 32px 32px 24px 32px; text-align: center;">
            <img src="{{brand_logo}}" alt="{{company_name}}" style="max-width: 140px; height: auto; outline: none; border: none; text-decoration: none;">
          </td>
        </tr>

        <tr>
          <td style="padding: 0 40px 40px 40px;">
            <h2 style="margin: 0 0 16px 0; color: #1e293b; font-size: 20px; font-weight: 700; line-height: 1.4;">
              Hi {{name}},
            </h2>
            <p style="margin: 0 0 24px 0; color: #475569; font-size: 16px; line-height: 1.6;">
              This is a friendly reminder regarding your upcoming schedule. Please see the details of your <strong>{{type}}</strong> below:
            </p>

            <table width="100%" border="0" cellpadding="0" cellspacing="0" style="background-color: #f1f5f9; border-radius: 8px; margin-bottom: 24px;">
              <tr>
                <td style="padding: 20px;">
                  <table width="100%" border="0" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="color: #64748b; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; padding-bottom: 4px;">Event Type</td>
                    </tr>
                    <tr>
                      <td style="color: #0f172a; font-size: 16px; font-weight: 600; padding-bottom: 16px;">{{type}}</td>
                    </tr>
                    {% if due_date %}
                    <tr>
                      <td style="color: #64748b; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; padding-bottom: 4px;">Due Date</td>
                    </tr>
                    <tr>
                      <td style="color: #0f172a; font-size: 16px; font-weight: 600;">{{due_date}}</td>
                    </tr>
                    {% endif %}
                  </table>
                </td>
              </tr>
            </table>

            <p style="margin: 0; color: #475569; font-size: 15px; line-height: 1.6;">
              Best regards,<br>
              <span style="color: #1e293b; font-weight: 600;">{{sender}}</span>
            </p>
          </td>
        </tr>

        <tr>
          <td style="padding: 24px 40px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center;">
            <p style="margin: 0; font-size: 12px; color: #94a3b8; line-height: 1.5;">
              &copy; {{company_name}} <br>
              This is an automated notification. Please do not reply directly to this email.
            </p>
          </td>
        </tr>

      </table>

    </td>
  </tr>
</table>

</body>
</html>
""".strip()


_ALLOWED_VARS = {
    "name",
    "type",
    "description",
    "sender",
    "company_name",
    "due_date",
    "brand_logo",
    "support_email",
    "footer",
    "content",  # for PERSONAL_MESSAGE_WRAPPER
}

_IF_OPEN_RE = re.compile(r"{%\s*if\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*%}")
_IF_CLOSE_RE = re.compile(r"{%\s*endif\s*%}")
_VAR_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def _truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    return bool(v)


def _render_conditionals(src: str, data: Mapping[str, Any]) -> str:
    """
    Safe subset:
      - {% if var %} ... {% endif %}  (var must be in _ALLOWED_VARS)
    Any unknown control tag is stripped.
    Nested ifs supported.
    """
    out: list[str] = []
    stack: list[bool] = [True]  # include flags

    lines = src.splitlines(True)  # keep newlines
    for line in lines:
        m_open = _IF_OPEN_RE.search(line)
        m_close = _IF_CLOSE_RE.search(line)

        if m_open:
            var = m_open.group(1)
            if var in _ALLOWED_VARS:
                include = stack[-1] and _truthy(data.get(var))
                stack.append(include)
            else:
                # unknown var => treat as False (and keep nesting consistent)
                stack.append(False)
            continue

        if m_close:
            if len(stack) > 1:
                stack.pop()
            continue

        # Normal line: include only if all parents included
        if stack[-1]:
            out.append(line)

    return "".join(out)


def _render_vars(src: str, data: Mapping[str, Any]) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key not in _ALLOWED_VARS:
            return ""  # unknown vars disappear
        v = data.get(key)
        return "" if v is None else str(v)

    return _VAR_RE.sub(repl, src)



# import bleach
# from bleach.css_sanitizer import CSSSanitizer

# def _sanitize_html(html: str) -> str:
#     allowed_tags = [
#         "div",
#         "p",
#         "br",
#         "b",
#         "strong",
#         "i",
#         "em",
#         "ul",
#         "ol",
#         "li",
#         "span",
#         "small",
#         "h1",
#         "h2",
#         "h3",
#         "h4",
#         "a",
#         "img",
#         "hr",
#         "table",
#         "thead",
#         "tbody",
#         "tr",
#         "th",
#         "td",
#     ]

#     allowed_attrs = {
#         "*": ["style"],
#         "a": ["href", "target", "rel"],
#         "img": ["src", "alt", "width", "height", "style"],
#     }

#     css_sanitizer = CSSSanitizer(
#         allowed_css_properties=[
#             "background",
#             "background-color",
#             "color",
#             "font-family",
#             "font-size",
#             "font-weight",
#             "line-height",
#             "text-align",
#             "padding",
#             "padding-top",
#             "padding-right",
#             "padding-bottom",
#             "padding-left",
#             "margin",
#             "margin-top",
#             "margin-right",
#             "margin-bottom",
#             "margin-left",
#             "border",
#             "border-top",
#             "border-right",
#             "border-bottom",
#             "border-left",
#             "border-radius",
#             "width",
#             "max-width",
#             "height",
#             "display",
#             "vertical-align",
#             "letter-spacing",
#             "text-transform",
#             "box-shadow",
#             "overflow",
#             "text-decoration",
#         ]
#     )

#     cleaned = bleach.clean(
#         html,
#         tags=allowed_tags,
#         attributes=allowed_attrs,
#         css_sanitizer=css_sanitizer,
#         strip=True,
#     )
#     return cleaned


def _sanitize_html(html: str) -> str:
    # tight allowlist: tweak if you need more tags
    allowed_tags = [
        "div",
        "p",
        "br",
        "b",
        "strong",
        "i",
        "em",
        "ul",
        "ol",
        "li",
        "span",
        "small",
        "h1",
        "h2",
        "h3",
        "h4",
        "a",
        "img",
        "hr",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
    ]
    allowed_attrs = {
        "*": ["style"],
        "a": ["href", "target", "rel"],
        "img": ["src", "alt", "width", "height", "style"],
    }

    # allow inline styles but strip dangerous protocols/attrs
    cleaned = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True,
    )
    cleaned = bleach.linkify(cleaned)
    return cleaned


def _wrap_personal_message(inner_html: str) -> str:
    # inner_html is already sanitized before wrapping
    wrapped = PERSONAL_MESSAGE_WRAPPER.replace("{{content}}", inner_html)
    # sanitize again after wrapping (belt + suspenders)
    return _sanitize_html(wrapped)


import bleach

# Assuming these exist elsewhere in your codebase:
# - PERSONAL_MESSAGE_WRAPPER: str  (must include "{{content}}" placeholder)
# - _render_conditionals(tmpl: str, data: dict) -> str
# - _render_vars(tmpl: str, data: dict) -> str
# - _sanitize_html(html: str) -> str
# - _wrap_personal_message(html: str) -> str


def render_scheduler_html(tmpl: str, user: dict, followup: dict, branding: dict) -> str:
    sender = (branding.get("company_name") or "").strip() or "Your Company"
    support_email = (branding.get("support_email") or "").strip()
    footer = (branding.get("footer") or "").strip()

    if support_email and not footer:
        footer = f"Need help? Contact {support_email}"


    message_override = (followup.get("message_override") or "").strip()
    if message_override:
        safe_body = bleach.clean(
            message_override.replace("\n", "<br>"),
            tags=[
                "b", "strong", "i", "em", "u", "br", "p", "ul", "ol", "li",
                "div", "span", "a"
            ],
            attributes={"a": ["href", "target", "rel"]},
            strip=True,
        )

        html = PERSONAL_MESSAGE_WRAPPER.replace("{{content}}", safe_body)

        return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>{html}</body>
</html>"""

    # ✅ Normal template render: description is just a variable inside the template
    data = {
        "name": (followup.get("client_name") or "there").strip(),
        "type": (followup.get("followup_type") or "follow-up").strip(),
        "description": (followup.get("description") or "").strip(),
        "due_date": (followup.get("due_date") or "").strip(),
        "sender": sender,
        "company_name": sender,
        "brand_logo": (branding.get("brand_logo") or "").strip(),
        "support_email": support_email,
        "footer": footer,
    }

    step1 = _render_conditionals(tmpl or "", data)
    step2 = _render_vars(step1, data)
    safe = _sanitize_html(step2)
    return safe
