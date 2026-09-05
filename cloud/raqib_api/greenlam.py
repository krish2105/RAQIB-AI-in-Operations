"""Client for the Greenlam tracker API (existing project; schema from its repo).

Contract used (api/app/routers/tickets.py, schemas_tickets.py, routers/auth.py):
  POST /auth/login  {employee_id, pin}                -> {access_token, ...}
  POST /tickets     TicketCreate (Bearer)            -> TicketRead 201
      id?: UUID (client-generated, idempotent), machine_id: int,
      priority: Low|Medium|High|Critical, description, location?, downtime_type,
      raised_via: qr|manual|web, input_language: en|hi|hi-Latn, client_ts
We never duplicate its schema; we write tickets into it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx

from .config import settings

log = logging.getLogger(__name__)

PRIORITY = {1: "Low", 2: "Medium", 3: "Critical"}

# Retail shelves are not machines in the tracker. Until the pilot creates shelf
# assets, restock tasks map to a single "Shelf replenishment" pseudo-machine id
# configured per site. Default 0 means "unmapped" and is rejected by the tracker,
# which is the honest outcome.
SHELF_MACHINE_ID = 0


def priority_for_severity(sev: int) -> str:
    return PRIORITY.get(int(sev), "Medium")


def machine_id_for_shelf(shelf_id: str) -> int:
    return SHELF_MACHINE_ID


class GreenlamClient:
    def __init__(self, url: str, employee_id: str, pin: str, client: httpx.Client | None = None) -> None:
        self.url = url.rstrip("/")
        self.employee_id = employee_id
        self.pin = pin
        self.http = client or httpx.Client(timeout=10.0)
        self._token: str | None = None

    def login(self) -> str:
        r = self.http.post(f"{self.url}/auth/login", json={"employee_id": self.employee_id, "pin": self.pin,
                                                          "device_uid": "raqib-agent", "platform": "server"})
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self.login()
        return {"Authorization": f"Bearer {self._token}"}

    def raise_ticket(self, machine_id: int, description: str, priority: str = "Medium", location: str | None = None,
                     client_id: UUID | None = None, input_language: str = "en") -> dict:
        body = {
            "id": str(client_id or uuid4()),
            "machine_id": int(machine_id),
            "priority": priority,
            "description": description[:2000],
            "location": (location or None) and str(location)[:160],
            "downtime_type": "breakdown" if priority in ("High", "Critical") else "no_downtime",
            "raised_via": "web",
            "input_language": input_language,
            "client_ts": datetime.now(UTC).isoformat(),
        }
        r = self.http.post(f"{self.url}/tickets", json=body, headers=self._headers())
        if r.status_code == 401:  # token expired -> one retry
            self._token = None
            r = self.http.post(f"{self.url}/tickets", json=body, headers=self._headers())
        r.raise_for_status()
        data = r.json()
        return {"tracker": "greenlam", "ticket_id": data.get("id"), "ticket_no": data.get("ticket_no"),
                "stage": data.get("stage"), "machine_code": data.get("machine_code"), "priority": priority}


def client_from_settings(http: httpx.Client | None = None) -> GreenlamClient | None:
    if settings.greenlam_url and settings.greenlam_employee_id and settings.greenlam_pin:
        return GreenlamClient(settings.greenlam_url, settings.greenlam_employee_id, settings.greenlam_pin, http)
    return None
