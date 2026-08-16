# 多客户端配置示例

MCP 客户端的 server 声明主要有两种 JSON 格式：

| 客户端 | 格式 | 对应示例 |
|---|---|---|
| TRAE、Claude Desktop、Cline、Cursor、Cherry Studio 等 | 顶层 `mcpServers` | `mcpServers.example.json` |
| Z-Code（用户级 `~/.zcode/cli/config.json` 或工作区 `<repo>/.zcode/config.json`） | 嵌套 `mcp.servers` | `zcode.config.example.json` |

共用的填写要点：

- `<你的-Python-路径>`：换成安装了依赖的 Python（先 `pip install -e .`，或 `pip install "mcp>=1.2.0,<2" requests`）。
- `<GLM-vision-目录>`：本仓库克隆/解压后的绝对路径，例如 `C:/Users/me/GLM-vision`。
- `<你的-智谱-API-Key>`：在智谱开放平台（https://open.bigmodel.cn）申请；更安全的做法是留空，把 `ZHIPU_API_KEY` 写入系统环境变量。
- 发布到 PyPI 后，`command` 可直接写 `uvx`、`args` 写 `["glm-vision-mcp"]`，无需任何本地路径。