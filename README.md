# GLM-Vision MCP Server 使用与原理说明

一个基于智谱 GLM-4.6V-Flash 视觉模型的 MCP Server，作用是给纯文本大模型（例如 DeepSeek-V4-Flash、DeepSeek-V4-Pro）补上一双"眼睛"(视觉理解）：当主模型读不懂图片时，调用它把图片转成结构化文字描述和 OCR 文本，再回到主模型继续推理。

服务名固定为 `glm-vision`，不随模型版本变动。

---

## 一、这个 MCP 解决什么问题

绝大多数文本模型的输入接口只有文字，图片传进去会被忽略或直接报错。但实际工作中经常遇到"这张截图里写了什么""这个图表的结构是什么""这份 PDF 页面里有哪些元素"这类问题。

本 MCP 的思路是 **describe-first（先描述，再推理）**：不试图让文本模型直接"看"图，而是先用一个专用的视觉模型把图片翻译成文字，再把文字交给主模型继续做分析、写代码、回答问题。整个过程对主模型透明——它只看到一段返回的文字描述。

## 二、工作原理（数据是怎么流动的）

整个调用链路只有四个环节：

```
图片本地路径
    │  ① vision 工具被调用，传入 image_path 和 prompt
    ▼
vision_server.py（本机 stdio 进程）
    │  ② 读取图片字节，base64 编码，拼成 data URL
    ▼
智谱 GLM-4.6V-Flash API（https://open.bigmodel.cn）
    │  ③ 视觉模型看图，按 prompt 生成文字描述 / OCR
    ▼
结构化文字结果
    │  ④ 原样返回给主模型，主模型基于这段文字继续推理
    ▼
主模型输出最终答案
```

关键点解释：

- **stdio 传输**：MCP Server 以本地子进程方式运行，通过标准输入输出与客户端通信。启动命令写在 `mcp.json` 里，客户端（如 TRAE）负责拉起这个进程。
- **base64 编码**：图片文件不能直接发给 API，需要先编码成 `data:image/png;base64,xxxx` 这种 URL 格式，嵌入到请求 JSON 的 `image_url` 字段里。实测 GLM-4.6V-Flash 直接传纯 base64 字符串也能识别（官方文档推荐方式）。
- **FastMCP**：这是 MCP 官方 Python SDK 提供的高层封装，几行代码就能把一个普通 Python 函数暴露成 MCP 工具，不用手写 JSON-RPC 协议。

## 三、项目文件结构

| 文件 | 作用 |
|---|---|
| `vision_server.py` | MCP Server 主程序，唯一的实现文件，运行后暴露 `vision` 工具 |
| `pyproject.toml` | Python 打包配置；`pip install -e .` 后得到 `glm-vision` 命令入口 |
| `mcp.json` | 客户端侧的注册配置（模板，填路径与 Key 即可用） |
| `requirements.txt` | 传统 pip 依赖清单（`mcp` 1.x 和 `requests`） |
| `.env.example` | API Key 配置模板，复制成 `.env` 后填入真实的智谱 Key |
| `.gitignore` | 忽略 `.env`（含敏感 Key）、缓存与构建产物 |
| `test_image.png` | 本地测试图片，用于验证工具是否可用 |
| `tests/` | pytest 单元测试与 stdio 冒烟测试（不需要网络/Key） |
| `examples/` | Z-Code / TRAE / Claude Desktop 等多客户端配置模板 |
| `LICENSE` | MIT 开源许可 |
| `.github/workflows/ci.yml` | GitHub Actions 自动测试 |

## 四、核心代码解读

`vision_server.py` 一共四个部分，按顺序阅读：

1. **配置区**（约 32-50 行）：定义智谱 API 地址 `https://open.bigmodel.cn/api/paas/v4/chat/completions`、首选模型 `glm-4.6v-flash` 与降级模型 `glm-4v-flash`；从环境变量读取 `ZHIPU_API_KEY`，如果同目录有 `.env` 文件则自动加载其中的变量。`FastMCP("glm-vision")` 创建服务实例，`main()` 作为入口启动 stdio 服务。
2. **`_image_to_base64`**（56-65 行）：校验文件存在，用 `mimetypes` 推断图片类型，读字节、base64 编码，拼成 data URL。
3. **`_call_glm` / `_try_request`**（68-120 行）：组装 OpenAI 兼容格式的请求体（`messages` 里图文混合，图片在前、文字 prompt 在后），带 `Bearer` Key 调智谱接口，从返回的 `choices[0].message.content` 里取出文字结果。`_try_request` 对 429 限流与 5xx 服务端错误做指数退避重试（2s/4s/8s）；**429 重试耗尽后自动降级到 `glm-4v-flash` 再试一次**，两个模型都被限流则返回可读错误。
4. **`vision` 工具**（127-145 行）：用 `@mcp.tool()` 装饰器把函数暴露成 MCP 工具。参数 `image_path` 必填，`prompt` 可选，不填则使用默认的"描述 + OCR"指令。

一个必须注意的坑：**`mcp` 包要固定 1.x 版本**。`mcp` 2.x 是一次重大重构，移除了 `mcp.server.fastmcp`，代码会直接报 `ModuleNotFoundError`。所以 `pyproject.toml` / `requirements.txt` 都写成 `mcp>=1.2.0,<2`。

## 五、配置文件详解

`mcp.json` 是模板，机器相关的内容用占位符表示，填入即可使用（不同客户端的现成模板见 `examples/`）：

```json
{
  "mcpServers": {
    "glm-vision": {
      "command": "<你的-Python-路径>",
      "args": [
        "<本项目绝对路径>/vision_server.py"
      ],
      "env": {
        "ZHIPU_API_KEY": "<你的-智谱-API-Key>",
        "RUN_MCP_TIMEOUT_MS": "90000"
      }
    }
  }
}
```

字段含义：

| 字段 | 含义 |
|---|---|
| `mcpServers` | 固定顶层结构，下面可以挂多个 Server，每个一个名字 |
| `command` | 启动用的 Python 解释器路径（`python`、`py` 或绝对路径都行，需已装依赖） |
| `args` | 传给解释器的参数，这里是 `vision_server.py` 的绝对路径 |
| `env` | 传给子进程的环境变量；`ZHIPU_API_KEY` 是必须的智谱 Key，`RUN_MCP_TIMEOUT_MS` 是调用超时（毫秒），视觉模型推理较慢，默认可能不够用，这里放宽到 90 秒 |

在 TRAE 中使用时，把这份配置放进**项目根目录的 `.trae/mcp.json`**，然后在 设置 > MCP 里打开"启用项目级 MCP"开关即可。也可以在设置面板里"手动添加"粘贴同一份 JSON。Z-Code 使用嵌套 `mcp.servers` 结构（见 `examples/zcode.config.example.json`）。

## 六、使用前提：申请智谱 API Key

1. 打开智谱开放平台 <https://open.bigmodel.cn>，注册并登录。
2. 在「API Keys」页面创建一个 API Key（`glm-4.6v-flash` 属于免费模型，有免费额度）。
3. 在项目目录里执行 `copy .env.example .env`，把 `ZHIPU_API_KEY` 的值换成你自己的 Key：

```ini
ZHIPU_API_KEY=你的_智谱_API_Key_填在这里
```

`.env` 已被 `.gitignore` 忽略，不会误提交到版本库。如果不想用文件，也可以直接把 Key 写进 `mcp.json` 的 `env` 字段，或写入系统环境变量。

## 七、在其他环境手工搭建的完整步骤

给任何支持 MCP 的客户端（TRAE、Claude、Cline、Z-Code 等）重建这个 Server，按以下六步操作：

**第 1 步：准备 Python 环境。** 需要 Python 3.10 以上且能访问外网（要走智谱 API）。

**第 2 步：安装依赖。** 在项目目录执行：

```bash
pip install "mcp>=1.2.0,<2" requests
```

直接写 `pip install mcp` 装到 2.x 会失败，务必带上版本约束。本仓库也可以整体安装：`pip install -e .`，安装后可获得 `glm-vision` 命令入口。

**第 3 步：创建 `vision_server.py`。** 完整代码如下，原样保存即可：

```python
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
# 优先使用新模型；429 限流重试耗尽后自动降级到旧免费模型
MODEL = "glm-4.6v-flash"  # 首选：128K 上下文
FALLBACK_MODEL = "glm-4v-flash"  # 降级：免费档限流更宽松

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
    """调用视觉接口，返回文字结果。

    优先使用 MODEL；429 限流在本模型上重试耗尽后，自动降级到
    FALLBACK_MODEL 再试一次；两个模型都被限流则给出可读错误。
    """
    if not API_KEY:
        raise RuntimeError(
            "未设置 ZHIPU_API_KEY。请先注册智谱账号获取 key，"
            "并写入环境变量或本目录的 .env 文件。"
        )

    content = [
        {"type": "image_url", "image_url": {"url": image_data_url}},
        {"type": "text", "text": prompt},
    ]

    for model in (MODEL, FALLBACK_MODEL):
        payload = {"model": model, "messages": [{"role": "user", "content": content}]}
        resp = _try_request(payload, timeout)
        if resp is not None:
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"智谱 API 返回错误: {data['error']}")
            return data["choices"][0]["message"]["content"]

    raise RuntimeError("智谱接口持续限流(429)，glm-4.6v-flash 与 glm-4v-flash 均已重试，请稍后几分钟再试")


def _try_request(payload: dict, timeout: int, max_retries: int = 2, backoff: float = 2.0):
    """带退避地投递一次请求，返回可判定的 response。

    429 与 5xx 属瞬时故障，指数退避重试（2s/4s/8s）；
    429 重试耗尽返回 None（触发上层切换模型），5xx 重试耗尽抛错。
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    wait = backoff
    for attempt in range(max_retries + 1):
        resp = requests.post(
            ZHIPU_API_URL, headers=headers, json=payload, timeout=timeout
        )
        if resp.status_code != 429 and resp.status_code < 500:
            return resp
        if attempt == max_retries:
            if resp.status_code == 429:
                return None  # 限流重试耗尽，交给调用方切换模型
            resp.raise_for_status()
        time.sleep(wait)
        wait *= 2
    return None  # 不可达


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
```

**第 4 步：配置 API Key。** 按第六节创建 `.env` 文件，或把 `ZHIPU_API_KEY` 写入系统环境变量。

**第 5 步：编写并注册 `mcp.json`。** 参照第五节的模板，把 `command` 换成你自己环境的 Python 路径，`args` 换成 `vision_server.py` 的实际绝对路径（也可以直接使用 `examples/` 下的现成模板）。在客户端设置里的 MCP 面板「手动添加」，粘贴这份 JSON。TRAE 则直接把文件放到项目根目录的 `.trae/mcp.json` 并开启项目级 MCP。

**第 6 步：验证。** 在对话中让 AI 识别一张本地图片，例如"用 vision 工具识别 `你的-GLM-vision-目录/test_image.png`"。返回正常文字描述即搭建成功。

## 八、vision 工具调用说明

工具签名：`vision(image_path, prompt)`

| 参数 | 必填 | 说明 |
|---|---|---|
| `image_path` | 是 | 图片的本地绝对路径，支持 png / jpg / jpeg / webp 等常见格式 |
| `prompt` | 否 | 自定义识别指令；不填则使用默认的"详细描述 + 完整提取文字（OCR）+ 说明界面/图表结构与位置关系"指令 |

同一个 Server 未来要扩展能力，只需在 `vision_server.py` 里再写一个 `@mcp.tool()` 装饰的函数，重启服务即可暴露新工具，无需改动客户端配置。

## 九、常见问题排查

| 现象 | 原因与处理 |
|---|---|
| 报错"未设置 ZHIPU_API_KEY" | `.env` 没建或 Key 没填；检查文件与代码同目录、变量名拼写。改完需重启客户端里的 MCP 进程 |
| 报错 `ModuleNotFoundError: mcp.server.fastmcp` | `mcp` 装成了 2.x。执行 `pip install "mcp>=1.2.0,<2"` 降级 |
| 报错"找不到图片文件" | `image_path` 必须是绝对路径，且是运行 MCP 进程的那台机器上的路径（云端环境传本地路径会找不到） |
| 调用后长时间无响应或超时 | 视觉模型推理较慢，把 `mcp.json` 的 `RUN_MCP_TIMEOUT_MS` 调大（本项目为 90000） |
| 返回"网络错误 / Connection"类异常 | 本机或云端环境无法访问智谱接口；检查网络与代理设置 |
| 返回 "429 Too Many Requests" | 免费模型限流，属瞬时状态：脚本会自动退避（2s/4s/8s）并降级到 `glm-4v-flash` 重试；两个模型都被限流时稍等 1-2 分钟即可 |
| 中文出现乱码 | 文件必须保持 UTF-8 编码保存，尤其 Windows 下不要用 GBK |

## 十、安全与注意事项

- `ZHIPU_API_KEY` 属于敏感凭证：只写在 `.env`（已被 `.gitignore` 忽略）或环境变量里，不要写进代码、配置文件模板或提交到版本库。
- MCP Server 直接读取本机文件系统，只应加载可信来源的项目配置，避免恶意 `mcp.json` 被自动执行。
- 智谱 API 是远程第三方服务，调用会消耗其配额，是否免费及可用性以智谱官方说明为准，受网络与当地法律法规限制。
- 图片会以 base64 形式上传到智谱服务器进行识别，涉及敏感图片时请评估隐私风险。
