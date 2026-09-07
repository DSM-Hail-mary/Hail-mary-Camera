import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from Hail_Mary.edge.uplink import Uplink, build_occupancy_payload


def _sample_record(record_id, count=3):
    return {
        "id": record_id,
        "zone_id": "hall_main",
        "window_start": "2026-09-08T09:00:00Z",
        "window_end": "2026-09-08T09:01:00Z",
        "count": count,
    }


class _AcceptingHandler(BaseHTTPRequestHandler):
    received_bodies = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length)
        _AcceptingHandler.received_bodies.append(json.loads(body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"accepted": len(_AcceptingHandler.received_bodies[-1])}).encode())

    def log_message(self, *args):
        pass


class _FailingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(500)
        self.end_headers()

    def log_message(self, *args):
        pass


class _FlakyHandler(BaseHTTPRequestHandler):
    """Fails the first two requests, then succeeds -- a real server with real
    stateful behavior, not a simulated/mocked failure."""
    request_count = 0

    def do_POST(self):
        _FlakyHandler.request_count += 1
        length = int(self.headers["Content-Length"])
        self.rfile.read(length)
        if _FlakyHandler.request_count < 3:
            self.send_response(500)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"accepted": 1}).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def real_http_server():
    def _start(handler_cls):
        server = HTTPServer(("127.0.0.1", 0), handler_cls)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    servers = []

    def factory(handler_cls):
        server = _start(handler_cls)
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}/api/v1/occupancy"

    yield factory

    for server in servers:
        server.shutdown()


def test_build_occupancy_payload_strips_local_id():
    records = [_sample_record(1, count=3), _sample_record(2, count=5)]

    payload = build_occupancy_payload(records)

    assert payload == [
        {"zone_id": "hall_main", "window_start": "2026-09-08T09:00:00Z",
         "window_end": "2026-09-08T09:01:00Z", "count": 3},
        {"zone_id": "hall_main", "window_start": "2026-09-08T09:00:00Z",
         "window_end": "2026-09-08T09:01:00Z", "count": 5},
    ]


def test_upload_batch_succeeds_against_a_real_server(real_http_server):
    _AcceptingHandler.received_bodies = []
    url = real_http_server(_AcceptingHandler)

    uplink = Uplink(url)
    result = uplink.upload_batch([_sample_record(1), _sample_record(2)])

    assert result.success is True
    assert result.uploaded_ids == [1, 2]
    assert len(_AcceptingHandler.received_bodies) == 1
    assert len(_AcceptingHandler.received_bodies[0]) == 2


def test_upload_batch_with_no_records_is_a_no_op(real_http_server):
    url = real_http_server(_AcceptingHandler)
    uplink = Uplink(url)

    result = uplink.upload_batch([])

    assert result.success is True
    assert result.uploaded_ids == []


def test_upload_batch_reports_failure_on_server_error(real_http_server):
    url = real_http_server(_FailingHandler)
    uplink = Uplink(url, max_retries=1, backoff_seconds=0.01)

    result = uplink.upload_batch([_sample_record(1)])

    assert result.success is False
    assert result.uploaded_ids == []


def test_upload_batch_reports_failure_on_connection_error():
    # Nothing listens on this port -> a real ConnectionError, not a simulated one.
    uplink = Uplink("http://127.0.0.1:1/api/v1/occupancy", max_retries=1, backoff_seconds=0.01)

    result = uplink.upload_batch([_sample_record(1)])

    assert result.success is False
    assert result.uploaded_ids == []


def test_upload_batch_retries_and_eventually_succeeds(real_http_server):
    _FlakyHandler.request_count = 0
    url = real_http_server(_FlakyHandler)
    uplink = Uplink(url, max_retries=5, backoff_seconds=0.01)

    result = uplink.upload_batch([_sample_record(1)])

    assert result.success is True
    assert result.uploaded_ids == [1]
    assert _FlakyHandler.request_count == 3
