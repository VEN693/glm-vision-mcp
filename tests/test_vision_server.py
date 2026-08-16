"""GLM Vision MCP Server 单元与冒烟测试。

对外部 HTTP 一律 mock，测试不依赖真实网络与 API Key；
测试图片用内存中的数据生成，不依赖仓库附属文件。
"""
import base64
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import vision_server as vs  # noqa: E402

# 1x1 透明 PNG，用于 _image_to_base64 测试
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
def _clean_api_key(monkeypatch):
    """清掉本机 .env 可能注入的 Key，保证测试结果确定。"""
    monkeypatch.setattr(vs, "API_KEY", "")


def _resp(status: int, content: str = "ok"):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    if status >= 400:
        r.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status} error"
        )
    return r


# --- _image_to_base64 ---


def test_image_to_base64_ok(tmp_path):
    img = tmp_path / "sample.png"
    img.write_bytes(_PNG_BYTES)
    data_url, mime = vs._image_to_base64(str(img))
    assert mime == "image/png"
    header, payload = data_url.split(",", 1)
    assert header == "data:image/png;base64"
    assert payload


def test_image_to_base64_missing_file():
    with pytest.raises(FileNotFoundError):
        vs._image_to_base64("C:/no/such/file.png")


# --- _call_glm ---


def test_call_glm_requires_key():
    with pytest.raises(RuntimeError, match="ZHIPU_API_KEY"):
        vs._call_glm("data:image/png;base64,AAAA", "prompt")


def test_call_glm_success(monkeypatch):
    monkeypatch.setattr(vs, "API_KEY", "sk-test")
    with mock.patch.object(vs.requests, "post", return_value=_resp(200)) as post:
        out = vs._call_glm("data:image/png;base64,AAAA", "描述一下")
    assert out == "ok"
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["model"] == vs.MODEL


def test_call_glm_retry_on_429_then_success(monkeypatch):
    monkeypatch.setattr(vs, "API_KEY", "sk-test")
    side = [_resp(429), _resp(200)]
    with (
        mock.patch.object(vs.requests, "post", side_effect=side) as post,
        mock.patch.object(vs.time, "sleep") as sleep,
    ):
        out = vs._call_glm("data:image/png;base64,AAAA", "p")
    assert out == "ok"
    assert post.call_count == 2
    sleep.assert_called_once()


def test_call_glm_retries_exhausted(monkeypatch):
    monkeypatch.setattr(vs, "API_KEY", "sk-test")
    side = [_resp(429), _resp(500), _resp(429), _resp(500)]
    with (
        mock.patch.object(vs.requests, "post", side_effect=side) as post,
        mock.patch.object(vs.time, "sleep") as sleep,
    ):
        with pytest.raises(requests.exceptions.HTTPError):
            vs._call_glm("data:image/png;base64,AAAA", "p")
    assert post.call_count == 4
    assert sleep.call_count == 3


def test_call_glm_api_error_payload(monkeypatch):
    monkeypatch.setattr(vs, "API_KEY", "sk-test")
    r = mock.Mock()
    r.status_code = 200
    r.json.return_value = {"error": {"message": "bad"}}
    with mock.patch.object(vs.requests, "post", return_value=r):
        with pytest.raises(RuntimeError, match="智谱"):
            vs._call_glm("data:image/png;base64,AAAA", "p")


# --- stdio 冒烟：握手 + 工具清单（无需网络 / Key） ---


def test_stdio_initialize_and_tools_list():
    reqs = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    proc = subprocess.run(
        [sys.executable, str(REPO / "vision_server.py")],
        input="\n".join(json.dumps(r) for r in reqs) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(REPO),
    )
    results = {}
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") is not None:
            results[msg["id"]] = msg
    assert results[1]["result"]["serverInfo"]["name"] == "glm-vision"
    tools = results[2]["result"]["tools"]
    assert "vision" in [t["name"] for t in tools]