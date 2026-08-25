# 10：Phase 3 MIUI 原型固件构建器路书

## 1. 阶段目标

Phase 3 建立一套“用户自备精确官方 ROM”的可复现构建器，在不触碰 Bootloader、基带、
信任区和 persist 的前提下，生成可审计的 MIUI 衍生 system 原型。首个目标不是精简，
而是证明输入身份、解包、元数据保存、原样重建和恢复边界都可信。

Phase 2 的 `phase2-v0.2.7` 是行为基线；Phase 3 不把尚未完成的重启和音频回归伪装为通过。

## 2. 锁定输入

- ROM：`leo_images_V9.2.3.0.NXHCNEK_20171229.0000.00_7.0_cn_4ca14075f0.tgz`；
- SHA-256：`007d3d7d9a7e3e70684498070bab03ec145a73b1de44ed7299698cc4bf5ad94f`；
- system：Android sparse v1，4096-byte block，425984 blocks；
- system 展开容量：1744830464 bytes，即 1703936 KiB；
- 目标设备：Xiaomi Mi Note Pro / `leo` / fastboot product `MSM8994`。

构建器拒绝“相同版本名但哈希不同”的输入，也拒绝把公开仓库当作专有文件分发渠道。

## 3. 不可破坏边界

1. Gate 0–2 仅在本机处理镜像，不调用 fastboot；
2. 默认产物只包含 system，不重打包或写入 Bootloader、modem、tz、rpm、sbl、aboot；
3. 不覆盖 persist；原厂 `rawprogram0.xml` 对 persist 的 filename 为空；
4. 不运行原厂 `flash_all*.sh`；这些脚本会写多个固件分区，其中 lock 版本还会擦除 devinfo；
5. 不修改或重签 Spotify、GMS、Xiaomi 专有 APK；
6. 不把私有 ROM、镜像、提取树、密钥和设备数据加入 Git；
7. 任何首次写入设备的候选必须先有完整 recovery、system 备份和明确恢复命令。

## 4. Gate 设计

### Gate 0 — 输入与容器

- [x] 精确 ROM 文件名和 SHA-256；
- [x] tar 路径安全和必需成员唯一性；
- [x] sparse header 与物理 system 分区容量一致；
- [x] persist 默认不写；
- [x] sparse → raw → sparse → raw 的原始字节完全一致；
- [x] 形成机器可读 Gate 0 报告。

Gate 0 只证明 Android sparse 容器工具链，不证明 ext4 文件级重建。

### Gate 1 — ext4 只读审计

- [x] 校验 ext4 superblock、features、UUID、inode/block 参数和空间使用；
- [x] 导出完整路径、类型、模式、UID/GID、capabilities、符号链接和 xattrs；
- [~] 保存全部现有路径的实际 SELinux 标签；原厂 `file_contexts` 正则源仍待恢复或构造
  等价输入；
- [x] 核对原厂 system 哈希清单与 Phase 1 音频闭包；
- [x] 记录文件级重建的当前空间事实：数据卷约 30 GiB 可用，Gate 1 私有材料约 3.0 GiB。

Gate 1 已由无挂载 direct-ext4 解析和 Linux `ro,noload` 内核视图双重验证。详情见
[`2026-08-24-phase3-gate1-semantic-audit.md`](reviews/2026-08-24-phase3-gate1-semantic-audit.md)。

### Gate 2 — 无修改文件级重建

- [x] 锁定 builder、Android metadata、旧内核 feature set 与 verified-boot 架构；
- [x] 从只读清单重建 ext4；
- [x] 保持分区容量，不扩大 system；
- [x] 比较路径、内容哈希、权限、所有者、链接、xattrs、capabilities 和 SELinux 标签；
- [x] 运行只读文件系统检查；
- [ ] 重新生成 sparse system，并验证可由 fastboot 解析；
- [ ] 差异为零或每一项都有明确、可接受的解释（journal blocks 仍待裁定）。

### Gate 3 — 最小有意修改

- [ ] 只加入项目 release 签名的 Leo Shell；
- [ ] MIUI Launcher 继续保留；
- [ ] 不删除系统应用；
- [ ] 生成 SBOM、文件差异、空间预算和回退说明；
- [ ] 在不写设备的情况下完成全部静态门禁。

### Gate 4 — 分层精简

每批只处理一个依赖集合。先“禁用入口”，后“从镜像移除”；每批都要重建、启动、网络、
Spotify、耳机 HiFi、温度和恢复测试。音频闭包、PackageManager 启动依赖和 MIUI 启动保护
均作为硬门，不以包名直觉删除组件。

## 5. 空间与环境

当前数据卷约 30 GiB 可用。单次 sparse 容器往返峰值约 6.6 GiB，可以执行，但完成后
必须删除明确命名的临时镜像，只保留报告。文件级重建和多版本对照需要更充足的工作盘；
完整 Android 平台构建仍不在当前空间预算内。

## 6. 停止条件

- ROM 哈希、分区容量或设备身份不匹配；
- 工具不能保存 UID/GID、xattrs、capabilities 或 SELinux 标签；
- 输出超出原始 system 分区；
- 需要运行原厂全量刷机脚本或写入 persist/固件分区；
- 无法解释原样重建差异；
- 没有可验证恢复包就要求首次实机写入；
- 参考机成为唯一可承受失败的设备而没有第二条恢复路径。

## 7. 当前下一步

Gate 1 的双证据工具链已通过，Gate 2 的 labeling、ext4 builder 与 verified-boot 双轨边界
也已由 [`12-PHASE-3-GATE2-UNMODIFIED-REBUILD-CONTRACT.md`](12-PHASE-3-GATE2-UNMODIFIED-REBUILD-CONTRACT.md)
锁定。现已完成两次本机 raw ext4 构建和逐项语义比较；详见
[`2026-08-25-phase3-gate2-candidate-audit.md`](reviews/2026-08-25-phase3-gate2-candidate-audit.md)。
在 journal 差异裁定前不生成 sparse ROM，更不写入设备。
