import asyncio
from pathlib import Path
from typing import Any

from after_sales_agents.api import app


async def _asgi_get(path: str) -> tuple[int, dict[str, str], bytes]:
    messages: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    headers = {key.decode("latin-1"): value.decode("latin-1") for key, value in start["headers"]}
    body = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    return start["status"], headers, body


def _get(path: str) -> tuple[int, dict[str, str], bytes]:
    return asyncio.run(_asgi_get(path))


def _ui_directory() -> Path:
    return Path(__file__).parents[1] / "src" / "after_sales_agents" / "ui"


def test_root_redirects_to_operator_workbench() -> None:
    status, headers, _ = _get("/")

    assert status == 307
    assert headers["location"] == "/ui"


def test_operator_workbench_is_served_as_html() -> None:
    status, headers, body = _get("/ui")
    html = body.decode("utf-8")

    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert "售后协作控制台" in html
    assert "工单对话" in html
    assert "智能体协作时间线" in html
    assert "订单事实证据" in html
    assert "政策引用" in html
    assert "独立审核检查" in html
    assert "批准" in html and "修改" in html and "拒绝" in html
    assert "状态差异" in html
    assert "无真实写操作" in html


def test_static_assets_are_served_without_external_frontend_dependencies() -> None:
    css_status, css_headers, css = _get("/ui/assets/app.css")
    js_status, js_headers, javascript = _get("/ui/assets/app.js")
    html = (_ui_directory() / "index.html").read_text(encoding="utf-8")

    assert css_status == 200
    assert css_headers["content-type"].startswith("text/css")
    assert b".main-grid" in css
    assert js_status == 200
    assert "javascript" in js_headers["content-type"]
    assert b"runWorkflow" in javascript
    assert "https://" not in html and "http://" not in html


def test_ui_uses_only_existing_review_apis_and_never_calls_write_tools() -> None:
    javascript = (_ui_directory() / "assets" / "app.js").read_text(encoding="utf-8")

    assert 'postJson("/api/v1/planning/review"' in javascript
    assert 'postJson("/api/v1/review/audit"' in javascript
    assert 'postJson("/api/v1/review/decision"' in javascript
    assert 'postJson("/api/v1/review/verify-state"' in javascript
    assert "cancel_pending_order" not in javascript
    assert "return_delivered_order_items" not in javascript
    assert "exchange_delivered_order_items" not in javascript
    assert "can_execute_now" in javascript
    assert "write_executed" in javascript
    assert "simulatedSnapshots" in javascript


def test_ui_routes_are_deliberately_hidden_from_business_openapi() -> None:
    paths = app.openapi()["paths"]
    major, minor, *_ = (int(part) for part in app.version.split("."))

    assert (major, minor) >= (0, 6)
    assert "/" not in paths
    assert "/ui" not in paths
    assert "/api/v1/planning/review" in paths
    assert "/api/v1/review/decision" in paths
