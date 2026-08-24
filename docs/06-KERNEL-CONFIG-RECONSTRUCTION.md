# 06：Stock kernel 配置重建 v0.1

## 结论

stock kernel 没有 IKCONFIG，实机也不存在 `/proc/config.gz`，所以不能像新设备一样
直接导出完整 `.config`。但我们不需要由此停工：可以把官方 `leo_user_defconfig`
作为候选集，再用 stock Image 符号、设备节点和实机运行状态逐项证实。

v0.1 已登记 27 个与音频、功耗、调试和安全直接相关的选项：

- 23 个已由实机或 stock Image 直接确认；
- 4 个为高置信候选，仍需源码系统首次构建验证；
- 当前所有已查选项都与官方 `leo_user_defconfig` 一致，未发现反例。

机器可读表见
[`manifests/kernel-config-evidence-v0.1.tsv`](../manifests/kernel-config-evidence-v0.1.tsv)。它不是伪造出的
“完整 stock config”，而是一张每个结论都附有证据等级的子集。

## 1. 什么是 kernel config

Linux 内核源码里同时放着大量互斥或可选能力。`.config` 决定哪些代码被编入：

- `y`：直接编入 kernel Image，开机后通常会在 `/sys/module/` 看到内建驱动状态；
- `m`：编译为可加载 `.ko` 模块，加载后进入 `/proc/modules`；
- `n`：不编译。

它与“运行时参数”不是同一层。例如：

```text
CONFIG_CPU_IDLE=y
```

表示 CPU idle 框架存在；而：

```text
/sys/module/lpm_levels/parameters/sleep_disabled=N
```

是当前时刻的运行开关。只看 boot 命令行、defconfig 或 sysfs 中任意一个，都会把
“编译进去了什么”与“当前怎样运行”混为一谈。

## 2. 证据等级

| 等级 | 证据 | 可以证明什么 |
| --- | --- | --- |
| 直接确认 | stock Image 符号 + 实机注册/运行 | 功能确实存在，且不是只留在源码中 |
| 高置信 | 官方 defconfig + 实机间接产物 | 选项极可能存在，但仍缺专属导出口 |
| 官方候选 | 只出现在官方 defconfig | 只能作为首次构建输入，不能写成 stock 事实 |

私有运行快照由
[`scripts/collect-kernel-config-evidence.sh`](../scripts/collect-kernel-config-evidence.sh) 只读采集。本次快照
SHA-256 为：

```text
60173f50ccbd1050a205dc1a455ee561d9fce770db80af70538a6c7dcfcbcce3
```

快照不记录 ADB 序列号、账号、网络配置或用户文件。

## 3. 已确认的核心组

### 音频与 DSP

`CONFIG_SND`、PCM、compress offload、ASoC、MSM8994、ES9018、WCD9330、ADSPRPC、
ADSP loader 和 AVTimer 都有 Image 或运行时证据。实机上已注册：

- `msm8994-tomtom-mtp-snd-card`；
- PCM 与 `comprC0D*` 节点；
- `/dev/adsprpc-smd`；
- `/sys/kernel/boot_adsp/boot`。

这说明 compressed offload 在内核层存在；它不改变 H1 实验中 Spotify 实际使用
deep-buffer PCM 而非 offload 的结论。“系统有这个能力”不等于“该次播放使用它”。

### 功耗与性能

CPU idle、hotplug、suspend/PM sleep、MSM performance 和 thermal 都存在。实机可见 8 个
possible/present CPU，当前 online 集动态变化；CPU0 的 retention 和 power-collapse 都有
非零计数，34 个 thermal zone 也均保留。

因此第二代可以精简性能策略，但不能删除 CPU idle、hotplug 或 thermal 保护。

### 安全与调试

SELinux 当前为 Enforcing，`/dev/mem` 不存在；这两个边界必须保留。
KALLSYMS 和受 Xiaomi 白名单约束的 debugfs 存在，对 bring-up 很有价值；量产版应最小化
它们的暴露面，而不是在开发初期一刀切掉可观测性。

## 4. 第二代构建策略

首次源码系统构建不应立即发明一份“最小 config”。安全的顺序是：

1. 在大小写敏感的 Linux 文件系统上，用锁定的官方树生成 `leo_user_defconfig`；
2. 将 v0.1 表中的音频、供电、idle、thermal 和 SELinux 选项设为必须项；
3. 首次启动保留 modules、KALLSYMS 和受限 debugfs，先换取可诊断性；
4. 完成 Wi-Fi、触摸、有线 HiFi、suspend/resume 和 thermal 压力验收后，再分组删除无关驱动；
5. 每次收缩 config 都重建生成 `.config`、`savedefconfig`、Image 哈希和运行证据。

这样得到的最终 config 不会是“猜出来的原厂配置”，而是“以原厂为起点、每个删减都经过
实机验收的 Leo Audio OS 配置”。

## 5. 下一步

- 在 Linux 构建环境中生成官方基线 `.config`；
- 将 4325 行官方 defconfig 按音频、功耗、网络、显示和无关外设分组；
- 扩展 v0.1 为完整的差异报告，但不把无证据的默认值伪装成 stock 事实；
- 并行解析 stock sepolicy，使内核设备节点与用户空间 allow 规则形成闭包。
