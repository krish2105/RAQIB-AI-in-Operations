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
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx

from .config import settings

log = logging.getLogger(__name__)


class CircuitOpen(RuntimeError):
    """The tracker failed repeatedly; calls are refused until the cooldown passes (then one probe is allowed)."""


class CircuitBreaker:
    """closed -> (N failures) -> open -> (cooldown) -> half-open (one probe) -> closed on success / open on failure."""

    def __init__(self, failures: int = 3, cooldown_s: float = 60.0, clock=time.monotonic) -> None:
        self.max_failures, self.cooldown_s, self.clock = failures, cooldown_s, clock
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        return "half_open" if self.clock() - self.opened_at >= self.cooldown_s else "open"

    def before(self) -> None:
        if self.state == "open":
            raise CircuitOpen(f"tracker circuit open for {self.cooldown_s - (self.clock() - self.opened_at):.0f} s more")

    def success(self) -> None:
        self.failures, self.opened_at = 0, None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.max_failures or self.state == "half_open":
            self.opened_at = self.clock()

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
    def __init__(self, url: str, employee_id: str, pin: str, client: httpx.Client | None = None, retries: int | None = None,
                 breaker: CircuitBreaker | None = None, sleep=time.sleep) -> None:
        self.url = url.rstrip("/")
        self.employee_id = employee_id
        self.pin = pin
        self.http = client or httpx.Client(timeout=10.0)
        self._token: str | None = None
        self.retries = retries if retries is not None else settings.greenlam_retries
        self.breaker = breaker or CircuitBreaker(settings.greenlam_breaker_failures, settings.greenlam_breaker_cooldown_s)
        self._sleep = sleep
        self._sent: dict[str, dict] = {}  # idempotency key -> result (the tracker also dedupes on the client-generated id)

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
        key = body["id"]
        if key in self._sent:  # same idempotency key -> same ticket, no second POST
            return {**self._sent[key], "deduplicated": True}
        self.breaker.before()
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                r = self.http.post(f"{self.url}/tickets", json=body, headers=self._headers())
                if r.status_code == 401:  # token expired -> one re-login
                    self._token = None
                    r = self.http.post(f"{self.url}/tickets", json=body, headers=self._headers())
                if r.status_code == 409:  # the tracker already has this id: treat as success
                    r = self.http.get(f"{self.url}/tickets/{key}", headers=self._headers())
                if 500 <= r.status_code < 600:
                    raise httpx.HTTPStatusError(f"tracker {r.status_code}", request=r.request, response=r)
                r.raise_for_status()
                data = r.json()
                out = {"tracker": "greenlam", "ticket_id": data.get("id"), "ticket_no": data.get("ticket_no"),
                       "stage": data.get("stage"), "machine_code": data.get("machine_code"), "priority": priority, "attempts": attempt}
                self._sent[key] = out
                self.breaker.success()
                return out
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    self.breaker.failure()
                    raise  # 4xx is our bug, not transient
                last = exc
                log.warning("greenlam attempt %d/%d failed: %s", attempt, self.retries, exc)
                if attempt < self.retries:
                    self._sleep(0.5 * 2 ** (attempt - 1))
        self.breaker.failure()
        raise last  # type: ignore[misc]


def client_from_settings(http: httpx.Client | None = None) -> GreenlamClient | None:
    if settings.greenlam_url and settings.greenlam_employee_id and settings.greenlam_pin:
        return GreenlamClient(settings.greenlam_url, settings.greenlam_employee_id, settings.greenlam_pin, http)
    return None
