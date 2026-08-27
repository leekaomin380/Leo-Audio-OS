# Phase 5B Gate M0/M1：MoKee 可信输入与静态审计

日期：2026-08-27

## 裁定

**M0 通过；M1 通过；M2 尚未开始，也未获设备写入授权。**

锁定的 `MK100.0-leo-221019-RELEASE.zip` 是可解释、可复核的 `leo` MoKee Android 10
输入。它已经包含 ESS9018 内核/DTB 路径、QUAT MI2S、Forte 校准、I2S 配置、ACDB/ADSP
支撑和 Android 10 音频框架，适合作为兼容性桥梁。它不是可发布系统：boot 明确为
userdebug/dev-keys、SELinux Permissive、默认开放不安全 ADB，并禁用 deep sleep。

首个实机候选如果未来获准，只能是**未经音频覆盖、未经删包的锁定原版 MoKee**。其 OTA
脚本只显式写入 `boot` 与 `system`，但 addon backuptool 可能恢复旧附加组件，因此进入 M2 前还要
关闭或完整审计 addon 保留行为，并重新验证双份回滚材料和 recovery/fastboot 救援入口。

## 1. M0：输入闭环

| 项目 | 已验证事实 |
| --- | --- |
| 文件 | `MK100.0-leo-221019-RELEASE.zip` |
| 目标 | updater assert 同时接受 `NotePro` / `leo` |
| 版本 | Android 10、SDK 29、2022-08-05 security patch |
| 大小 | `647032071` bytes |
| 发布 MD5 / 本地 MD5 | `1e4026ea6788f9e8adc8419602d11e46`，一致 |
| 本地 SHA-256 | `e1d32441513d49108802cc426b0891f7c3be577f2cb41d4030b4fe2ddf614390` |
| 容器 | 10 entries，ZIP CRC 全通过 |
| system | transfer-list v4 重建为 1,744,830,464-byte ext4；只读 e2fsck exit 0 |
| boot | `9470dd6a01120480289c17d0da161e73b2eb6361ece3ea72041b07da088934af` |

ROM、boot、system、安装脚本和 DTB 的公开摘要在
`manifests/mokee-rom-inventory-v0.1.tsv`。原始 ZIP、镜像、专有二进制与反编译中间物只保存在
Git 忽略的 `resources/private/phase5b-mokee/`，没有进入公开提交。

## 2. 启动和分区链

ROM 使用 legacy-v0-compatible boot、system-as-root 和单一 system 分区内的 `/system/vendor`。
boot 附带 36 份 DTB。已锁定的 `leo` 黄金路径是 index 25；stock 与 MoKee DTB25 的 SHA-256
不同，但目标硬件音频节点的语义相同。

OTA 具有以下已知边界：

1. 检查设备代号和 `TZ.BF.3.0.R1-00226` 前提；
2. 显式写入 `system` 和 `boot`；
3. 未发现 modem、recovery 或 bootloader 写入；
4. backuptool 仍可能跨刷机保存/恢复 addon，因此“ZIP 只写两个分区”不等于运行环境绝对纯净。

boot 的发布级阻断项不是推测，而是镜像内事实：

- cmdline：`androidboot.selinux=permissive`、`lpm_levels.sleep_disabled=1`、
  `buildvariant=userdebug`；
- default properties：`ro.secure=0`、`ro.adb.secure=0`、`ro.debuggable=1`、
  `persist.sys.usb.config=adb`；
- 没有检测到 Android BootSignature footer。

所以 M2 原版基准只能在已解锁、可恢复的研究设备上短期验证，不能被称为 Leo Audio OS 发布候选。

## 3. DTB 音频语义差异

用仓库私有 `dtc` 对两份 index 25 DTB 完整反编译。结果：

- stock DTB25：`cee146b6093e34d2997ca21314cd25d9a7d321429b695dff6a6bae70ad178d5e`；
- MoKee DTB25：`6edb500870102d4607e12e1c3f3470a79cd3f65c9a5130d237c39ef4ba803fe8`；
- 两者都含 `es9018@48` / `compatible = "ess,es9018"`；
- ESS 的五路供电、reset/mute/switch/OPA/45M/49M GPIO 与 pinctrl 引用一致；
- sound card model、四路 LPAIF mode mux、QUAT MI2S sleep/active pinctrl、CPU DAI 和
  `audio-routing` 一致；
- 相关标记计数一致：`audio-routing` 1、`ess_int` 3、`ess_power_int` 3、
  `quat_mi2s` 14。

完整 DTB 仍存在显示面板、LED/fstab 等非音频差异，所以本结论是“**音频目标节点语义一致**”，
不是“两份 DTB 等价”。这证明 MoKee 已携带硬件描述层的 ESS bring-up，不证明运行时一定切入
HiFi 输出。

## 4. 音频闭包与最小差量

详细逐组件 SHA、ABI、裁决与实机测试要求见
`manifests/mokee-audio-delta-v0.1.tsv`。关键结论如下。

### 4.1 已经等价的层

- 7 份 `Forte_*.acdb` 与 MIUI 黄金参照全部逐字节相同；
- `mixer_paths.xml` 逐字节相同；
- `mixer_paths_i2s.xml` 和 `audio_platform_info_i2s.xml` 只有注释差异，功能 XML 相同；
- `libDiracAPI_SHARED.so` 逐字节相同；
- MoKee kernel/DTB 已描述 ESS9018 与 QUAT MI2S。

这意味着第一轮不需要“植入整套原厂音频目录”。校准资产、I2S 路由和硬件描述已经在 MoKee
输入中存在。

### 4.2 真正缺失的能力

MIUI 32/64 位 stock HAL 都含：

```text
SND_DEVICE_OUT_HIFI_HEADPHONES
persist.audio.hifi
persist.audio.hifi.volume
platform_set_hifi_property
QUAT_MI2S BitWidth
QUAT_MI2S SampleRate
```

MoKee 32/64 位 HAL 会识别 I2S sound card 并选择 I2S XML，但均缺少上述 MIUI 专用控制。
因此当前首选方案是：

1. 保留 MoKee Android 10 AudioPolicy、HIDL service、Dirac wrapper、ACDB loader/support 和
   linker namespace 关系；
2. 在锁定的开源 Qualcomm HAL 上重写/移植最小 HiFi 状态机；
3. 只有静态 ABI 与原版运行数据证明必要时，才评估单个 stock blob；
4. 禁止把 Android 7 的 stock HAL、audioserver 或 framework 整体覆盖 Android 10。

`audio_platform_info.xml` 与 AudioPolicy 的差异必须保留 Android 10 侧语义：MoKee 的 backend
命名、BT SCO 和 XML policy 结构属于平台代际兼容，不应为追求 hash 一致而倒退。

### 4.3 服务、init 与 SELinux

MoKee 的音频启动闭包已经能静态解释：

- `audioserver.rc` 启动 audioserver，并在重启时联动 `vendor.audio-hal-2-0`；
- HIDL rc 声明 audio 4.0/2.0 interface，进程身份为 audioserver；
- `init.target.rc` 启动 `adsprpcd`、`rfs_access` 等 Qualcomm 支撑服务；
- `init.qcom.rc` 初始化 ADSP boot sysfs、`/data/misc/audio`、ACDB delta 和 `/data/audio`；
- file contexts 覆盖 audio HIDL、`adsprpcd`、`rfs_access`、`/dsp`、`/data/rfs`、
  `/dev/adsprpc-smd`、`/dev/msm_*`、WCD DSP 节点和 ADSP boot sysfs。

MoKee 成品中没有 `audiod` binary 或 service。其设备 product 明确没有打包 audiod，尽管通用
源码和 vendor policy 还保留 `audiod` 符号。当前裁决是“原版基准不需要先补 audiod”；残留 policy
属于待清理的兼容债务，而不是足以证明缺文件的证据。

仍需由 M2 运行时证明：进程/映射、ACDB load、设备节点、SELinux denial、AudioPolicy 决策、
ESS probe 和 QUAT mixer 状态均闭合。

## 5. 组件处置预案

原版镜像四个 app 目录共 103 个 package directory；精确清单和初步 bucket 在
`manifests/mokee-component-disposition-v0.1.tsv`：

| bucket | 数量 | 含义 |
| --- | ---: | --- |
| retain-core | 12 | 启动、权限、网络、媒体和系统界面核心 |
| retain-maintenance-first | 20 | 先保留，待维护/恢复入口替代后再裁决 |
| investigate | 5 | 需要 caller/build graph 才能判断 |
| remove-batch-1..5 | 66 | 表面应用、电话、相机、可选硬件和 MoKee 附加组件 |

静态分类显示约 64% 的 package directory 有望在 M4 分批退出，但这不是现在删除 66 个包的授权。
删减必须等 M3 音频等价完成，并以源码产品白名单、依赖闭包、双构建和每批冷启动/音频回归执行。
特别是 `AudioFX` 可删不代表 Dirac 库或 effect chain 可删；`Lawnchair`、Settings、PackageInstaller、
DocumentsUI 和 VPN/证书组件要保留到 Leo Home 与隐藏维护模式完成替代。

ROM 不含 GMS 或 Play Store。Spotify 的安装、登录和依赖是 M2/M4 单独的维护面问题，不能通过
addon backuptool 偷渡旧 Google 组件来“解决”。

## 6. M1 通过条件逐项回答

1. **如何启动**：legacy boot + 36-DTB 选择 + system-as-root；当前 boot 为研究型不安全配置。
2. **如何出声**：AudioPolicy → audioserver → audio HIDL 2.0/4.0 → msm8994 HAL → I2S XML →
   QUAT MI2S/ESS kernel path，ACDB/ADSP 与 Dirac 支撑在镜像中存在。
3. **已有何种 ESS 支持**：硬件描述、驱动字符串、I2S 配置和原厂同一份 Forte 校准都已存在；
   缺的是已证明存在于 MIUI HAL 的专用 HiFi 控制状态机。
4. **首个候选为何不触碰未知分区**：锁定 updater 只显式写 boot/system；进入 M2 前还需处理
   backuptool，并实测回滚入口。M1 本身没有写设备。

## 7. 进入 M2 前置门与停止点

当前立即停止在设备写入门。下一步不是生成 HiFi 改造包，而是由 SH 设计并冻结 M2 原版基准契约：

1. 重验当前设备身份、电量、USB/按键/recovery/fastboot；
2. 对 stock rollback ZIP、Phase 4 release set 和第二份离线副本做全量 hash/read test；
3. 明确 addon backuptool 处置，禁止继承旧 Magisk/GApps/脚本；
4. 固定无需登录态备份的 Spotify 重新安装与网络方案；
5. 设计冷启动、Wi-Fi、外放、耳机、Spotify、息屏、温度、deep sleep、crash/denial 和恢复采集；
6. 定义“ESS 成立”证据：kernel probe + 节点 + AudioPolicy/HAL route + QUAT mixer + ACDB load，
   不能只凭耳机有声或主观音质；
7. 在真正进入 recovery 或写 boot/system 前，再向设备所有者请求一次临场明确授权。

M2 之前不得刷写、wipe、修改当前黄金参照，也不得把本报告中的高可信静态推断写成实机事实。

## 8. 本轮验证记录

- 重新顺序读取 ROM、boot、system raw 和 MoKee DTB25，SHA-256 均与清单一致；ROM MD5 亦一致；
- 逐行把音频差量矩阵中的 26 个本地 MoKee/stock 文件重新计算 SHA-256，无 mismatch；
- 通过 debugfs 从 ext4 重新枚举四个 app 目录，103 个实际目录与组件处置表精确一致，无缺项/多项；
- 三份 TSV 分别满足 10、7、5 列契约，组件键无人工合并；
- `audit-mokee-rom.py` 与 `stream-sdat2img.py` 通过 `py_compile`，审计命令入口可解析；
- `git diff --check` 通过；执行前后可用空间约 10 GiB，未触发 6 GiB 停止线；
- 本轮没有调用 ADB、没有连接或重启设备、没有生成可刷候选、没有写任何分区。
