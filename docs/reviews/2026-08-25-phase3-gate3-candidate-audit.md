# Phase 3 Gate 3：最小 Leo Shell 候选审计

日期：2026-08-25

## 裁定

Gate 3 的正确候选通过全部本机静态门禁，可以冻结为 `phase3-gate3-v0.1`。该冻结点证明项目能从
Gate 2 的 3923 路径语义基线出发，只新增 `/app/LeoShell` 与其 APK，并可复现地重建 ext4 和
Android sparse 开发容器。

这个裁定不授权写入设备。候选仍是 `development-unverified`：分区尾部为零，不含新的 dm-verity
hash tree、签名 metadata 或 FEC，也没有与之配套并经过验证的 boot。

## APK 来源闭环

- 两次独立 `homeCandidateRelease` unsigned 构建均为 22212 bytes，SHA-256 均为
  `49a41f29e085448b14fa58d819688a497f5400a3d95d873399b37c112001a348`；
- `homeCandidateReleaseRuntimeClasspath` 两次均报告 `No dependencies`；
- 两次使用同一登记密钥进行 v1+v2 签名，最终 APK 均为 29543 bytes，SHA-256 均为
  `8a81a01f22098ba1b95be72d8fa333ad200738f16029c865f90b9669e57489ff`；
- 唯一 signer 证书 SHA-256 为
  `4f81ed58df81e8d51b18f396bfe53ce09ba92396494afdc980e3f6746eccc7db`；
- unsigned 与 signed APK 的 10 个非签名 ZIP 成员名称和解压字节全部相同；
- APK 只有一个 `classes.dex`，无 runtime dependency、Kotlin builtins、native library、嵌套
  APK/JAR 或 Android permission。

审计曾拒绝第一版签名 APK：其 `classes.dex` 缺少当前 `MaintenanceAuthActivity` 对 `setup` 状态的
捕获，说明它不是当前源码的产物。由该陈旧 APK 生成的两份 ext4、完整容器和 staging 已删除；本
报告的所有哈希只指向重新签名并闭合来源链的候选。

## 文件系统差异

- Gate 2：3923 条；Gate 3：3925 条；
- 新增路径严格为 `/app/LeoShell` 与 `/app/LeoShell/LeoShell.apk`；
- 原有 3923 条记录的内容、类型、mode、UID/GID、mtime、符号链接、xattr、capability 和 SELinux
  label 全部不变；
- `/app` 因新增一个子目录，link count 从 106 增至 107；
- 3838 个后续 inode number 顺延。这是 ext4 allocator 地址变化，不是文件语义变化；
- directory/regular/symlink 分别为 425/3262/238；SELinux label 为 3925 条，capability 仍为
  5 条；
- MIUI Launcher APK 哈希仍为
  `03a380c1b5ce656e310b275ceb8bce61122764e9a56dc05d941d04ecea4a317c`；
- 17 条音频兼容清单全部命中原始内容哈希。

Gate 2 与 Gate 3 的 ext4 UUID、feature set、block/inode geometry 和 journal 保持不变。新增目录、
APK 和 metadata 实际使用 9 个 4096-byte block 与 2 个 inode；两份候选均通过只读
`e2fsck -f -n`。

## 可复现性与容器

两份独立 raw ext4 候选逐字节相同：

- raw ext4 SHA-256：
  `10857ee55fd85f485febd15407b58b4da6dc95ba2ef932826ef505d38342574c`；
- raw ext4 长度：1717571584 bytes；
- 完整 development partition 长度：1744830464 bytes；
- ext4 后 27258880 bytes 全零；
- partition raw SHA-256：
  `a62fb0ba221ceea4a1a9c52ba7308853f561b04ce588bc97fa250258a027141b`；
- Android sparse SHA-256：
  `50c264caecb29533d3d1150c73a7f60ba107dd8078d7c6a7d32bbf77dc153334`；
- sparse 展开后与完整 raw 逐字节相同。

构建使用 Gate 2 冻结源码中的同一 builder 定义。最终 Gate 2 v6 与 Gate 3 候选使用的本地镜像为
`sha256:e4c6224db7874deb9743a936101988a86d0daedb3d48cd94c6b640aac3bffb14`；早期 SELinux 探针
记录的 `e462…` 是加入精确 journal helper 前的旧镜像，不是冻结候选的最终 builder。

## 发布边界

Git ignore 和 tracked-file 审计通过：ROM、APK、raw/sparse 镜像、私钥和 `resources/private/`
均未进入 Git。公开仓库只登记源码、证书、哈希、契约、SBOM 和验证脚本。

## 下一门

进入设备写入前必须另建 verified-boot/recovery gate：为候选生成项目自有 verity tree、签名
metadata 与 FEC，构建只信任该根的 boot，并验证至少两条独立恢复路径。Gate 3 冻结本身不缩短
这些步骤，也不允许把零尾 `system.img` 与原厂 `wait,verify` boot 配对。
