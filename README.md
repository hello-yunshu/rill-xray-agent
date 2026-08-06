# Rill Xray Agent

> 本地优先、fail-closed（默认关闭）的 Xray 管理脚本观测与决策支持代理。
> 包含可移植运行时（Runtime）、受限代理（Agent）、审计链、状态与事务恢复、备份安全、systemd 单元、Xray 宿主集成、测试、发布门禁与 AI execution instructions。

[English](./README_EN.md) · [文档目录](./docs/)

## 它是什么

Rill Xray Agent 是一个面向 Xray 管理脚本的本地观测与决策支持代理。它不接管 Xray 的配置所有权，只提供观测、审计与受限的决策支持能力，帮助你在 Xray 主机上获得可追踪、可回滚、可审计的操作记录。

## 安全默认

- 默认 `observe-only`（仅观测）模式
- 路由辅助（Route Assist）关闭
- 自动执行（bounded auto）关闭
- 不上传 Xray 配置，不采集用户密钥
- 配置校验、重载、回滚与服务生命周期始终由 Xray 宿主项目负责

## 组成

| 组件 | 说明 |
| --- | --- |
| `rill-xray-agent-runtime` | 拥有本地状态、审计链与决策生命周期 |
| `rill-xray-agent-agent` | 通过受限 Unix socket 暴露方法集 |
| Xray 适配器 | 仅输出哈希、大小、校验返回码与服务状态 |
| Python CLI | 提供 `status` / `health` / `metrics` / `config` / `snapshot` / `mode` / `inspect` 命令 |

## 快速开始

本地验证源码包：

```bash
python3 scripts/verify_package_tree.py
python3 scripts/verify_package_sums.py
python3 scripts/verify_project_memory.py
python3 scripts/run_all_checks.py
```

CLI 使用示例（默认 socket 为 `/run/rill-xray-agent/agent.sock`）：

```bash
rill-xray-agent --json status
rill-xray-agent --json snapshot
rill-xray-agent mode observe-only
```

## 文档

- [架构](./docs/ARCHITECTURE.md)
- [安全模型](./docs/SECURITY_MODEL.md)
- [使用说明](./docs/USAGE.md)
- [发布门禁](./docs/RELEASE_GATES.md)
- [项目记忆 / 状态](./PROJECT_MEMORY/01_CURRENT_STATE.md)

## 状态

当前为 **pre-release**（`v0.1.0-rc.1`），尚未正式发布。真实主机 systemd、Xray/Nginx/Fail2ban 及 ShellCheck 上线前资格验证仍为待办项。

## 许可证

[MIT](./LICENSE-MIT)