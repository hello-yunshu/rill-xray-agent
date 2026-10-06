# Rill canonical source audit fix (XRA-01–05, XRA-07–09)

基于固定基线 `48b19f585df2b89e49ecd99a0714f00f086bb12f`，在分支 `fix/audit-rill-agent-safety` 完成源头阶段 1/2 修复。修复仅在此源头和其既有 Xray 消费镜像中生成；未合并、未发布、未部署，也未开启 routeAssist/boundedAuto。

## 问题、修改与回归

| ID | 修改 | 回归与结果 |
|---|---|---|
| XRA-01 | `python/rill_xray_agent/rillml_artifact.py`：单一绝对 deadline 覆盖握手/health；selector 非阻塞 IPC、有界 NDJSON 行、受限 stderr/stdout、进程组超时终止，校验 requestId/API/kind/health。 | `tests/test_rillml_safety.py` 精确 IPC 行上限、超限、EOF/坏 JSON和慢进程超时终止；RillML 全既有模块通过。真实已发布 runtime 端到端验证未执行。 |
| XRA-02 | 同文件：响应流分块写入临时文件，只读取上限 + 1；预检 Content-Length、拒绝 HTTPS 降级重定向、全重试共用 deadline，摘要/尺寸核验后原子发布。 | 新回归验证上限 + 1 与 Content-Length 零读取、HTTP 降级拒绝；既有下载校验用例通过。未访问生产发布服务。 |
| XRA-03 | 同文件：进程内锁 + POSIX 文件锁；事务日志、状态快照、安装/回滚互斥及崩溃恢复；只报告验证过的当前/回滚组件。 | `tests/test_rillml_artifact.py` 的现有安装、失败探测、回滚、重装用例通过。多进程故障注入完整矩阵未执行。 |
| XRA-04 | 同文件：核对二进制普通文件类型、大小、摘要、发布者及平台/API 元数据；旧状态或 tamper 状态不作为 verified 组件复用。 | checksum mismatch/损坏安装既有用例通过。 |
| XRA-05 | `integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_install.sh`：候选 payload 预校验，持久化升级快照与 prepared/committed 标记，错误/信号恢复 managed payload、unit 状态及工作模式；升级无论成功失败都撤销旧 auto 确认。 | `tests/test_installer_transaction.py` 在隔离 DESTDIR 注入 payload 复制失败，确认旧可执行文件、状态和用户配置恢复，临时事务清理；`bash -n` 通过。真实 PID1/systemd 主机升级和 SIGKILL 矩阵未执行。 |
| XRA-07 | `python/rill_xray_agent/safe_fs.py`：随机 O_EXCL 暂存名，完整 short-write/InterruptedError 循环，零进展失败，文件与目录 fsync；发布失败恢复旧 inode 并清理暂存文件。 | `tests/test_backup_security.py` 覆盖 2/中断/剩余字节与零写旧文件保持；备份恢复摘要核对与既有 symlink 测试通过。ENOSPC/fsync/replace 故障矩阵未全部覆盖。 |
| XRA-08 | `python/rill_xray_agent/backup.py`：解压前预检 ZIP 数量、路径、类型、加密、压缩比与预算；独立有界 MANIFEST 读取；严格 schema/唯一路径/摘要/权限验证；restore 暂存和 journal 恢复。 | 新回归拒绝超限 manifest 和缺失 schema，并通过安全 roundtrip/hash。重复 ZIP entry、CRC/under-declared、special mode 与每个 journal 崩溃点的全部组合未覆盖。 |
| XRA-09 | 同文件：只收可解析 JSON 状态，递归拒绝秘密键/URI/密钥标记，未知二进制默认排除；创建时限单项/总量并流式写 ZIP。 | 新回归在 2 MiB 后合成 vless URI、嵌套 privateKey、未知二进制均排除，并检查归档内容；安全状态 roundtrip 通过。 |

## 验证

- Ubuntu 24.04 / WSL，隔离 ext4 临时副本，降权 `nobody` 执行 canonical Python 模块：44 个模块通过；为遵循“保留审计证据原文”，该资格运行排除了唯一触发历史门禁的 `test_public_repository_hygiene` 模块。
- 原始完整入口 `python3 scripts/run_python_tests.py`：失败，唯一已观察到的首个失败是 `test_public_repository_hygiene.Tests.test_no_prompt_files_anywhere`。它报告仓库历史中的 `AUDIT_2026-10-05/00-启动修改.md`、`01-Rill源头运行与升级安全.md`、`02-Rill源头备份与隐私.md` 与“no prompt files anywhere”规则冲突。这些审计原文按本任务要求保留；未删文档或放宽门禁。
- `python3 scripts/build_canonical_manifest.py` 后 `--check`：通过，124 项，bundle SHA-256 `484ab7a4e196d7cc649634e4d3ec96c6fa5cac48dd6a28c11023bbb2b4b133fd`，canonicalDigest `44677c4f2989d15e0d9025b2d2fbbdcbfd10881d456d798fc03b796e17b8851a`。
- `python3 scripts/verify_no_build_gate.py --root .`：通过，RillML 未引入本地编译。
- `integrations/xray_bash_onekey/tools/verify_repo.py` 未执行：该脚本要求外部 Xray 仓库路径，且对应阶段 3 尚未开始。
- 未执行：真实 PID1/systemd、发行版矩阵、真实 RillML 发布 runtime/网络端到端和全组合强杀故障资格；本轮仅完成 WSL 与 DESTDIR 隔离验证。

## 后续

源头修复提交及推送后，由兄弟仓库 `Xray_bash_onekey` 执行 `AUDIT_2026-10-05/03-主仓同步与发布准入.md`（阶段 3），消费这里生成的 canonical manifest/digest/bundle；仍不自动合并或发版。
