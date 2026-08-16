# Changelog

## [Unreleased]

- 429 限流自动降级模型：`glm-4.6v-flash` → `glm-4v-flash`。
- 指数退避延长为 2s/4s/8s；限流重试耗尽返回可读错误。

## [0.1.0] - 2026-08-15

- 初始可安装版本：`pip install -e .` 后获得 `glm-vision` 命令入口。
- 服务名 `glm-vision`，模型 `glm-4.6v-flash`（免费，128K 上下文）。
- 对 429 限流与 5xx 服务端错误指数退避重试（1s/2s/4s，最多 3 次）。
- 测试：pytest 单元测试与 stdio 冒烟测试；GitHub Actions 覆盖 Python 3.10-3.12。
- 多客户端配置模板见 `examples/`。
- MIT 许可证。