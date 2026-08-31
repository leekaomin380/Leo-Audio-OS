# M3 HiFi Controller：发现、验证等级与当前进度裁决

日期：2026-08-29 22:03（Asia/Shanghai）  
项目：Leo Audio OS / Xiaomi Mi Note Pro (`leo`)  
范围：MoKee Phase 5B M3 自动 HiFi 控制器、ESS9018 音量标定与构建门。  
性质：**阶段状态快照**；不构成刷写授权，也不把代理报告等同于主分支已集成状态。

## 1. 执行摘要

当前手机已经持久运行 MoKee，显示、联网、Apple Music、有线耳机和 ESS9018 → OPA1612
临时 HiFi 路由均已获得实机证据。项目已经从“MoKee 是否能使用这套 HiFi 硬件”的可行性
判断，推进到“如何由 HAL 自动、确定性且故障安全地管理该路径”的 M3 实现阶段。

本阶段最重要的收敛如下：

1. MoKee 同音量刻度下响度偏低的主导原因已经定位到 ES9018 的 `Volume` kcontrol；
2. M3 控制器已经形成五个可应用补丁，并经过两轮架构审计和关键缺陷修正；
3. 最新补丁的三个修改源文件已经通过严格 ARM32 语法检查并成功生成 ARM32 EABI5
   relocatable object；
4. 尚未完成真实 Android `audio.primary.msm8994.so` 模块链接，因此当前裁决仍是：
   **GO 到真实模块构建，NO-GO 到 ROM 集成和设备写入**；
5. R7-B（`Volume 205 → 225 → 205`）尚未执行，不能把 `225` 写成已验证默认值；
6. 44.1 kHz SRC 仍是 M3.5 独立里程碑，当前 M3 不得宣称 bit-perfect。

以“MoKee 成为可日用的自动 HiFi 播放器”为尺度，当前总进度估计为 **55%–60%**；若
R7-B 和真实 HAL 链接均通过，可推进至约 **70%–75%**。百分比仅用于项目调度，不替代
下文证据门。

## 2. 当前设备基线

截至本快照，已经确认：

- `system` 与 `boot` 均为持久化 MoKee 基线，不再依赖临时 `fastboot boot`；
- MoKee 可以正常启动、联网并运行 Apple Music；
- 720p 显示模式已能以正确尺度使用；
- 外放与普通有线耳机播放正常；
- 通过运行时路由实验，已经证明 `QUAT_MI2S → ESS9018 → OPA1612 → 耳机插孔` 能持续有声；
- R6 已通过：改变 Android 媒体音量不会改变 ES9018 `Volume` kcontrol，二者是叠加关系；
- R7-A 已通过：`205 → 213 → 205` 连续、有声，无爆音、失真、单边或断续，并完成恢复；
- 当前安全恢复基线为 `Volume = 205 205`；
- R7-B 的 `225` 尚未实测。

设备基线只能证明原版 MoKee 与临时运行态实验；它不能证明 M3 HAL 补丁已经进入手机。

## 3. 音量链条的新事实

### 3.1 `Volume` 的真实语义

从 M2 实际启动内核的 ES9018 `snd_kcontrol_new` 表中已经离线闭合：

```text
min    = 0
max    = 255
invert = 1
TLV    = -127.50 dB + 0.50 dB × control_value
```

在当前有效区间中，控件值越大，输出越响。关键点为：

| 状态 | 控件值 | 对应数字增益 |
|---|---:|---:|
| MoKee `mixer_paths.xml` 默认 | 205 | -25.0 dB |
| MIUI `hifi_volume=30` 的 HAL 映射结果 | 225 | -15.0 dB |
| MIUI `hifi_volume=40` 的 HAL 映射结果 | 229 | -13.0 dB |

因此，MoKee 当前基线相对 `225` 存在 **10 dB** 缺口，相对 `229` 存在 **12 dB** 缺口。
这足以解释用户报告的“同一 Android 音量刻度下明显更轻”。

### 3.2 原厂映射

stock HAL 的 `set_hifi_volume` 把逻辑值 `v` 映射为：

```text
ESS Volume control = v × 40 / 100 + 213
```

调用者包括初始化时读取 `persist.audio.hifi.volume`，以及处理 `hifi_volume` 参数。原厂
HiFi 与普通耳机拥有独立音量记忆的用户观察，与该控制结构相符。

### 3.3 当前裁决

- `Volume=205` 不是内核不可变默认值，而是 MoKee/stock 共用 `mixer_paths.xml` 顶层
  `HIFI` 默认块写入的配置值；
- `QUAT_MI2S_RX Volume=8192` 已经是最大值，不是当前响度缺口的来源；
- R7-B 若证明 `225` 连续、无异常且主观响度合理，可把它提升为 M3 v1 的候选进入增益；
- 在 R7-B 完成前，`225` 仍是**高可信候选**而不是发布默认值；
- M3 v1 可以采用“确定性 ESS 基准增益 + Android 媒体音量软件衰减”，但这仍不等于已经实现
  MIUI 式独立 HiFi 音量 UI。

## 4. 路由与 M3 控制器的关键发现

### 4.1 设备选择本质

stock `platform_get_output_snd_device` 对 HiFi 耳机的选择本质上读取一个布尔状态；没有阻抗、
格式或流类型参与该选择。这支持 M3 先实现简单、确定性的有线 HiFi 状态机，而不复制并不存在
的“按阻抗自动决定 HiFi”逻辑。

### 4.2 数字设备编号不可跨代搬运

stock 的数值设备编号 `34` 对应 `hifi-headphones`，但 MoKee 枚举中间插入了新设备，编号
`34` 已对应其他输出。M3 必须在 MoKee 枚举和三张映射表内新增/使用正确的符号条目，禁止
直接复用 stock 数字。

### 4.3 mixer 路径由两部分组成

实际路径名由：

```text
use_case_table[id] + " " + backend_tag_table[snd_device]
```

组成。只增加 `snd_device` 而不增加 `backend_tag_table` 的 `hifi-headphones` 条目，最终仍会
选择普通 `deep-buffer-playback`，静默回到 SLIMBUS。`hw_interface_table` 与后端匹配表也必须
同步闭合。

### 4.4 首版钩子位置曾经错误，现已修正

早期补丁把 QUAT 后端确定性配置放在 `check_and_route_playback_usecases()` 路径中；但此时
`usecase->out_snd_device` 仍是旧设备，导致：

- 标准耳机 → HiFi 时不触发；
- HiFi → 标准耳机时反而触发。

最新 Claude 补丁已把钩子移动到 `enable_snd_device()`：该位置第一次看到新设备，并早于
`enable_audio_route()` 启动 DAI。这是本轮最重要的正确性修复。

### 4.5 后端配置必须确定性写入

原 HAL 对非特定 offload usecase 不是“主动写 48 kHz”，而是直接返回、什么也不写；并且
QUAT 采样率没有 teardown 复位点。这意味着一次 44.1 kHz offload 可能把控件遗留给后续
deep-buffer 流。M3 进入 HiFi 时必须明确写入并读回 `KHZ_48 / S24_LE`，而不是依赖遗留状态。

### 4.6 并发通知音是必须实测的风险

HiFi 与普通 SLIMBUS 被识别为不同后端。额外通知音可能保留普通 `headphones` 路径，使
`HPHL DAC Switch` 再次打开。M3 v1 的安全策略是检测到该模拟出口即回退；A16 必须验证
通知音、多 usecase 和回退行为。

### 4.7 失败语义

最新补丁把瞬态的控件缺失/ESS 未绑定改为最多两次有界只读重探测；设备表结构不匹配才永久
禁用本次 boot 的 HiFi。失败不能阻止普通耳机播放或系统启动。

## 5. SRC 的当前事实与边界

- Apple Music 的 44.1 kHz track 在当前 MoKee 中进入 48 kHz AudioFlinger/HAL，并以
  48 kHz 到达 QUAT backend；SRC 已被实机确证；
- stock MIUI 的 deep-buffer 路径同样没有证明消除了 44.1 → 48 SRC；
- stock 的 44.1 backend 配置活路径只覆盖严格的一个 offload usecase id；其他 offload id
  也未覆盖；
- 不能通过简单把 deep-buffer backend 改成 44.1 kHz 来宣称解决 SRC，这可能只会把 SRC
  从 AudioFlinger 转移到 ADSP，或造成前后端速率错配；
- DIRECT PCM 是否映射到用户可达的 offload usecase 族仍未闭合。若答案为否，M3.5 的
  44.1 直通可能没有应用可达入口，应明确判不可行，而不是继续盲改。

因此，SRC 保持为 M3.5 独立里程碑；M3 首先保证 48 kHz/S24_LE 的确定性、安全 HiFi 路由。

## 6. M3 补丁资产与代理交付

### 6.1 Claude 分支

工作树：`/Users/km/Desktop/Leo-Audio-OS-claude-opus5`  
分支：`research/claude-opus5-hifi-architecture`  
当前提交：`b99b728`

关键提交序列：

```text
120b732  Add the M3 HiFi controller patch series draft
ac8ecd4  Add R6/R7 runbook and offline M3 verification scripts
53c5efd  Fix six defects found by auditing my own M3 patch series
ea3c428  Add host-mock fault injection and feature-off equivalence gate
971f83c  Record the M3 self-audit and the compile readiness assessment
b99b728  Update the M3 contract with boot persistence, R6/R7-A and the -5 evidence
```

主要资产包括五个 M3 patch、M3 契约、R6/R7 路书、host mock、feature-OFF 等价脚本、
源码谱系和编译准备报告。该分支尚未合并主分支。

截至本快照，新的 R7-B 任务书已经生成，但本机 Claude CLI 因未登录未能执行；在用户通过
已登录的 Claude 界面手动派发并收到结果前，状态仍为**未执行**。

### 6.2 agy 分支

工作树：`/Users/km/Desktop/Leo-Audio-OS-agy-gemini31pro`  
分支：`research/agy-gemini31pro-m3-build-gate`  
已提交基线：`0be365f`

`0be365f` 建立了独立构建门，但它验证的是旧 `ac8ecd4`，且使用了会抑制关键问题的
`-Wno-int-conversion` 与 `-Wno-implicit-function-declaration`。其“GO”只能解释为 GO 到下一层
编译验证，不能解释为 GO 到硬件或 ROM。

agy 已收到修正任务：改为验证 `b99b728`、启用严格警告、生成 ARM32 object，并尽最大可能
推进真实 Android HAL 链接。截至本快照，构建门脚本存在未提交修改，任务尚未交付最终报告。

## 7. 主代理独立复核

对 Claude 最新 `b99b728`，已经完成以下独立复核：

| 验证 | 结果 |
|---|---|
| `git diff --check ac8ecd4..b99b728` | CLEAN |
| patch contract | 34 PASS / 0 FAIL |
| host mock | 88 PASS / 0 FAIL |
| feature OFF token equivalence | 三个目标源文件全部一致 |
| 最新 patch 应用于干净 `7f4cac74` 源码 | 成功 |
| 严格 ARM32 syntax：`audio_hw.c` | PASS |
| 严格 ARM32 syntax：`platform.c` | PASS |
| 严格 ARM32 syntax：`leo_hifi.c` | PASS |
| ARM32 EABI5 relocatable objects | 三个文件全部生成成功 |

目标文件哈希：

```text
audio_hw.o   b6ea387c3467da90aa0cd38eb3e0315d58814b90173cf14425ea3d04dbbeafbf
platform.o   182421d82a6e7f96d0bef5238be0a5705779d4008a1f6f28e59a1e46180a9b89
leo_hifi.o   422050528c44d70c80820e3d5853c85bfb3d5c907f718d63555acdae3c327cc9
```

这些结果把 M3 从“可应用源码草案”推进为“高可信编译候选”，但 relocatable object 不是
Android HAL 共享对象，不能检查真实 `DT_NEEDED`，也不能证明 ROM 可启动或设备可播放。

## 8. 当前证据门裁决

| 层级 | 当前状态 | 裁决 |
|---|---|---|
| 架构与控制流 | 关键缺陷已修，仍待最终集成审计 | GO |
| Patch 应用与静态契约 | 通过 | GO |
| Host mock / 故障注入 | 88/88 | GO |
| 功能关闭等价性 | 通过 | GO |
| ARM32 严格语法与 object 生成 | 通过 | GO |
| Android HAL 模块编译 | 未证明 | BLOCKED/PENDING |
| `audio.primary.msm8994.so` 真实链接 | 未完成 | NO-GO |
| ROM 集成与离线镜像审计 | 未开始 | NO-GO |
| M3 上机 | 未授权、产物不存在 | NO-GO |
| R7-B `225` 增益 | 未执行 | PENDING |
| A16 通知音/多 usecase | 未执行 | PENDING |
| 44.1 kHz SRC / M3.5 | 未解决 | PENDING |

正式裁决：

> M3 当前是高可信的源码/编译候选，不是可刷写候选。

## 9. 下一阶段路书

### Gate 1 — R7-B 实机标定

1. 只读确认 ADB、耳机、播放、`Volume=205`、路由与 PCM；
2. 在用户明确佩戴耳机并播放后，设置独立自动恢复机制；
3. 短时执行 `205 → 225`，读回并采集主观/客观结果；
4. 无条件恢复 `205` 并读回；
5. 只有连续、有声、无爆音/失真/单边/断续且恢复成功，才把 `225` 提升为 M3 候选值。

该实验只允许易失 mixer 写入；禁止重启、刷分区、改系统文件或持久属性。

### Gate 2 — 最新补丁真实构建

1. 以 `b99b728` 和干净 `7f4cac74` 为唯一输入；
2. 审阅 `platform_api.h`、`Android.mk` 与 `LEO_HIFI_ENABLED` 传播；
3. 使用真实 Android/CAF 头文件与构建规则完成模块编译；
4. 链接出真实共享对象后才检查导出符号和 `DT_NEEDED`；
5. 记录第一条决定性失败命令与最小缺失输入，不用宽泛错误列表代替根因。

### Gate 3 — 集成裁决

1. Codex 对 Claude 与 agy 结果进行交叉复核；
2. 只选择经过裁决的提交/文件进入主分支，不整分支盲目合并；
3. 生成 M3 HAL 候选和 feature-OFF 对照产物；
4. 完成 system 镜像离线审计、哈希、回退材料与写入路书；
5. 另行取得设备写入授权。

### Gate 4 — M3 实机矩阵

至少验证首次播放、暂停/恢复、快速切歌、息屏、插拔、通知音、多播放器、AudioFlinger/HAL
重启、ESS probe 失败、旁路检测、增益恢复和普通耳机回退。任何“有声音”都必须同时有路由
读回，防止 QUAT 与 SLIMBUS 双通路假阳性。

### Gate 5 — M3.5 SRC

M3 稳定后再裁决 DIRECT/offload 用户可达性；只有 App → AudioPolicy → AudioFlinger → HAL →
ALSA frontend → QUAT backend → 时钟家族全部闭合，才讨论端到端 44.1 kHz。否则交付目标应改为
可解释、可报告的 SRC，而不是虚假的 bit-perfect。

## 10. 资源使用裁决

- Claude 本轮已经完成高价值架构修正，应冻结 `b99b728`；除 R7-B 或真实链接错误的定点审计外，
  不再让其进行宽泛自审；
- agy 适合承担可重复脚本、编译环境探测、头文件/符号闭合和构建证据工程；
- Codex 保持架构裁决、实机安全门、跨分支整合与最终 GO/NO-GO；
- 在真实链接或 SRC 架构出现新证据前，继续增加长篇推演的边际收益低于执行现有证据门。

## 11. 不得误读的状态

- “任务书已派发”不等于任务已完成；
- “patch applies”不等于能编译；
- “object 生成”不等于 Android 模块链接；
- “模块链接”不等于 ROM 可启动；
- “有声音”不等于 ESS 是唯一模拟出口；
- “225 理论对应 -15 dB”不等于 R7-B 已通过；
- “硬件支持 44.1 kHz 时钟家族”不等于 Apple Music 可以 bit-perfect；
- 在所有离线门、回退材料和临场授权闭合前，禁止写入 M3 候选。
