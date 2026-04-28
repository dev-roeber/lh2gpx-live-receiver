from __future__ import annotations

import socket
import threading
import time
import re
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn

from app.config import Settings
from app.main import create_app
from app.models import LiveLocationPoint, LiveLocationRequest, RequestMetadata

playwright = pytest.importorskip("playwright.sync_api", reason="Playwright is optional for browser E2E tests")
sync_playwright = playwright.sync_playwright
expect = playwright.expect


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _settings(tmp_path: Path, port: int) -> Settings:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        bind_host="127.0.0.1",
        port=port,
        public_hostname="localhost",
        public_base_url=f"http://127.0.0.1:{port}",
        bearer_token=None,
        admin_username=None,
        admin_password=None,
        data_dir=data_dir,
        sqlite_path=tmp_path / "receiver.sqlite3",
        raw_payload_ndjson_path=data_dir / "raw.ndjson",
        legacy_request_ndjson_path=data_dir / "legacy.ndjson",
        raw_payload_ndjson_enabled=False,
        local_timezone="UTC",
        log_level="INFO",
        request_body_max_bytes=1024 * 1024,
        points_page_size_default=1000,
        points_page_size_max=200000,
        rate_limit_requests_per_minute=0,
        trust_proxy_headers=False,
    )


@pytest.mark.browser
def test_import_link_opens_map_with_active_import_filter(tmp_path: Path) -> None:
    port = _free_port()
    app = create_app(_settings(tmp_path, port))
    session_id = uuid4()
    payload = LiveLocationRequest(
        sessionID=session_id,
        source="import:e2e.json",
        captureMode="import",
        sentAt="2026-03-20T12:00:00Z",
        points=[
            LiveLocationPoint(
                latitude=52.52,
                longitude=13.405,
                timestamp="2026-03-20T12:00:00Z",
                horizontalAccuracyM=5.0,
            )
        ],
    )
    metadata = RequestMetadata(
        request_id="browser-e2e",
        received_at_utc=payload.sentAt,
        remote_addr="127.0.0.1",
        proxied_ip="",
        user_agent="test",
        request_path="/api/import",
        request_method="POST",
    )
    app.state.storage.ingest_success(payload, metadata, "{}")

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started

    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except Exception as exc:
                pytest.skip(f"Playwright Chromium is not installed: {exc}")
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/dashboard/import")
            link = page.locator('a[href*="/dashboard/map?import_session="]').first
            expect(link).to_be_visible()
            link.click()
            expect(page).to_have_url(re.compile(f"import_session={session_id}"))
            expect(page.locator("#import-filter-toggle")).to_be_checked()
            expect(page.locator("#import-select-dropdown")).to_have_value(str(session_id))
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
