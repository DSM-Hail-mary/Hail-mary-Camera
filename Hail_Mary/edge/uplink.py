"""HTTP batch uplink for occupancy records (M3).

Reads pending rows from buffer.py and POSTs them to the server in one batch.
Payload assembly is isolated in build_occupancy_payload() so a server schema
change only requires touching this one function.
"""

import json
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UploadResult:
    success: bool
    uploaded_ids: list[int] = field(default_factory=list)


def build_occupancy_payload(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assumed contract (unconfirmed with the server): a JSON array of
    {zone_id, window_start, window_end, count}. The local-only `id` is
    stripped before sending."""
    return [
        {
            "zone_id": record["zone_id"],
            "window_start": record["window_start"],
            "window_end": record["window_end"],
            "count": record["count"],
        }
        for record in records
    ]


class Uplink:
    def __init__(self, endpoint_url: str, max_retries: int = 3, backoff_seconds: float = 1.0) -> None:
        self.endpoint_url = endpoint_url
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def upload_batch(self, records: Sequence[dict[str, Any]]) -> UploadResult:
        if not records:
            return UploadResult(success=True, uploaded_ids=[])

        body = json.dumps(build_occupancy_payload(records)).encode()
        ids = [record["id"] for record in records]

        delay = self.backoff_seconds
        for attempt in range(self.max_retries):
            if self._post(body):
                return UploadResult(success=True, uploaded_ids=ids)
            if attempt < self.max_retries - 1:
                time.sleep(delay)
                delay *= 2

        return UploadResult(success=False, uploaded_ids=[])

    def _post(self, body: bytes) -> bool:
        request = urllib.request.Request(
            self.endpoint_url, data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, ConnectionError, OSError):
            return False
