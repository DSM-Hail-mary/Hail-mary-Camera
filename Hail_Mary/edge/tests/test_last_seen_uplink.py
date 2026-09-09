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
