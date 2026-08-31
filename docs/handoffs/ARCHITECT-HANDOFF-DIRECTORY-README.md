# 架构师交接目录与编号规范

依据用户 2026-08-30 指令确定；固定目录于 2026-08-31 依用户裁定迁移，见文末「目录迁移」。

固定目录：
`/Users/km/Documents/Codex/leo-audio-os/architect-handoffs/`

该路径**不含日期**，不依附任何一次会话。交接书自身的日期只在文件名与编号中体现。

编号格式：`LEO-HO-YYYYMMDD-HHMMSS-FROM-TO-DEST`

- 时间使用 Asia/Shanghai，取创建交接书时的真实时间。
- FROM / DEST 使用 `CODEX` 或 `CLAUDE`。
- 文件名为 `<编号>.md`；同名已存在则重新取时间，不覆盖旧文件。
- 例如：`LEO-HO-20260830-160942-CODEX-TO-CLAUDE.md`。
- 交出后状态为“待接管”。接班者明确确认该编号后登记为已接管；不得因文件存在就假定已接管。
- 本目录规范补充《AGY 用户触发交接协议 v1.0》，不扩大操作授权。该协议原件仍在
  `/Users/km/Documents/Codex/2026-08-30/leo-audio-os-m3-users-km-2/outputs/agy-orchestration-feasibility-20260830/AGY-用户触发交接协议-v1.0.md`，
  仓库内另有副本 `docs/handoffs/AGY-用户触发交接协议-v1.0.md`。迁移后此处改用绝对路径，原相对路径已失效。

当前交接：`LEO-HO-20260831-095439-CLAUDE-TO-CODEX.md`。

状态：**待 Codex 接管**。Claude 已停止派发与项目变更；本机 agy 进程 0，设备在基线。Gate 2 已闭合、Gate 3 前三项已进 main；Gate 3 第 4/5 项未开始，M3 上机仍为 NO-GO。

前次交接：`LEO-HO-20260830-223623-CODEX-TO-CLAUDE.md`（Claude 已带 3 条异议接管，见其 `-ACCEPTANCE.md`）。再前次：`LEO-HO-20260830-213000-CLAUDE-TO-CODEX.md`，Codex曾带异议接管，见其 `-ACCEPTANCE.md`。历史文件完整保留。

---

## 目录迁移（2026-08-31）

原固定目录为
`/Users/km/Documents/Codex/2026-08-30/leo-audio-os-m3-users-km-2/outputs/architect-handoffs/`，
以 **Codex 某一次会话的开始日期**命名。

问题：编号规范要求交接书取创建时的真实时间，承载它的目录却钉在 `2026-08-30`。
2026-08-31 写成的 `LEO-HO-20260831-095439-CLAUDE-TO-CODEX.md` 因而躺在一个写着 8-30 的路径下；
更实际的风险是接班者开新会话目录后，「固定目录」与其实际工作目录冲突，交接书会被写到两处。

用户 2026-08-31 裁定迁移至上述不含日期的路径。

迁移方式：先复制、逐文件 SHA256 校验一致（7/7）、再删除原件并在原位置留 `MOVED.md` 指针。
**未做不可逆移动，未改写任何交接书内容。**

已迁移文件（7 个，哈希未变）：

```
LEO-HO-20260830-160942-CODEX-TO-CLAUDE.md
LEO-HO-20260830-213000-CLAUDE-TO-CODEX.md
LEO-HO-20260830-213000-CLAUDE-TO-CODEX-ACCEPTANCE.md
LEO-HO-20260830-223623-CODEX-TO-CLAUDE.md
LEO-HO-20260830-223623-CODEX-TO-CLAUDE-ACCEPTANCE.md
LEO-HO-20260831-095439-CLAUDE-TO-CODEX.md
README.md
```

仓库 `docs/handoffs/` 内按文档日期命名的归档副本不受影响，仍是长期事实来源。
