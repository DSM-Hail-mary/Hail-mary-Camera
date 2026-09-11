import cgi
import io
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from Hail_Mary.edge.last_seen_uplink import upload_last_seen_image

SAMPLE_JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-bytes-for-test\xff\xd9"


class _AcceptingHandler(BaseHTTPRequestHandler):
    received_paths: list[str] = []
    received_images: list[bytes] = []

    def do_POST(self):
        _AcceptingHandler.received_paths.append(self.path)
        content_type = self.headers["Content-Type"]
        length = int(self.headers["Content-Length"])
        form = cgi.FieldStorage(
            fp=io.BytesIO(self.rfile.read(length)),
            headers=self.headers,
            environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
        )
        _AcceptingHandler.received_images.append(form["image"].file.read())
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


class _FailingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.rfile.read(length)
        self.send_response(500)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def real_http_server():
    servers = []

    def factory(handler_cls):
        server = HTTPServer(("127.0.0.1", 0), handler_cls)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}"

    yield factory

    for server in servers:
        server.shutdown()


def test_upload_last_seen_image_succeeds_against_a_real_server(real_http_server):
    _AcceptingHandler.received_paths = []
    _AcceptingHandler.received_images = []
    base_url = real_http_server(_AcceptingHandler)

    result = upload_last_seen_image(base_url, "hall_main", SAMPLE_JPEG_BYTES)

    assert result is True
    assert _AcceptingHandler.received_paths == ["/api/v1/last-seen/hall_main"]
    assert _AcceptingHandler.received_images == [SAMPLE_JPEG_BYTES]


def test_upload_last_seen_image_returns_false_on_server_error(real_http_server):
    base_url = real_http_server(_FailingHandler)

    result = upload_last_seen_image(base_url, "hall_main", SAMPLE_JPEG_BYTES)

    assert result is False


def test_upload_last_seen_image_returns_false_on_connection_error():
    # Nothing listens on this port -> a real ConnectionError, not a simulated one.
    result = upload_last_seen_image("http://127.0.0.1:1", "hall_main", SAMPLE_JPEG_BYTES, timeout=0.5)

    assert result is False


def test_upload_last_seen_image_rejects_path_traversal_zone_id_without_a_request(real_http_server):
    # Code review 2026-09-11: zone_id was spliced into the URL unvalidated
    # (f"{base_url}/api/v1/last-seen/{zone_id}") -- a zone_id containing
    # "../" would misroute the request entirely. No network call should even
    # be attempted for an invalid zone_id.
    _AcceptingHandler.received_paths = []
    base_url = real_http_server(_AcceptingHandler)

    result = upload_last_seen_image(base_url, "../escape", SAMPLE_JPEG_BYTES)

    assert result is False
    assert _AcceptingHandler.received_paths == []


def test_upload_last_seen_image_url_encodes_zone_id_with_special_characters(real_http_server):
    # A zone_id built via plain f-string interpolation (no urllib.parse.quote)
    # would send a malformed/misrouted request line for characters like
    # spaces. zone_id itself stays a legal filename-ish token per
    # is_valid_zone_id(), but must still round-trip safely through a URL.
    _AcceptingHandler.received_paths = []
    _AcceptingHandler.received_images = []
    base_url = real_http_server(_AcceptingHandler)

    result = upload_last_seen_image(base_url, "hall main", SAMPLE_JPEG_BYTES)

    assert result is True
    assert _AcceptingHandler.received_paths == ["/api/v1/last-seen/hall%20main"]
