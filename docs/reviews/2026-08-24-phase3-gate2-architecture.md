# Phase 3 Gate 2：无修改重建架构裁决

日期：2026-08-24

## 结论

Gate 2 的架构设计通过，可以进入机械实现，但仍不授权构建后刷入设备。

决定如下：

1. builder 使用固定 Linux 环境中的现代 `mke2fs + e2fsdroid`；
2. Android DAC/capabilities 从 Gate 1 清单生成精确 canned `fs_config`；
3. SELinux 使用 3923 条实际标签生成“封闭世界、逐路径精确等价”的 labeling 输入；
4. ext4 保持原厂 feature set 和几何上限，不复制旧 `make_ext4fs` padding 缺陷；
5. Gate 2 输出是 `development-unverified`，不伪造原厂 dm-verity；
6. 最终发布固件另建项目自有 verity key、boot 公钥、hash tree、签名 metadata 与 FEC 链。

## 关键新证据：raw system 不等于 ext4

Gate 1 的 raw 大小是 1744830464 bytes，但 ext4 superblock 只声明 419329 blocks，即
1717571584 bytes。对 ext4 之后 27258880 bytes 的只读检查证明它们绝大多数非零。

边界进一步精确收敛为：

| 区域 | blocks | SHA-256 |
| --- | ---: | --- |
| ext4 region | 419329 | `786cd054e489d135cb47ab402cbf518014b0592d1afbaad44864d92154030293` |
| verity tree | 3304 | `90bf3e38b94b6fa18e22a57a622d2ff5f43d1ae20f6090ee2794e4cf0c289e50` |
| verity metadata | 8 | `3570a6cfeb020c930a56eaffea777c169188c381a0f32d9fb416e466e3c9ab64` |
| FEC payload | 3342 | `8d781dad8f43912141fe890e997045e868dcb0d4a5fb77a31a2a6bf6611f106b` |
| FEC footer block | 1 | `493fdb8a476b943dde362a813b173ff12aaa9f7d9ed974742b0c31be14259fa1` |

metadata magic 为 `0xb001b001`，table 长 236 bytes；table 的 data/hash block count 均为
419329。FEC footer magic 为 `0xfecfecfe`，roots 为 2，input size 为 1731137536 bytes，
FEC payload size 为 13688832 bytes。所有数字与区段边界精确闭合。

原厂 boot 的 `fstab.qcom` 对 `/system` 使用 `wait,verify`，且 ramdisk 内存在 `verity_key`。
这证明尾部是启动链的一部分，而非可随意覆盖的空白。

## 当前设备为什么仍有开发路径

对本机已保存的 Magisk patched boot ramdisk 做只读比较后，唯一相关 fstab 变化为：

```diff
- /system ... wait,verify
+ /system ... wait
```

stock 与 patched kernel section SHA-256 相同。这意味着当前开发 boot 已停止要求 system 的
原厂 verity table；Gate 2 可以在不持有小米私钥的情况下构建本地候选。但这不是“验证链
已解决”，而是“开发态明确关闭验证”。

Gate 2 不改 boot，也不刷 system。未来发布态要恢复验证，正确方法是项目持有自己的私钥、
在 boot 中放对应公钥，再重新生成整条 verity/FEC 链。

## SELinux 等价性的裁决

我们不拥有小米原始文本 `file_contexts`，但 Gate 1 已从两个独立只读视图证明每个现有
inode 的实际标签。对于“无修改路径树”这一封闭集合，可以生成一条路径对应一条标签的
literal rule，并通过同一 libselinux 对 3923 个路径/mode 做 lookup 全覆盖证明。

该做法的证明边界是明确的：

- 对 Gate 2 当前路径树等价；
- 不等同于恢复小米原始 regex 设计；
- 不自动覆盖 Gate 3 新路径；
- 最终仍以候选 inode 的 `security.selinux` 原始 xattr 与 Gate 1 逐字节相同为准。

因此，Gate 1 的 SELinux 来源缺口已转化为一个可验证、诚实命名的 Gate 2 输入，而不是被
字符串扫描掩盖。

## 为什么不用旧 `make_ext4fs`

原厂工具的优点是接近历史布局，但 Gate 1 已定位到其 inode bitmap padding 行为会让现代
`e2fsck` 返回需要修正。复制它只能复制缺陷，不能提高旧内核兼容性。

现代 AOSP 的 [`mkuserimg_mke2fs.py`](https://android.googlesource.com/platform/system/extras/+/master/ext4_utils/mkuserimg_mke2fs.py)
明确以 `mke2fs` 建文件系统，再由 `e2fsdroid` 接收时间戳、`fs_config` 和 `file_contexts`。本项目
候选是 raw ext4，故 `e2fsdroid` 必须带 `-e`；默认 sparse 打开方式会在写入前失败。
[`e2fsdroid` 的 metadata 实现](https://android.googlesource.com/platform/external/e2fsprogs/+/34f4f33/contrib/android/perms.c)
会把 UID/GID/mode 写入 inode，把 64-bit capability mask 编码为 VFS capability xattr，并以
`selabel_lookup` 结果写入带结尾 NUL 的 SELinux xattr。

旧内核风险通过“候选 feature set 必须与原厂精确相同”来控制，而不是靠使用一个已知会
产生非规范位图的旧 builder。

## 已锁定的高风险细节

- ext4 只有 419329 blocks；425984 blocks 是包含 verity/FEC 的外层分区容量；
- 5 个 capability xattr 可无损映射为 `0x400`（4 条）与 `0xc0`（`run-as`）；
- root 与 `/lost+found` mtime 为 0，其他 3921 条为 1230739200；
- 不能用单一 `e2fsdroid -T` 覆盖所有路径；root 从 staging 保留 epoch 0。`lost+found`
  由 mke2fs 的固定初始时间建立，再由受控 `debugfs` 归一为 epoch 0；最小镜像已通过
  `e2fsck -f -n` 验证；
- 源树没有 hardlink、device node、FIFO、socket，减少了 staging 歧义；
- root 权限/owner 依赖 mke2fs 默认值，`lost+found` 是 e2fsdroid 的特殊路径，二者必须单独
  做输出验证；
- 当前数据卷约 30 GiB 可用，足够进行受控双构建，但不能无界保留重复 raw/staging。

## 下一步与智能档位

下一板块是固定容器、编写生成器与比较器、提取 staging、双构建和本地验收。其决策已被
本裁决约束，属于 Terra medium 适合的机械实现。

若出现以下任一情况，立即停止并切回 Sol high：

- mke2fs 不能只生成原厂 feature set；
- journal/reserved GDT 无法稳定；
- libselinux lookup 与实际标签不一致；
- capability roundtrip 不同；
- `e2fsck` 非 0；
- 两次构建有不能归因的语义或 raw 差异；
- verified-boot 边界需要改变。
