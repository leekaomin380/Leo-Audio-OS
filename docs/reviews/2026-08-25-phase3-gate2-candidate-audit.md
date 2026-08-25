# Phase 3 Gate 2：无修改 ext4 候选审计

日期：2026-08-25

## 当前结论

Gate 2 的 raw ext4 重建器和开发态 sparse 外层容器均已达到“语义等价、文件系统干净、构建
字节可复现、journal 对齐、完整分区容器回环”的阶段。没有任何设备写入授权；这个结论也不把
开发态零尾当成原厂 verified-boot 产物。

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

## 开发态 partition raw 与 sparse 回环

以 hardened helper 生成且与 v4/v5 raw 字节相同的 `candidate-ext4-v6` 为输入，
`build-gate2-development-container.py` 在私有目录物化了精确 425984-block 分区：前 419329
blocks 为已核验 ext4，剩余 6655 blocks（27258880 bytes）全部为零。脚本不读取、更不复用
原厂 dm-verity hash tree、metadata 或 FEC。

- 完整 partition raw SHA-256：`c3559a096f3d8820db8f9303f478a846f5cfc0558d61d5d4bc571a95774baee4`；
- Android sparse：v1、4096-byte block、425984 blocks、292 chunks、1309724720 bytes；
- sparse SHA-256：`fd35321b815b10a101acc1f4639e411c8e07118cebd5f3fa36fcee74205ffe4c`；
- `simg2img` 回展开后的完整 raw SHA-256 与上述 partition raw 相同，且 `cmp` 逐字节相同；
- 回展开 raw 的前 1717571584 bytes 与 v6 ext4 SHA-256
  `a230be9f432cb521bcd2e94dc25eac7c17c3ea9b09fd09cd94c56d8139129dae` 相同，尾段仍为全零；
- 在隔离、只读 Linux 容器中对回展开 raw 执行 `e2fsck -f -n`，exit 0。

这证明了 Gate 2 候选可被本机 `img2simg` 封装、由独立 `simg2img` 解析并无损回到指定开发态
分区字节序列；它不证明可与原厂 `wait,verify` boot 配对，更不构成 fastboot 或设备写入授权。

## Journal 裁定

现代 `mke2fs 1.46.6` 的 CLI 只接受 MiB journal size，`-J size=25` 因而生成 6400 blocks；
这不是 ext4/JBD2 限制。锁定的同源 `libext2fs` 提供 `ext2fs_add_journal_inode()`，可直接接收
精确 block 数。项目专用 helper 只接受 6552，要求输入尚无 journal，并通过正式 libext2fs
API 建立 inode 8、更新 superblock backup 和 `has_journal` feature。

小型探针和两份完整候选均证明：journal inode size/blockcount 与原厂一致，JBD2 superblock
逐字节一致，候选 feature set 不变，`e2fsck -f -n` 为 0，系统语义清单仍与原厂逐字节相同，
两次 raw ext4 也逐字节相同。journal 差异据此关闭，不再作为停止条件。

下一步是冻结 Gate 2 证据，并另立 Gate 3 的最小有意修改契约：差异清单、空间预算、SELinux
新增规则、只读静态检查与回退材料必须先齐备。仍不进入 dm-verity/FEC、fastboot/recovery 或
设备测试步骤。
