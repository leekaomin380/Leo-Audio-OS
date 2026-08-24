# 11：Phase 3 Gate 1 ext4 元数据审计契约

## 1. 目的

Gate 1 要回答的不是“能否看到 system 文件”，而是：我们能否从原厂 ext4 镜像生成一份
足以约束后续无修改重建的、可重复验证的语义清单。

任何普通目录复制都不足以证明这一点。Android system 的行为同时依赖文件内容、路径类型、
Unix DAC、硬链接、符号链接、扩展属性、Linux capabilities 和 SELinux 标签。遗漏其中一层，
都可能得到“文件看起来齐全，但服务无法启动或权限边界改变”的镜像。

## 2. 工具链决定

采用两套相互独立的只读证据。

### A. 无特权镜像审计：主证据

在固定 Linux 用户空间中使用：

- `e2fsck -f -n`：只读一致性检查；
- `dumpe2fs -h`：superblock、features、UUID、inode/block 参数；
- `debugfs -R stats`：文件系统结构复核；
- `debugfs` 递归目录、inode `stat` 与 `ea_list/ea_get`：目录项、inode 和 xattr。

这一条路径不挂载镜像，不需要 `CAP_SYS_ADMIN`，也不向 raw image 写入日志或恢复信息。
[`debugfs(8)`](https://man7.org/linux/man-pages/man8/debugfs.8.html)明确提供递归目录、inode
状态和扩展属性读取命令。

### B. Linux 内核只读视图：交叉证据

在隔离、无网络的 Linux 环境中，将 raw image 作为只读输入，以 `ro,noload` 挂载：

- `ro` 禁止文件系统写入；
- `noload` 禁止重放 journal；
- `find/lstat/readlink` 生成路径和 stat 清单；
- `getfattr` 读取所有 xattr；
- `sha256sum` 计算所有普通文件内容；
- `getcap` 只作人类可读复核，原始 `security.capability` xattr 才是权威值。

挂载视图不是唯一证据。它必须与 A 路径在目录项数量、路径类型、UID/GID、mode、链接和
xattr 上一致，否则 Gate 1 失败。

## 3. 为什么必须保留 xattr

Linux 扩展属性承载普通 stat 之外的数据；`security` namespace 用于安全模块和文件
capabilities。Linux 内核的 ext4 文档也说明 xattr 可能保存在 inode 或独立属性块中，
因此不能靠复制文件内容推断其存在。

Android 构建链同样把 DAC 与 MAC 当作独立输入：AOSP 的
[`e2fsdroid`](https://android.googlesource.com/platform/external/e2fsprogs/+/refs/heads/main/contrib/android/e2fsdroid.c)
分别接受 `fs_config` 和 `file_contexts`；AOSP
[`build_image.py`](https://android.googlesource.com/platform/build/+/master/tools/releasetools/build_image.py)
会把这两类输入传入 ext4 构建过程，并在展开镜像上运行只读 `e2fsck`。

因此 Gate 1 同时保存：

1. inode 上实际存在的原始 xattr；
2. 从 UID/GID/mode/capability 导出的 Android `fs_config` 候选；
3. 每个路径的实际 SELinux 标签；
4. stock `file_contexts.bin` 的哈希和来源引用。

“实际标签清单”可以约束无修改重建，但不能自动恢复原始 SELinux 正则源文件。若无法获得
等价的文本 `file_contexts`，Gate 2 不能把字符串扫描结果伪装为可发布策略来源。

## 4. 固定环境

Gate 1 环境必须记录并锁定：

- Linux 基础镜像名称与不可变 digest；
- 内核版本；
- `e2fsprogs`、`attr`、`libcap` 和 Python 版本；
- 审计脚本 Git 提交；
- raw system SHA-256；
- 所有命令、退出码和 stderr；
- 审计开始与结束时的可用空间。

主审计容器默认无网络、无设备映射、无 ADB/fastboot、无特权能力。raw image 只读绑定，
报告目录单独可写。B 路径若需要内核挂载，必须在隔离 Linux VM/容器中单独运行，不能把
整个项目目录以可写方式交给特权环境。

## 5. 机器清单

每个目录项输出一条 canonical JSON Lines 记录。路径按原始字节排序；同时保存 UTF-8
显示值和 Base64 值，避免换行或不可见字符破坏 TSV/日志边界。

每条记录至少包含：

| 字段 | 含义 |
| --- | --- |
| `path_utf8` / `path_b64` | 规范化绝对 system 路径与原始路径字节 |
| `inode` | 原厂 inode，仅用于建立硬链接组和审计 |
| `type` | directory、regular、symlink、char、block、fifo、socket |
| `mode_octal` | 完整权限位，包含 setuid/setgid/sticky |
| `uid` / `gid` | 数字所有者，不做主机用户名映射 |
| `nlink` / `hardlink_group` | 链接数与同 inode 路径集合 |
| `size` | inode 逻辑大小 |
| `rdev_major/minor` | 特殊节点设备号 |
| `symlink_target_b64` | 原始符号链接目标字节 |
| `content_sha256` | 普通文件内容哈希 |
| `xattrs` | 名称到原始值 Base64 的有序映射 |
| `selinux_label` | `security.selinux` 解码显示值 |
| `capability_hex` | `security.capability` 原始十六进制 |
| `mtime_ns` | 原厂 mtime；其他时间作为信息字段保存 |
| `source_a/source_b` | 两条证据各自是否观察到同一值 |

清单之外还要生成：

- `superblock.json`；
- `filesystem-check.txt`；
- `entries.jsonl`；
- `hardlinks.json`；
- `fs-config-derived.tsv`；
- `selinux-labels.tsv`；
- `audio-compatibility-check.json`；
- `toolchain.json`；
- `audit-summary.json`；
- 所有报告文件的 `SHA256SUMS`。

报告不包含 ROM、system 内容、专有文件内容或可还原二进制的 dump，只包含元数据、哈希和
有限路径信息；完整私有清单仍不得进入公开 Git。

## 6. Gate 1 硬性一致项

以下任一不一致都使 Gate 1 失败：

- 路径集合；
- 路径类型；
- 普通文件内容 SHA-256；
- symlink 原始目标；
- UID、GID、mode；
- 特殊节点设备号；
- 硬链接分组；
- 全部 xattr 名称和原始值；
- `security.selinux`；
- `security.capability`；
- Phase 1 `audio-compatibility-v0.1.tsv` 中全部文件的路径和 SHA-256；
- 文件系统检查出现需要修改镜像才能修复的错误；唯一例外是
  `manifests/stock-system-ext4-profile-v0.1.json` 锁定原厂 raw 的已裁定 inode bitmap
  padding 偏差。该例外必须报告为 `accepted_source_deviation`，不得报告为 `clean`。

## 7. 记录但不要求物理相同

以下项目在 Gate 1 必须保存；到 Gate 2 比较时允许变化，但必须解释：

- inode 具体编号；
- data block 物理位置；
- 目录哈希树布局；
- journal sequence；
- free block/free inode 数量；
- sparse chunk 划分与 sparse 文件哈希；
- atime 与 ctime；
- ext4 allocation bitmap 的物理形态。

锁定原厂 raw 的 inode bitmap padding 属于已登记的源输入物理偏差。Gate 2 可以且应当
把它规范化为现代 ext4 表示；这不属于语义清单差异。

允许它们变化不等于可以忽略。若变化导致分区超限、启动性能明显退化、文件丢失或
fsck 异常，Gate 2 仍然失败。

## 8. Gate 2 前必须锁定的重建参数

Gate 1 应导出并由 Gate 2 显式消费：

- 分区字节数与 block size；
- filesystem features；
- inode size、inode count；
- reserved blocks 与 journal 参数；
- label、UUID、hash seed；
- 固定 timestamp 策略；
- 派生 `fs_config`；
- 可证明等价的 `file_contexts`；
- 原始路径树及内容输入；
- system 可用空间和预留 headroom。

如果只能重建“文件内容”，不能证明 DAC、capabilities 和 SELinux 标签，则不进入 Gate 2。

## 9. 安全停止条件

- 工具尝试以读写方式打开 raw system；
- `e2fsck` 未使用 `-n`；
- 非锁定原厂 raw 试图复用 source-only fsck 例外；
- 主审计要求 root、设备映射或网络；
- B 路径发生 journal replay；
- 两条证据无法在路径或安全元数据上收敛；
- 工具版本或容器 digest 未记录；
- 报告目录混入专有文件内容；
- 当前空间不足以同时保存 raw image、审计输出和安全余量。

## 10. 进入执行档的边界

契约完成后，下一板块是机械实现：准备固定 Linux 环境、编写采集器、生成 raw system、
执行两条只读证据并校验 JSON schema。这部分不再需要 Sol high；遇到任何元数据差异、
SELinux 来源缺口或文件系统异常时再升档审计。
