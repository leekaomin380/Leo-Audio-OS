# 12：Phase 3 Gate 2 无修改重建契约

## 1. 目的

Gate 2 要证明：在不增删或修改任何 system 路径的前提下，可以从 Gate 1 的只读证据重建
一个语义等价、旧内核可读、`e2fsck` 完全通过的 ext4，并把它装入与原厂 system 分区容量
相同的 Android sparse 容器。

这不是“做出一个能解包的镜像”，也不是刷机授权。Gate 2 全程只处理本机私有输入；任何
候选都不得调用 ADB、fastboot、recovery 或原厂全量脚本。

## 2. 新发现的 system 分区结构

Gate 1 的 raw 文件并不只是 ext4。锁定输入的 425984 个 4096-byte block 分成：

| 区域 | 起始 block | blocks | bytes | 作用 |
| --- | ---: | ---: | ---: | --- |
| ext4 | 0 | 419329 | 1717571584 | `/system` 文件系统 |
| dm-verity hash tree | 419329 | 3304 | 13533184 | ext4 Merkle tree |
| verity metadata | 422633 | 8 | 32768 | 签名、table、root hash、salt |
| FEC payload | 422641 | 3342 | 13688832 | Reed-Solomon 纠错数据 |
| FEC footer block | 425983 | 1 | 4096 | 末尾 64-byte FEC header/footer |

原厂 metadata 使用 `0xb001b001` magic；table 指向
`/dev/block/bootdevice/by-name/system`，数据块数为 419329，算法为 SHA-256。最后一个 block
包含 `0xfecfecfe` magic、version 0、2 roots，以及与上述布局一致的 input/FEC size。

这与原厂 boot ramdisk 的 `fstab.qcom` 中 `wait,verify` 和 `verity_key` 形成完整信任链。
任何物理重建都会改变 ext4 block 内容，因此原厂 hash tree、FEC 和签名不能复制到新镜像。

## 3. verified-boot 双轨边界

### 3.1 Gate 2 开发态

当前已验证的 Magisk patched boot 只把 system 行的 fs_mgr flag 从 `wait,verify` 改为
`wait`；stock kernel payload 保持相同。Gate 2 因而采用以下开发态边界：

1. 只生成 419329-block ext4；
2. 外层扩展到原分区的 425984 blocks；
3. ext4 后的区域全部为零，不伪装成有效 verity/FEC；
4. 产物明确标记为 `development-unverified`；
5. Gate 2 不生成、修改或刷入 boot image。

这条路径用于证明重建器，不是最终安全架构。候选也不得与原厂 `wait,verify` boot 配对；
该组合预期会在 fs_mgr 校验阶段失败。

### 3.2 未来发布态

真正的专用设备固件应恢复只读验证链：项目生成并离线保管自己的 verity 私钥，把对应公钥
写入项目 boot ramdisk，保留 `wait,verify`，再为每个 system 构建 hash tree、签名 metadata
和 FEC。bootloader 已解锁且当前设备能接受 patched boot，说明技术路径存在；但密钥治理、
boot 可复现重打包、失败回退和实机验证属于后续独立 Gate。

不得把 AOSP test key 当作发布密钥；不得声称拥有小米原厂私钥；不得用原厂签名包裹新的
hash tree。

## 4. 工具链裁决

采用固定 Linux 容器中的 `mke2fs + e2fsdroid`，不采用旧 Android 7 `make_ext4fs`。

理由：

1. 当前 AOSP 的 ext4 用户镜像路径由 `mke2fs` 建立文件系统，再由 `e2fsdroid` 写入内容、
   Android DAC、capabilities 和 SELinux xattr；
2. `e2fsdroid` 原生接受 canned `fs_config` 与 `file_contexts`，并对未找到的配置项失败；
3. 原厂 `make_ext4fs` 已在 Gate 1 证明会留下 inode bitmap padding 偏差；Gate 2 要求
   `e2fsck -f -n = 0`，不能继承该缺陷；
4. 旧内核兼容性由输出 feature set 决定，不由构建工具发布日期决定。

上游依据：

- [AOSP `mkuserimg_mke2fs.py`](https://android.googlesource.com/platform/system/extras/+/master/ext4_utils/mkuserimg_mke2fs.py)；
- [AOSP `e2fsdroid`](https://android.googlesource.com/platform/external/e2fsprogs/+/refs/heads/main/contrib/android/e2fsdroid.c)；
- [AOSP `e2fsdroid` Android metadata implementation](https://android.googlesource.com/platform/external/e2fsprogs/+/34f4f33/contrib/android/perms.c)；
- [AOSP canned `fs_config`](https://android.googlesource.com/platform/system/core/+/refs/heads/main/libcutils/canned_fs_config.cpp)。

容器必须锁定 immutable image digest、e2fsprogs/libselinux 版本、构建脚本提交和完整命令。
不使用 macOS 主机默认 ext4 profile，也不读取主机的 `/etc/mke2fs.conf`。

## 5. ext4 输出约束

候选必须锁定：

- 4096-byte block；419329 blocks；
- 104832 inodes；256-byte inode；
- label `system`；UUID `da594c53-9beb-f85c-85c5-cedf76546f7a`；
- reserved block count 0；
- 原厂参考几何为 13 block groups、32768 blocks/group、8064 inodes/group、103 reserved GDT
  blocks、6552 journal blocks；
- feature set **精确等于**
  `has_journal ext_attr resize_inode filetype extent sparse_super large_file uninit_bg`；
- 不得出现 `64bit`、`metadata_csum`、`flex_bg`、`huge_file`、`dir_index` 或其他原厂没有的
  feature；
- errors behavior、inode/group geometry、journal 大小和 reserved GDT 必须记录并比较；候选以
  `resize=432046080` 固定 103 个 reserved GDT blocks；上述
  原厂值是优先目标，不能精确复现的物理参数要在候选 profile 中固定并由高智能档单项裁定；
- root 与 `/lost+found` mtime 为 epoch 0，其余 3921 条路径为 1230739200；
- 两次独立构建必须先做到语义清单逐项相同；目标是 raw ext4 也逐字节相同。若 raw hash
  不同，必须找出时间、UUID、hash seed、journal 或 allocation 的非确定性来源，不能直接
  宣布可复现。

构建器使用隔离 `mke2fs.conf` 明确启用旧 feature set。完成后以 superblock 实测结果为准，
命令行看起来正确不能替代输出验证。

不能直接给 `e2fsdroid` 使用单一全局 `-T`，因为原厂不是单一时间戳。staging root 设为
epoch 0，其余普通目录项按清单设为 1230739200；`e2fsdroid` 从 staging `lstat` 读取时间。
`/lost+found` 在 e2fsdroid 中是特殊路径，不执行普通 timestamp/permission 分支。

已完成的最小实验表明：`E2FSPROGS_FAKE_TIME=0` 会被 mke2fs 解释为“未指定”并回退到真实时钟，
因此不能满足 epoch 0；`E2FSPROGS_FAKE_TIME=1` 可稳定建立固定初始文件系统。随后必须运行受控
`debugfs` 后处理，把 `/lost+found` 的 atime/ctime/mtime 置为 0、缩小这个空目录至原厂的 4096
bytes，并把 superblock 的 `min_extra_isize`/`want_extra_isize` 置为原厂的 28。这个归一化步骤已在
最小镜像和完整候选上经 `e2fsck -f -n` 验证，不能省略，也不能用 2009 静默替代 epoch 0。

## 6. 内容 staging 契约

完整路径树从锁定 raw 的 Linux `ro,noload` 视图提取到私有 staging；不从互联网、第三方
ROM 或不完整的 Phase 1 音频提取目录补文件。

提取后、建镜像前必须对 staging 检查：

- 3923 条路径完整，类型为 424 directory、3261 regular、238 symlink；
- 没有 hardlink、device node、FIFO 或 socket；
- 每个普通文件 SHA-256 与 Gate 1 相同；
- 每个 symlink target 的原始字节与 Gate 1 相同；
- 路径集合无新增、无缺失。

staging 上的 host UID/GID、xattr 和 mode 不是权威输入；它们由下述 Android metadata 文件
重新生成并在候选镜像上验证。

## 7. `fs_config` 精确生成

Gate 1 的 TSV 是审计格式，不直接交给 `e2fsdroid`。Gate 2 为每条路径生成一条 canned
记录：

```text
system/<relative-path> uid gid permission-bits [capabilities=0x...]
```

根路径在 canned 文件中编码为“行首空格后直接给 uid”的空路径记录，而不是 `system`；这是
`e2fsdroid` 在调用 canned `fs_config` 前把 mountpoint root 转为 `""` 的实际接口约束。其余
路径使用 `system/<relative-path>`；`e2fsdroid` mountpoint 固定为 `/system`。mode 只输出权限位，
文件类型由 inode 保留。每条 lookup 必须精确命中；任何缺项均失败。

候选先以 raw ext4 创建，因此调用 `e2fsdroid` 时必须显式使用 `-e`；不带该参数会按 Android
sparse 格式打开 raw 文件并在写入前失败。最小集成镜像已验证 `-e` 后可加载全部 3923 条
`fs_config`、写入 SELinux xattr，且 `e2fsck -f -n` 通过。

5 个 `security.capability` xattr 均为 VFS capability revision 2、effective flag、仅 permitted
位非零，可以无损转换为 64-bit capability mask：

- `cnss-daemon`、`ims_rtp_daemon`、`imsdatadaemon`、`pm-service`：`0x400`；
- `run-as`：`0xc0`。

生成器必须拒绝未知 revision、非零 inheritable 位、不能表示的 flags 或超出 64-bit 的值；
候选上仍以原始 20 bytes xattr 逐字节比较为最终门禁。

## 8. SELinux 封闭世界等价输入

Gate 2 不声称恢复了小米原始 `file_contexts` 正则源。它从 Gate 1 的 3923 条实际标签生成一
份只适用于当前封闭路径树的文本规则：

1. `/` 映射为 `/system`，其余路径加 `/system` 前缀；
2. 每个路径按 SELinux file-context regex 语法逐字符转义；
3. 每条规则只匹配一个完整路径，并带与目录项类型一致的 type qualifier；
4. 标签为 Gate 1 inode 上实际 `security.selinux` 值；
5. 使用与 `e2fsdroid` 相同的 libselinux 编译/加载规则；
6. 对 3923 个路径和 mode 逐条 lookup，结果必须与清单完全相同；
7. 对未登记路径做负向测试，避免宽泛规则意外覆盖。

这证明的是“对当前路径树等价”，不是“对未来路径等价”。Gate 3 新增 Leo Shell 时必须
显式添加新路径规则并证明所用 type 已存在于 stock sepolicy；不能让 `system_file` fallback
掩盖缺失设计。

AOSP 说明 `file_contexts` 在镜像构建时用于写入 filesystem xattr；`e2fsdroid` 对每个 inode
调用 `selabel_lookup`，并把包含结尾 NUL 的值写入 `security.selinux`。因此上述闭包可由输出
xattr 逐字节验证，而无需把 `file_contexts.bin` 的字符串扫描结果冒充源策略。

## 9. Gate 2 产物

私有产物：

1. `system.ext4.raw`：只含 419329-block ext4；
2. `system.partition.raw`：425984-block 开发态分区，后段为零；
3. `system.img`：由完整 partition raw 生成的 Android sparse；
4. staging 内容、e2fsdroid-ready `fs_config`、封闭世界 `file_contexts`；
5. 两次构建的工具链、命令、superblock、`e2fsck`、语义清单和 SHA-256；
6. sparse → raw 回环证明。

公开 Git 只保存脚本、契约、无内容哈希报告和不泄露专有二进制的 profile；ROM、完整路径
清单、APK/ELF、raw/sparse 镜像、私钥与设备数据继续留在 `resources/private` 或外部安全
存储。

## 10. 硬门

候选必须同时满足：

- `e2fsck -f -n` exit 0，且无 Gate 1 的 legacy padding 例外；
- feature set 无新增、无缺失；分区总容量不超过 1744830464 bytes；
- 路径、类型、内容 hash、symlink target、UID/GID、mode、nlink、mtime 精确相同；
- 全部 xattr 名称和值精确相同；SELinux 3923/3923、capability 5/5；
- Phase 1 音频兼容清单 17/17；
- 两次候选语义清单逐字节相同；
- `img2simg` 后能由独立 `simg2img` 展开，且完整 partition raw SHA-256 相同；
- 输出明确标记 `development-unverified`，不含可误认的旧 verity 尾部；
- 没有调用任何设备写入接口。

inode 号、data block 位置、journal sequence、free-space 布局和 sparse chunk 划分可以相对
原厂变化，但必须相对两次候选构建确定，并且不能引起语义、空间或 fsck 差异。

## 11. 停止条件

- 构建工具自动启用了旧 kernel 未证明支持的 ext4 feature；
- 任一 Android metadata lookup 使用默认值或 fallback 才能通过；
- root/`lost+found` 时间戳不能确定性复现；
- journal 或 reserved GDT 差异无法解释；
- staging 或报告混入公开 Git；
- 候选需要原厂 verity 私钥才能继续；
- 候选被要求与 stock `wait,verify` boot 配对；
- 当前空间不足以保留两份候选和一份源 raw，同时保留安全余量；
- 任何步骤试图连接或写入手机。

## 12. 下一执行档

本契约锁定后，下一板块是机械实现：固定 builder 容器、生成 staging/metadata 输入、做两次
本机构建和语义比较。该板块适合 Terra medium；只有遇到 feature、SELinux、verity、fsck
或不可解释的二进制非确定性时再切回 Sol high。
