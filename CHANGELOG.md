# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-08-15

首个可打包发布版本：

- 新增 `pyproject.toml`，`pip install -e .` 后获得 `glm-vision` 命令入口（等价 `python vision_server.py`）。
- 服务名正式定为 `glm-vision`（不随底层模型版本变动）。
- 视觉模型为智谱免费模型 `glm-4.6v-flash`（128K 上下文）。
- 内置对 429 限流与 5xx 服务端错误的指数退避重试（1s/2s/4s，最多 3 次）。
- 新增 `pytest` 单元测试与 stdio 冒烟测试、GitHub Actions CI（Python 3.10-3.12）。
- 新增 `examples/` 多客户端配置模板（Z-Code / TRAE / Claude Desktop 等）。
- MIT 许可证。