"""
GLM-4.6V-Flash 视觉 MCP Server
==============================
为纯文本模型提供视觉理解能力（图片 → 结构化文字/OCR）。

工作原理（describe-first 管线）：
    图片路径 -> 本工具读取并 base64 编码 -> 调用智谱 GLM-4.6V-Flash 视觉 API
              -> 得到结构化文字描述/OCR -> 返回到主模型继续推理

使用前提：
    1. 已注册智谱 BigModel 账号并创建 API key（免费）。
    2. 将 key 写入环境变量 ZHIPU_API_KEY（或本文件同目录的 .env）。

启动方式：
    python vision_server.py          # 直接以 stdio 模式运行
    glm-vision                        # pip 安装后的命令入口（见 pyproject.toml）
"""

from __future__ import annotations

import base64
import mimetypes
import os
import sys
import time
from pathlib import Path

import requests
from mcp.server.fastmcp import FastMCP  # 官方 Python SDK

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6v-flash"  # 免费模型，能力全面超过旧版 glm-4v-flash（128K 上下文、原生 Function Calling）

# 从环境变量读取 key；若同目录存在 .env，则自动加载
_DOT_ENV = Path(__file__).resolve().parent / ".env"
if _DOT_ENV.exists():
    for line in _DOT_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.getenv("ZHIPU_API_KEY", "")

mcp = FastMCP("glm-vision")


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------
def _image_to_base64(image_path: str) -> tuple[str, str]:
    """读取图片并返回 (data_url, mime)。"""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"找不到图片文件: {image_path}")

    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{b64}", mime


def _call_glm(image_data_url: str, prompt: str, timeout: int = 60) -> str:
    """调用 GLM-4.6V-Flash 视觉接口，返回文字结果。

    免费模型偶发 429 限流与 5xx 服务端错误，属瞬时故障，
    这里做最多 3 次指数退避重试（1s/2s/4s），仍失败才抛错。
    """
    if not API_KEY:
        raise RuntimeError(
            "未设置 ZHIPU_API_KEY。请先注册智谱账号获取 key，"
            "并写入环境变量或本目录的 .env 文件。"
        )

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    # 429 限流与 5xx 服务端错误属瞬时故障，指数退避重试（1s/2s/4s）
    max_retries = 3
    backoff = 1.0
    for attempt in range(max_retries + 1):
        resp = requests.post(
            ZHIPU_API_URL, headers=headers, json=payload, timeout=timeout
        )
        if resp.status_code != 429 and resp.status_code < 500:
            break
        if attempt == max_retries:
            break  # 重试耗尽，由下方 raise_for_status 抛出
        time.sleep(backoff)
        backoff *= 2

    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"智谱 API 返回错误: {data['error']}")

    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# MCP 工具定义
# ---------------------------------------------------------------------------
@mcp.tool()
def vision(
    image_path: str,
    prompt: str = (
        "请详细描述这张图片。如果图片中包含文字，请完整提取所有可见文字；"
        "如果包含界面、图表或表格，请说明其结构、关键元素和位置关系。"
        "请用结构化、客观的语言输出，方便后续文本模型基于你的描述继续分析和推理。"
    ),
) -> str:
    """识别一张图片，返回结构化文字描述与 OCR 文字。

    适用于截图、文档、图表、照片等。当主文本模型无法直接读取图片、
    或需要把图片内容转成文字再交给纯文本模型推理时，调用本工具。

    参数:
        image_path: 图片的本地绝对路径（支持 png/jpg/jpeg/webp 等常见格式）。
        prompt: 可选，自定义识别指令；不填则使用默认的"描述+OCR"指令。
    """
    data_url, _ = _image_to_base64(image_path)
    return _call_glm(data_url, prompt)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main() -> None:
    """以 stdio 模式启动 MCP Server（pip 安装后 `glm-vision` 命令即调用本函数）。"""
    if not API_KEY:
        print("警告: 未检测到 ZHIPU_API_KEY，工具调用将失败。请先配置 key。", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()