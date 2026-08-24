# Phase 3 Gate 1：原厂 ext4 inode 位图尾部裁定

日期：2026-08-24

## 裁定

原厂 raw system 的 `e2fsck` 退出码 4 不能被写成“文件系统完全干净”，但现有证据足以把
唯一告警限定为 Android 7 同期 `make_ext4fs` 的可解释遗留格式偏差，而不是文件内容、
目录结构或 inode 分配损坏。

Gate 1 允许把这一个**仅限锁定原厂输入**的偏差登记为已知例外，继续对原始、未修复的
raw image 做只读语义采集。例外不向任何重建镜像继承：Gate 2 产物必须在现代固定版本
`e2fsck -f -n` 下退出 0。

## 锁定输入

- ROM build：`V9.2.3.0.NXHCNEK`；
- ROM SHA-256：
  `007d3d7d9a7e3e70684498070bab03ec145a73b1de44ed7299698cc4bf5ad94f`；
- sparse system SHA-256：
  `03960aeded4f6b3c7802109ff74aedec67c5de15841bf175ace66a89cde36003`；
- raw system SHA-256：
  `ec6edfd79adb1f6053adcc6fcb1927fabd93fe3756d9e7c7af8a7abd0dcd3e7d`；
- raw system：1744830464 bytes；ext4 4096-byte blocks；
- inode：104832 个，每组 8064 个，inode size 256 bytes；
- UUID：`da594c53-9beb-f85c-85c5-cedf76546f7a`。

## 双版本复核

以下两个版本都只报告同一个问题：

- Debian 12 容器：`e2fsck 1.47.0`；
- macOS Homebrew：`e2fsck 1.47.4`。

两者执行 `e2fsck -f -n` 时均依次通过 inode、block、directory、connectivity、reference
count 检查，只在 Pass 5 报告：

```text
Padding at end of inode bitmap is not set. Fix? no
```

## 与 Android 7 构建器的对应关系

AOSP `android-7.0.0_r1` 的 `ext4_utils/allocate.c` 在初始化每个块组时用 `calloc` 一次
生成相邻的 block bitmap 和 inode bitmap，因此 inode bitmap 起始状态整块为 0；后续
`reserve_inodes()` 只把真实分配到的 inode bit 设为 1。该文件没有把
`inodes_per_group` 之后、同一 bitmap block 内的范围外 padding bit 设为 1 的步骤。
`make_ext4fs.c` 随后直接更新空闲计数并写出镜像。

这与原厂镜像逐字节观察完全对应：每个 bitmap block 的前 1008 bytes 表示 8064 个有效
inode；之后 3088 bytes 全为 `0x00`。只有 group 0 已实际初始化，其余 12 个块组带
`INODE_UNINIT` 标志，所以现代 `e2fsck` 对 group 0 的范围外尾部提出规范化要求。

缺少小米当年的私有构建日志，无法证明这份 ROM 使用了哪一个精确 commit；因此“由
`make_ext4fs` 生成”属于高置信度归因，不冒充供应链来源证明。

## 隔离修复实验

对原始 raw 建立初始 SHA-256 完全相同的 APFS 写时复制副本，只在副本上执行
`e2fsck 1.47.4 -f -y`。修复后再次执行 `-f -n`，退出码为 0。

修复共改变 3148 bytes，严格局限于 3 个 4096-byte block：

| block | 改动 | 字节数 |
| ---: | --- | ---: |
| 0 | superblock 的 last write / last check 时间 | 8 |
| 1 | 13 个 group descriptor 的 `itable_unused` 与相应 checksum | 52 |
| 106 | group 0 inode bitmap 的 byte 1008–4095：`00` → `ff` | 3088 |

没有 data block、inode table、目录内容或普通文件内容被修改。修复副本 SHA-256 为
`c9bb41188c54291dac9c809128966058322d8094bfa26cf8d00dfee82d391599`；它只用于诊断，
不是后续构建输入。

## 运行时风险判断

Linux v3.10 的 ext4 inode allocator 调用位图搜索时，把搜索上限明确限制为
`EXT4_INODES_PER_GROUP(sb)`，不会把尾部 padding 当作可分配 inode。相同源码在初始化
inode bitmap 时会主动调用 `ext4_mark_bitmap_end()` 把范围外 bit 设为 1，说明现代
规范化值应为 1，但原厂的 0 不会扩大内核的有效 inode 搜索范围。

因此此偏差的风险是“现代离线 fsck 不接受其物理表示”，而不是“内核会分配不存在的
inode”。原厂镜像实际可启动与长期运行也是旁证，但不能替代上述源码边界证明。

## 审计规则

Gate 1 只在以下条件全部成立时接受该例外：

1. raw SHA-256 与锁定 profile 完全相同；
2. size、UUID、label、block/inode geometry 与 profile 完全相同；
3. `e2fsck -f -n` 的唯一问题是上述 padding 告警；
4. group 0 bitmap 的 3088 个 padding bytes 全为 `0x00`；
5. 审计不修复、不挂载、不重放 journal；
6. 报告必须写明 `accepted_source_deviation`，不得写 `clean`。

如果 raw hash 不同，哪怕出现相同文字也不自动接受。Gate 2 及以后生成的任何镜像都不得
使用此例外，必须 `e2fsck -f -n = 0`。

## 官方源码依据

- AOSP Android 7.0 `allocate.c`：
  <https://android.googlesource.com/platform/system/extras/+/android-7.0.0_r1/ext4_utils/allocate.c>
- AOSP Android 7.0 `make_ext4fs.c`：
  <https://android.googlesource.com/platform/system/extras/+/android-7.0.0_r1/ext4_utils/make_ext4fs.c>
- Linux v3.10 ext4 inode allocator：
  <https://github.com/torvalds/linux/blob/v3.10/fs/ext4/ialloc.c>
- e2fsprogs 对该问题的测试输出：
  <https://github.com/tytso/e2fsprogs/blob/master/tests/j_long_trans_mcsum_64bit/expect>
