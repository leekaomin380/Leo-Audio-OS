# Phase 3 Gate 2：无修改 ext4 候选审计

日期：2026-08-25

## 当前结论

Gate 2 的 raw ext4 重建器已达到“语义等价、文件系统干净、构建字节可复现”的阶段，但尚未
完成 Gate 2，也没有生成 sparse 容器或获得任何设备写入授权。

私有候选 `candidate-ext4-v2` 与 `candidate-ext4-v3` 使用同一锁定 builder、同一 staging、
同一 metadata 和同一 profile 构建。最终 raw SHA-256 完全相同。两份候选分别与 Gate 1
原厂语义清单做 canonical-byte-equality 比较，均通过。

## 已通过的硬证据

- 路径、类型、普通文件内容 SHA-256、符号链接目标、UID/GID、mode、mtime、SELinux xattr
  和 5 条 capability xattr：3923 条语义记录逐字节等同原厂；
- `e2fsck -f -n`：通过，无 Gate 1 legacy padding 例外；
- ext4 features：精确为原厂旧 feature set；
- block size、block count、inode count、inode size、blocks/inodes per group、reserved block
  count、label、UUID、默认 mount options、TEA directory hash、reserved GDT 103 均对齐；
- `/lost+found` 的类型、owner、mode、4096-byte size 与 epoch 0 时间已对齐；
- 两次完整候选 raw ext4 字节哈希相同。

## 已知但未裁定的物理差异

现代 `mke2fs 1.46.6` 的 `-J size=25` 固定生成 6400 journal blocks；原厂 Android 7
构建器的 journal inode 为 6552 blocks。两者均显示为 25M，且候选文件系统检查、旧 feature
set 与全部系统语义均通过。这个差异不能以“语义相同”掩盖：后续须单独评估是否安全地重建
6552-block journal，或把它登记为有边界的、已解释的物理差异。

在该裁定前，不进入 sparse 打包、dm-verity/FEC、fastboot/recovery 或设备测试步骤。
