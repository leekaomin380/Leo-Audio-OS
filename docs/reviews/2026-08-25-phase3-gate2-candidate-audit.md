# Phase 3 Gate 2：无修改 ext4 候选审计

日期：2026-08-25

## 当前结论

Gate 2 的 raw ext4 重建器已达到“语义等价、文件系统干净、构建字节可复现、journal 对齐”
的阶段。Gate 2 尚未完成，因为 sparse 外层容器及其回环尚未生成；也没有任何设备写入授权。

journal 裁定后的私有候选 `candidate-ext4-v4` 与 `candidate-ext4-v5` 使用同一锁定 builder、
同一 staging、同一 metadata 和同一 profile 构建。最终 raw SHA-256 完全相同。两份候选分别与 Gate 1
原厂语义清单做 canonical-byte-equality 比较，均通过。

## 已通过的硬证据

- 路径、类型、普通文件内容 SHA-256、符号链接目标、UID/GID、mode、mtime、SELinux xattr
  和 5 条 capability xattr：3923 条语义记录逐字节等同原厂；
- `e2fsck -f -n`：通过，无 Gate 1 legacy padding 例外；
- ext4 features：精确为原厂旧 feature set；
- block size、block count、inode count、inode size、blocks/inodes per group、reserved block
  count、label、UUID、默认 mount options、TEA directory hash、reserved GDT 103 均对齐；
- `/lost+found` 的类型、owner、mode、4096-byte size 与 epoch 0 时间已对齐；
- journal inode 为原厂的 6552 blocks；JBD2 superblock 与原厂 4096 bytes 逐字节相同；
- 两次完整候选 raw ext4 字节哈希相同。

## Journal 裁定

现代 `mke2fs 1.46.6` 的 CLI 只接受 MiB journal size，`-J size=25` 因而生成 6400 blocks；
这不是 ext4/JBD2 限制。锁定的同源 `libext2fs` 提供 `ext2fs_add_journal_inode()`，可直接接收
精确 block 数。项目专用 helper 只接受 6552，要求输入尚无 journal，并通过正式 libext2fs
API 建立 inode 8、更新 superblock backup 和 `has_journal` feature。

小型探针和两份完整候选均证明：journal inode size/blockcount 与原厂一致，JBD2 superblock
逐字节一致，候选 feature set 不变，`e2fsck -f -n` 为 0，系统语义清单仍与原厂逐字节相同，
两次 raw ext4 也逐字节相同。journal 差异据此关闭，不再作为停止条件。

下一步只允许生成开发态零填充 partition raw 和 sparse 容器并做回环；仍不进入 dm-verity/FEC、
fastboot/recovery 或设备测试步骤。
