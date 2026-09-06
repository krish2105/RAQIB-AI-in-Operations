"""WhatsApp Cloud API: approved message templates only, to an opt-in roster.

No free text ever reaches WhatsApp. `send_alert(template, lang, vars)` maps a RAQIB alert template to the
approved WhatsApp template name for that language and passes the variables as body parameters. Without
WHATSAPP_TOKEN / WHATSAPP_PHONE_ID the client is disabled and the alert stays on the console/webhook sinks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v21.0"
LANG_CODE = {"en": "en", "hi": "hi", "ar": "ar"}
# RAQIB alert template -> WhatsApp template name (approved in the Meta business account) and the ordered body params
TEMPLATES: dict[str, dict[str, Any]] = {
    "queue_over": {"name": "raqib_queue_over", "params": ["zone", "count", "time"]},
    "shelf_gap": {"name": "raqib_shelf_gap", "params": ["shelf_id", "product", "time"]},
    "zone_breach": {"name": "mushrif_zone_breach", "params": ["zone", "camera", "time"]},
    "ppe_violation": {"name": "mushrif_ppe_violation", "params": ["zone", "camera", "time"]},
    "machine_stopped": {"name": "mushrif_machine_stopped", "params": ["machine_id", "minutes"]},
    "escalation": {"name": "raqib_escalation", "params": ["role", "note", "event_id"]},
}


class TemplateOnly(ValueError):
    """Raised for any attempt to send text that is not an approved template."""


@dataclass(frozen=True)
class Recipient:
    phone: str  # E.164 without '+', as the Cloud API expects
    role: str
    lang: str = "en"


class WhatsAppClient:
    def __init__(self, phone_number_id: str | None = None, token: str | None = None, http: httpx.Client | None = None) -> None:
        self.phone_number_id = phone_number_id if phone_number_id is not None else settings.whatsapp_phone_id
        self.token = token if token is not None else settings.whatsapp_token
        self.http = http or httpx.Client(timeout=10.0)

    @property
    def enabled(self) -> bool:
        return bool(self.phone_number_id and self.token)

    def send(self, *args: Any, **kwargs: Any) -> None:
        raise TemplateOnly("free-text WhatsApp messages are not allowed; use send_template()")

    def send_text(self, *args: Any, **kwargs: Any) -> None:
        raise TemplateOnly("free-text WhatsApp messages are not allowed; use send_template()")

    def send_template(self, to: str, template: str, lang: str, vars: dict[str, Any]) -> dict[str, Any]:
        spec = TEMPLATES.get(template)
        if spec is None:
            raise TemplateOnly(f"{template!r} is not an approved WhatsApp template")
        if lang not in LANG_CODE:
            raise TemplateOnly(f"no approved template language {lang!r}")
        if not self.enabled:
            raise RuntimeError("WhatsApp is not configured (WHATSAPP_PHONE_ID, WHATSAPP_TOKEN)")
        params = [{"type": "text", "text": str(vars.get(k, "-"))[:120]} for k in spec["params"]]
        body = {"messaging_product": "whatsapp", "to": to, "type": "template",
                "template": {"name": spec["name"], "language": {"code": LANG_CODE[lang]},
                             "components": [{"type": "body", "parameters": params}]}}
        r = self.http.post(f"{GRAPH}/{self.phone_number_id}/messages", json=body, headers={"Authorization": f"Bearer {self.token}"})
        r.raise_for_status()
        data = r.json()
        return {"to": to, "template": spec["name"], "lang": lang, "message_id": (data.get("messages") or [{}])[0].get("id")}


def send_alert_to_roster(client: WhatsAppClient, recipients: list[Recipient], template: str, lang: str, vars: dict[str, Any],
                         role: str | None = None) -> list[dict[str, Any]]:
    """Send one approved template per opted-in recipient (optionally filtered by role), in the recipient's language."""
    out = []
    for rcp in recipients:
        if role and rcp.role != role:
            continue
        try:
            out.append(client.send_template(rcp.phone, template, rcp.lang or lang, vars))
        except (httpx.HTTPError, TemplateOnly, RuntimeError) as exc:
            log.warning("whatsapp send to %s failed: %s", rcp.phone[-4:], exc)
            out.append({"to": rcp.phone, "error": str(exc)[:160]})
    return out
