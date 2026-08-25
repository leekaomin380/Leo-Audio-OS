# Phase 3 Gate 2：6552-block journal 裁定

日期：2026-08-25

## 结论

原厂 6552-block internal journal 可以由锁定的现代 `libext2fs` 安全、确定地重建。此前候选
的 6400 blocks 来自 `mke2fs -J size=25` 的整数 MiB 接口，不是 ext4 或旧内核约束。

## 实现边界

项目 helper `create-leo-journal` 只接受常量 6552，并在写入前要求：

- 输入是未挂载 raw ext4；
- `has_journal` 尚未启用；
- superblock 尚未登记 journal inode；
- reserved inode 8 为空。

最终 helper 还要求输入精确匹配 Leo 的 block/inode 几何、103 reserved GDT blocks、固定
label/UUID，以及“除 `has_journal` 尚未启用外”完全一致的旧 feature set；因此不能误用于普通
ext4 文件或其他设备镜像。

满足前置条件后，它调用与 builder 同一 pinned e2fsprogs revision 的
`ext2fs_add_journal_inode()`。该 API 分配 inode 8、写入 JBD2 superblock、更新 journal backup
与 `has_journal`。原厂 internal journal 的 JBD2 UUID 字段为全零；helper 在 libext2fs 完成
结构创建后把该字段归一为原厂值。

## 验证证据

- 最小探针：6552 blocks、26836992 bytes、JBD2 maxlen 6552、`e2fsck -f -n = 0`；
- 探针 JBD2 superblock 与原厂 4096-byte block 逐字节相同；
- 两份完整候选均有原厂 feature set、103 reserved GDT blocks 和 6552 journal blocks；
- 两份候选均与原厂 3923 条语义清单逐字节相同；
- 两份候选 raw ext4 逐字节相同；
- 两份候选均通过 `e2fsck -f -n`，无 legacy padding 例外。
- 加入完整 Leo profile 防误用检查后的第三份完整候选，raw 仍与前两份逐字节相同。

## 安全裁定

这不是手工扩展 journal inode、篡改 JBD2 maxlen 或复制原厂物理 blocks，而是通过维护中的
libext2fs 创建自洽结构，再对已确认无外部 journal 语义的 UUID 字段做原厂值归一。因此允许
进入 Gate 2 的 partition raw 与 sparse 容器回环；不构成设备写入授权。
