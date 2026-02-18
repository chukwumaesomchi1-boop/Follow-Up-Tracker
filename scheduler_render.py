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

DEFAULT_SCHEDULER_TEMPLATE = """
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
        "brand_logo": (branding.get("logo") or "").strip(),
        "support_email": support_email,
        "footer": footer,
    }

    step1 = _render_conditionals(tmpl or "", data)
    step2 = _render_vars(step1, data)
    safe = _sanitize_html(step2)
    safe_wrapped = _wrap_personal_message(safe)

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; padding:16px;">
{safe_wrapped}
</body>
</html>"""
