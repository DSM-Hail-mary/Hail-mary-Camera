"""HTTP uplink for a zone's "last seen" image (M2 exception, see
문서/제안서.md 9장 / 문서/개발_기능명세서.md M2).

Uploads the single frame captured at the moment a zone transitions from
occupied to empty (LastSeenTracker.update() returning True). Server keeps
only the most recent image per zone -- this is a plain multipart POST, not
a batch/queue, following the same std-lib-only urllib.request style as
uplink.py.
"""

import urllib.error
import urllib.parse
import urllib.request
import uuid

from Hail_Mary.edge.last_seen import is_valid_zone_id

_BOUNDARY_PREFIX = "hail-mary-last-seen-boundary-"


def _build_multipart_body(image_bytes: bytes, boundary: str) -> bytes:
    parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="image"; filename="last_seen.jpg"\r\n',
        b"Content-Type: image/jpeg\r\n\r\n",
        image_bytes,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts)


def upload_last_seen_image(base_url: str, zone_id: str, image_bytes: bytes, timeout: float = 5.0) -> bool:
    # zone_id comes straight from --zone-id/zone.json (calibrate.py), never
    # validated before this -- reject anything that could escape the URL
    # path (path traversal) before attempting a request, and percent-encode
    # whatever's left so a legal-but-unusual zone_id (spaces, unicode) can't
    # produce a malformed request line.
    if not is_valid_zone_id(zone_id):
        return False

    boundary = f"{_BOUNDARY_PREFIX}{uuid.uuid4().hex}"
    body = _build_multipart_body(image_bytes, boundary)
    url = f"{base_url}/api/v1/last-seen/{urllib.parse.quote(zone_id, safe='')}"

    request = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, ConnectionError, OSError):
        return False
