# Phase 3 Gate 3 冻结记录

日期：2026-08-25

## 冻结结论

Gate 3 最小 Leo Shell 文件系统集成通过静态审计，冻结目标标签为
`phase3-gate3-v0.1`。冻结范围是源码、公开 identity/SBOM/候选哈希、二路径 overlay 工具、语义
比较器和审计文档；不包含 APK、专有 ROM、staging、ext4/sparse 镜像或任何私钥。

## 冻结事实

- 基线：`phase3-gate2-v0.1`；
- 允许差异：只新增 `/app/LeoShell` 与 `/app/LeoShell/LeoShell.apk`；
- APK SHA-256：
  `8a81a01f22098ba1b95be72d8fa333ad200738f16029c865f90b9669e57489ff`；
- raw ext4 SHA-256：
  `10857ee55fd85f485febd15407b58b4da6dc95ba2ef932826ef505d38342574c`；
- 两次 APK build、两次签名与两次 ext4 build 均可复现；
- 3923 条原厂路径语义不变，17 条音频兼容项和 MIUI Launcher 保持；
- `e2fsck`、SELinux closed-world lookup 和 sparse/raw 回环全部通过；
- 私有材料与构建产物未进入 Git。

## 非声明

该标签不是可刷固件、OTA 包或正式 release。没有项目 verity/FEC、配套 boot、recovery 实测和
第二设备破坏性恢复演练时，不得把冻结的 development container 写入手机。

详细证据见
[`2026-08-25-phase3-gate3-candidate-audit.md`](2026-08-25-phase3-gate3-candidate-audit.md)。
