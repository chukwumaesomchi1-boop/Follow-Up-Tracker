# web/smart_templates.py

from __future__ import annotations

from typing import Any, Dict


SMART_TEMPLATE_LIBRARY = {
    "general_nudge_1": "Hi {{name}}, just checking in on your {{type}}.",
    "general_nudge_2": "Hi {{name}}, following up again on your {{type}}. Let me know if you need anything clarified.",
    "general_nudge_3": "Hi {{name}}, I wanted to make sure this {{type}} does not get missed.",
    "general_close_out": "Hi {{name}}, this is my final follow-up on your {{type}}. If you still need help, I’m here.",

    "sales_nudge_1": "Hi {{name}}, just following up to see if you had a chance to review this.",
    "sales_nudge_2": "Hi {{name}}, wanted to check back and answer any questions you may have.",
    "sales_nudge_3": "Hi {{name}}, I’m reaching out again in case timing was the only issue.",
    "sales_close_out": "Hi {{name}}, I’ll close this out for now, but feel free to reply anytime if you want to continue.",
}


def render_smart_template(template_key: str, context: Dict[str, Any]) -> str:
    template = SMART_TEMPLATE_LIBRARY.get(template_key) or SMART_TEMPLATE_LIBRARY["general_nudge_1"]

    result = template
    for key, value in context.items():
        result = result.replace("{{" + key + "}}", str(value or ""))

    return result