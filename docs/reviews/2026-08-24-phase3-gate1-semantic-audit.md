# Phase 3 Gate 1：原厂 system 语义审计

日期：2026-08-24

## 结论

Gate 1 的只读语义审计通过：锁定的原厂 `system.raw.img` 已生成完整、内容不出私有目录的
语义清单，并由两条独立证据逐字节收敛。这个结论允许进入 Gate 2 的**无修改重建设计**，
但不授权构建、刷入或删除任何系统组件。

Gate 2 的一个前置缺口仍然明确存在：当前保存的是每条现有 system 路径的实际 SELinux
标签，不是原厂 `file_contexts` 正则源文件。后续必须获得或生成可证明覆盖相同路径树的
文本 labeling 输入，不能把标签清单误写成原始策略来源。

## 输入与文件系统状态

- raw system SHA-256：
  `ec6edfd79adb1f6053adcc6fcb1927fabd93fe3756d9e7c7af8a7abd0dcd3e7d`；
- 容量：1744830464 bytes；UUID：`da594c53-9beb-f85c-85c5-cedf76546f7a`；
- 主审计容器：`leo-audio-os-selinux-audit:bookworm`，image ID
  `sha256:0eba1265dd100ea7c5761b96f2de7a13a09d68712b392234d24be7fa0b526066`；
- `e2fsck -f -n` 的唯一告警是已经裁定的 Android 7 inode bitmap padding 源输入偏差；
  分类为 `accepted_source_deviation`，不是 `clean`，也不允许被 Gate 2 继承。

## 主证据：direct ext4 只读解析

采集器直接读取 inode、extent、directory entry 和 xattr 二进制结构；它没有挂载镜像，
也没有写入 raw image。产出：

| 项目 | 结果 |
| --- | ---: |
| 路径条目 | 3923 |
| 唯一 inode | 3923 |
| directory / regular / symlink | 424 / 3261 / 238 |
| hardlink 组 | 0 |
| SELinux 标签 | 3923 |
| `security.capability` | 5 |
| Phase 1 音频兼容清单 | 17 / 17 哈希匹配 |

主清单 `entries.jsonl` SHA-256：
`e785beb7678b5dfb49752157697034eda72a085b82bc6ad436c644680a994300`。

除完整 JSONL 外，私有报告还生成了逐条 `fs_config` 候选、SELinux 标签表、硬链接表、
音频兼容性核验 JSON 和每个报告文件的 SHA-256 校验表。报告只包含路径、元数据、标签和
内容哈希，不包含 ROM、APK、ELF 或其他专有文件内容。

## 交叉证据：Linux 内核视图

第二条路径在隔离、无网络、只读根文件系统的 Linux 容器内执行。原始 raw 只读绑定后以
`ro,noload,loop` 临时挂载；内核记录为：

```text
/input/system.raw on /mnt type ext4 (ro,relatime,norecovery)
```

`norecovery` 是 Linux 对 `noload` 的有效展示，表示没有 journal replay。采集完成后容器
明确卸载 `/mnt`。内核的 `lstat`、`readlink`、xattr 和文件内容哈希清单与主清单逐字节相同；
hardlink 表也逐字节相同。

## 安全边界

- 没有调用 ADB、fastboot、recovery 或任何设备写入；
- 没有修改 raw image；
- 只读主路径没有特权能力；
- 内核交叉路径因 macOS 容器运行时的 loop mount 限制使用隔离容器的 `--privileged`，但只
  获得一个 raw 只读绑定和一个空报告目录写入点；没有把项目目录或手机暴露为可写目标；
- 当前数据卷约有 30 GiB 可用；本轮 Gate 1 私有输入和报告约占 3.0 GiB。

## Gate 2 入口条件

进入无修改重建前，仍需先锁定：

1. 适用于这棵 system 路径树的可验证 SELinux labeling 输入；
2. 从语义清单重建 ext4 的固定工具链、时间戳与分区空间预算；
3. 新镜像的 `e2fsck -f -n = 0`；
4. 新旧清单差异为零，或每一项均有明确的物理层解释。
