# 任务交接书：Claude Opus 5 — Leo/MoKee HiFi 架构独立审计

## 0. 任务身份

你是 Leo Audio OS 项目的**独立首席架构审计者**。请形成自己的工程判断，不要仅改写项目现有结论。
你的工作会由项目主代理再次与实机证据交叉核验；你的结论不会直接授权刷机或修改手机。

- 项目：Xiaomi Mi Note Pro（代号 `leo`）专用网络音频播放器系统
- Git 基线：`a6b95bfb921336bb8452689cbff54b51833413e3` 之后创建的隔离分支
- 你的分支：`research/claude-opus5-hifi-architecture`
- 你的工作树：`/Users/km/Desktop/Leo-Audio-OS-claude-opus5`
- 主项目只读参考：`/Users/km/Desktop/Leo-Audio-OS`

## 1. 唯一任务

为 MoKee Android 10 设计一套**最小、可回退、可读回验证**的 Leo HiFi Controller，使：

1. 有线播放可自动进入 `QUAT_MI2S → ES9018 → OPA1612`；
2. HiFi 音量与普通耳机音量独立，且有明确的状态所有者和恢复规则；
3. 44.1 kHz 家族内容在满足条件时避免当前非必要的 `44.1 → 48 kHz` SRC；
4. 暂停、切歌、息屏、拔线、HAL 崩溃和初始化失败时有序关闭或安全回退；
5. UI 只能读取真实状态，不能直接写 mixer、I2C、sysfs 或危险 property。

本轮只做架构、源码边界和验证设计；不实现补丁、不构建镜像、不操作手机。

## 2. 已由实机证明的事实

以下是本任务的固定输入。若你认为其中存在矛盾，请列为争议项并引用证据，不要静默覆盖。

### 2.1 当前系统与运行状态

- MoKee：`MK100.0-leo-221019-RELEASE`，Android 10，userdebug；
- `system` 已写入 MoKee M2 候选；本轮启动使用 `fastboot boot` 临时 MoKee `boot.img`，尚未持久写入
  `boot` 分区；
- 当前系统可启动、联网、运行 Apple Music；用户已完成登录；
- 当前显示以 MoKee 的 720p 模式配合 `wm density 320` 正常使用。显示问题不属于你的任务；
- 当前活动音频 HAL 是 32-bit `vendor/lib/hw/audio.primary.msm8994.so`；
- SELinux 当前为 Permissive，属于研究系统状态，不是最终发布目标。

### 2.2 默认 MoKee 与手动 HiFi 路由

- MoKee 默认：`MultiMedia1 → SLIMBUS_0_RX → WCD9330/Tomtom`；
- MoKee 的 `mixer_paths.xml` 已包含 `hifi-headphones` 系列路径，但 HAL 不选择
  `SND_DEVICE_OUT_HIFI_HEADPHONES`；
- 实机以运行时 mixer 写入完成过 A/B/A 因果验证：

```text
QUAT_MI2S_RX Audio Mixer MultiMedia1 = On
HPHL DAC Switch                      = Off
SLIM RX1 MUX                         = ZERO
SLIM RX2 MUX                         = ZERO
```

- 在切断 WCD 模拟出口后，耳机仍持续有声；QUAT 关闭后无声。因此 ESS/OPA 硬件链在 MoKee
  内核上可用；
- `QUAT_MI2S_RX Volume = 8192`，为该控件最大值；
- 用户主观确认声音质感改变，但相同 Android 音量刻度下响度低于 MIUI HiFi。

### 2.3 MIUI 独立 HiFi 音量

MIUI 运行记录包含：

```text
persist.audio.hifi        = true
persist.audio.hifi.volume = 30
platform_get_output_snd_device: snd_device(hifi-headphones)
SND_DEVICE_OUT_HIFI_HEADPHONES = 34
```

设备所有者确认 MIUI 的 HiFi 与普通耳机具有相互独立的音量记忆。当前尚未证明
`persist.audio.hifi.volume` 的单位、写入者、映射曲线或最终控制的增益级。

### 2.4 当前 SRC 证据

- Apple Music track：44.1 kHz；
- AudioFlinger/HAL：48 kHz / PCM16；
- QUAT backend：48 kHz / S24_LE；
- 以前的 Spotify 运行记录也证明 44.1 kHz track 被转换为 48 kHz；
- 官方内核证据显示硬件同时具有 44.1 kHz 家族的 45.1584 MHz 时钟和 48 kHz 家族的
  49.152 MHz 时钟，但当前 backend fixup 默认强制 48 kHz。

## 3. 必读材料（按顺序）

1. `docs/VISION.md`
2. `docs/ROADMAP.md`
3. `docs/03-AUDIO-DEPENDENCY-CLOSURE.md`
4. `docs/04-OFFICIAL-KERNEL-AUDIO-PATH.md`
5. `docs/16-PHASE-5B-MOKEE-COMPATIBILITY-BRIDGE-RUNBOOK.md`
6. `docs/17-LEO-AUDIO-STATE-CONTRACT.md`
7. `docs/reviews/2026-08-27-phase5b-m0-m1-static-audit.md`
8. `docs/reviews/2026-08-28-phase5b-m2-mokee-runtime-baseline.md`
9. `docs/reviews/2026-08-29-mokee-hifi-live-route-and-volume-observation.md`
10. `manifests/mokee-audio-delta-v0.1.tsv`
11. `manifests/audio-property-contract-v0.1.tsv`

私有二进制只读参考位于主项目：

```text
/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/lib/hw/audio.primary.msm8994.so
/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/lib64/hw/audio.primary.msm8994.so
/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/etc/audio_policy_configuration.xml
/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/etc/mixer_paths.xml
/Users/km/Desktop/Leo-Audio-OS/resources/private/stock-system-tree/lib/hw/audio.primary.msm8994.so
/Users/km/Desktop/Leo-Audio-OS/resources/private/stock-system-tree/etc/audio_policy.conf
/Users/km/Desktop/Leo-Audio-OS/resources/private/stock-system-tree/etc/mixer_paths.xml
```

不得把这些专有二进制复制进 Git。

## 4. 必须回答的架构问题

### A. 所有权与边界

- HiFi 模式选择、独立音量、实际增益、采样率选择分别应由 HAL、AudioPolicy、framework、
  kernel driver 或只读状态服务中的哪一层负责？
- 哪些状态必须是单一写入者？哪些只能被观察？
- 是否需要修改 framework；若不需要，如何维持独立 HiFi 音量语义？

### B. 最小补丁面

- 第一版可用实现需要修改哪些源码文件/模块？
- 哪些 MIUI 行为可以重新实现，哪些专有逻辑必须通过现有 blob 调用或放弃？
- 选择源码补丁、薄 shim、配置改动或二进制替换时，各自的失败模式是什么？

### C. 采样率策略

- 单应用、单流、有线 HiFi 时，如何让 44.1 kHz track 到达 44.1 kHz QUAT backend？
- 系统提示音、多流混音、48 kHz 内容、App 切换时如何选择时钟家族？
- 动态切换会否导致爆音、变速、锁相延迟、stream teardown 或 HAL 重启？
- 哪些条件下只能接受高质量 SRC，而不能声称 bit-perfect？

### D. 独立音量策略

- `persist.audio.hifi.volume` 应如何解释、迁移或替代？
- Android 音量 index、软件衰减、QUAT 数字增益、ESS DAC 数字音量、OPA/模拟级中，应该调哪一级？
- 如何避免模式切换时把普通耳机高音量直接套入 HiFi 而产生突发响度？
- 如何保存、恢复、限幅并向 UI 展示而不暴露危险控制面？

### E. 状态机与失败安全

至少覆盖：首次播放、暂停 3 秒、快速切歌、插拔、息屏、多个播放器、HAL 崩溃、AudioFlinger
重启、ESS probe 缺失、QUAT 写入失败、ACDB 失败、采样率切换失败、重启后恢复。

请明确每条路径的：前置条件、写入顺序、读回证据、超时、回滚和最终状态。

## 5. 交付物

在你的工作树创建：

```text
docs/research/CLAUDE-OPUS5-HIFI-CONTROLLER-ARCHITECTURE.md
```

文档必须包含：

1. 一页执行摘要与推荐方案；
2. 分层架构和数据/控制流；
3. 最小补丁文件/模块清单；
4. HiFi 独立音量模型；
5. 44.1/48 kHz 决策表；
6. 状态机与故障回退表；
7. 分阶段实现顺序；
8. 真机验收矩阵；
9. 对现有 `docs/17` 的逐条修订建议；
10. `事实 / 高可信推断 / 假设 / 未知` 四类证据表；
11. 你认为项目主方案最可能犯错的三个地方；
12. 明确的 `GO / NO-GO` 条件。

所有源码结论需给出仓库、commit/tag、路径、函数名或行号。二进制结论需给出文件 SHA-256、工具、
命令和可复现输出摘录。不要把字符串存在当作函数必然执行的证明。

完成后可以在你的分支进行一个本地提交，但不要推送、不要合并到 `main`。

## 6. 严格禁止

- 不运行 `adb`、`fastboot`、`heimdall` 或任何设备控制命令；
- 不写入或格式化任何分区；
- 不修改主工作树 `/Users/km/Desktop/Leo-Audio-OS`；
- 不修改候选镜像、boot、system、私有资产或回退包；
- 不安装 GApps、Magisk、驱动或系统服务；
- 不推送 GitHub、不创建 release、不上传私有文件；
- 不读取、记录或输出 Apple/Spotify 登录信息、token、设备序列号或个人账户信息；
- 不把“架构合理”写成“真机已经验证”。

若发现需要真机数据，只列出最小只读采集请求、风险与预期证据，由项目主代理另行执行。
