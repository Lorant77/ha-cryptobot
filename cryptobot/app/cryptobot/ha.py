"""Home Assistant integráció a Supervisor API-n át: értesítés + szenzorok."""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)
BASE = "http://supervisor/core/api"


class HomeAssistant:
    def __init__(self, notify_service: str = ""):
        self.token = os.environ.get("SUPERVISOR_TOKEN", "")
        self.notify_service = notify_service.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _post(self, path: str, payload: dict) -> None:
        if not self.enabled:
            return
        try:
            r = requests.post(f"{BASE}{path}", json=payload, timeout=15,
                              headers={"Authorization": f"Bearer {self.token}"})
            r.raise_for_status()
        except Exception as exc:
            log.warning("HA API hívás sikertelen (%s): %s", path, exc)

    def notify(self, title: str, message: str) -> None:
        log.info("ÉRTESÍTÉS: %s – %s", title, message.replace("\n", " | "))
        if not self.notify_service:
            return
        service = self.notify_service.removeprefix("notify.")
        self._post(f"/services/notify/{service}", {"title": title, "message": message[:3500]})

    def sensor(self, name: str, state, attributes: dict | None = None) -> None:
        attrs = {"friendly_name": f"Crypto Bot {name.replace('_', ' ')}"}
        attrs.update(attributes or {})
        self._post(f"/states/sensor.cryptobot_{name}", {"state": state, "attributes": attrs})
