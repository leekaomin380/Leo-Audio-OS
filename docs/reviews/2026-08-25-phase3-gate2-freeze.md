# Phase 3 Gate 2 冻结：无修改 system 重建与开发态容器

日期：2026-08-25

## 冻结结论

Gate 2 冻结为“无修改 system 重建器 + development-unverified Android sparse 容器”基线。
它证明了项目能够从锁定的、用户本机持有的官方 MIUI system 输入，重建语义等价且可由旧内核
特性集读取的 ext4，并装入精确分区几何的 Android sparse 容器后无损回展开。

冻结点不是可刷入固件，更不是发布镜像：它没有新的 dm-verity tree、FEC、签名 metadata 或
project release boot；因此不得同 stock `wait,verify` boot 配对，任何设备写入仍需新的独立授权。

## 已冻结的证据

- 精确 ROM、sparse 几何和 persist 不写边界已由 Gate 0 锁定；
- 两条只读 ext4 证据已导出 3923 条 system 语义记录；
- 两次完整 raw ext4 重建语义相同，且 raw SHA-256 相同；
- ext4 feature set、UUID、label、103 reserved GDT blocks 和 6552-block internal journal 与
  原厂目标对齐；JBD2 superblock 4096 bytes 相同；
- 产物 `e2fsck -f -n` 为 exit 0；
- hardened journal helper 输出与前两份 raw 候选相同；
- development partition 为 425984 个 4096-byte blocks：419329-block ext4 前缀加 6655-block
  物化零尾；不读取或复用 stock dm-verity/FEC；
- `raw → Android sparse v1 → raw` 后，完整 partition SHA-256 与 `cmp` 均确认字节不变；
- 全部材料均为本机私有输入/输出；构建过程中未调用 ADB、fastboot、recovery 或设备写入接口。

完整命令、版本、哈希和审计记录见
[`2026-08-25-phase3-gate2-candidate-audit.md`](2026-08-25-phase3-gate2-candidate-audit.md)、
[`2026-08-25-phase3-gate2-journal-ruling.md`](2026-08-25-phase3-gate2-journal-ruling.md) 与
[`12-PHASE-3-GATE2-UNMODIFIED-REBUILD-CONTRACT.md`](../12-PHASE-3-GATE2-UNMODIFIED-REBUILD-CONTRACT.md)。

## 冻结范围

冻结的公开内容是 builder、受限 journal helper、metadata 构造/验证脚本、容器脚本、契约与
无专有内容的审计摘要。ROM、提取文件树、raw/sparse 镜像、私钥、设备数据和任何第三方 APK
均继续留在 Git 之外。

冻结后不得为了“让它能刷”而修改 Gate 2 产物或偷渡 boot/verity/FEC 改动。此类工作只能在
新的 Gate 里开展，并保留本冻结点作为可复现对照。

## 未冻结项与下一门

- 不生成 project-owned verity/FEC、release keys 或 boot image；
- 不执行 fastboot/recovery/ADB 设备测试；
- 不删除 system 应用，不改变 MIUI 服务；
- 不声明 Spotify、网络、耳机 HiFi、温度或恢复回归已经在新 system 上通过；
- 不提供刷入指令。

Gate 3 只能从该冻结点分支：先引入项目签名的最小 Leo Shell，建立明确文件差异、SELinux 规则、
空间预算、静态门禁和恢复材料，再讨论任何实机测试。
