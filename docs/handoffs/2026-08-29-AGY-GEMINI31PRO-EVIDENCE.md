# 任务交接书：agy / Gemini 3.1 Pro — Leo/MoKee HiFi 底层证据工程

## 0. 任务身份

你是 Leo Audio OS 项目的**底层证据工程负责人**。目标是扩大、核验和组织原始证据，不负责决定
最终产品架构，也不操作手机。

- 项目：Xiaomi Mi Note Pro（代号 `leo`）专用网络音频播放器系统
- Git 基线：`a6b95bfb921336bb8452689cbff54b51833413e3` 之后创建的隔离分支
- 你的分支：`research/agy-gemini31pro-audio-evidence`
- 你的工作树：`/Users/km/Desktop/Leo-Audio-OS-agy-gemini31pro`
- 主项目只读参考：`/Users/km/Desktop/Leo-Audio-OS`

## 1. 唯一任务

建立三份可复现证据包，回答：

1. MoKee/CAF/AOSP 的哪个实现点导致 `leo` 不选择 `hifi-headphones`？
2. MIUI 的独立 HiFi 音量由哪些属性、函数和增益级实现？
3. MSM8994/leo 的 QUAT MI2S 如何在 44.1 kHz 与 48 kHz 时钟家族之间工作，当前哪里固定为
   48 kHz，最小可改点在哪里？

本轮不提出完整产品方案；可以列出候选解释，但必须给出支持、反证与置信度。

## 2. 固定实机事实

- MoKee `MK100.0-leo-221019-RELEASE`，Android 10 userdebug；
- 当前实际活动 HAL 是 32-bit `vendor/lib/hw/audio.primary.msm8994.so`；
- MoKee 默认走 `SLIMBUS_0_RX → WCD9330/Tomtom`，不选择
  `SND_DEVICE_OUT_HIFI_HEADPHONES`；
- `mixer_paths.xml` 已包含 `deep-buffer-playback hifi-headphones`，其关键差异是
  `QUAT_MI2S_RX Audio Mixer MultiMedia1 = 1`；
- 手动切断 WCD 出口并打开 QUAT 后，ESS9018 → OPA1612 在耳机插孔上持续有声，A/B/A 已闭合；
- MIUI 日志出现：

```text
persist.audio.hifi=true
persist.audio.hifi.volume=30
platform_get_output_snd_device: snd_device(hifi-headphones)
SND_DEVICE_OUT_HIFI_HEADPHONES=34
```

- 用户确认 MIUI HiFi 与普通耳机的音量记忆独立；
- Apple Music 与历史 Spotify 都观察到 44.1 kHz track → 48 kHz AudioFlinger/HAL →
  48 kHz QUAT backend；
- 内核资料显示 44.1 kHz 家族使用 45.1584 MHz，48 kHz 家族使用 49.152 MHz；当前
  QUAT backend fixup 默认 48 kHz / S24_LE。

这些是输入，不必重复证明；你的任务是定位其源码和二进制实现依据。

## 3. 必读材料

1. `docs/03-AUDIO-DEPENDENCY-CLOSURE.md`
2. `docs/04-OFFICIAL-KERNEL-AUDIO-PATH.md`
3. `docs/16-PHASE-5B-MOKEE-COMPATIBILITY-BRIDGE-RUNBOOK.md`
4. `docs/17-LEO-AUDIO-STATE-CONTRACT.md`
5. `docs/reviews/2026-08-27-phase5b-m0-m1-static-audit.md`
6. `docs/reviews/2026-08-28-phase5b-m2-mokee-runtime-baseline.md`
7. `docs/reviews/2026-08-29-mokee-hifi-live-route-and-volume-observation.md`
8. `manifests/mokee-audio-delta-v0.1.tsv`
9. `manifests/audio-property-contract-v0.1.tsv`

私有只读输入位于主项目，不要复制进 Git：

```text
/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/lib/hw/audio.primary.msm8994.so
/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/lib64/hw/audio.primary.msm8994.so
/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/etc/audio_policy_configuration.xml
/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/etc/mixer_paths.xml
/Users/km/Desktop/Leo-Audio-OS/resources/private/stock-system-tree/lib/hw/audio.primary.msm8994.so
/Users/km/Desktop/Leo-Audio-OS/resources/private/stock-system-tree/lib64/hw/audio.primary.msm8994.so
/Users/km/Desktop/Leo-Audio-OS/resources/private/stock-system-tree/etc/audio_policy.conf
/Users/km/Desktop/Leo-Audio-OS/resources/private/stock-system-tree/etc/audio_policy_configuration.xml
/Users/km/Desktop/Leo-Audio-OS/resources/private/stock-system-tree/etc/mixer_paths.xml
```

先对每个实际使用的二进制记录 SHA-256，防止把两版文件混为一谈。

## 4. 工作包 A：HAL 路由来源谱系

在 MoKee、LineageOS、AOSP、CodeAurora/CAF 或可验证镜像中定位与下列符号/逻辑对应的源码：

```text
platform_get_output_snd_device
SND_DEVICE_OUT_HIFI_HEADPHONES
hifi-headphones
persist.audio.hifi
persist.audio.hifi.volume
deep-buffer-playback hifi-headphones
QUAT_MI2S_RX Audio Mixer MultiMedia1
```

回答：

- MoKee 当前 HAL 最可能来自哪个仓库、分支、tag 或 CAF 基线？
- 32-bit 与 64-bit blob 的功能差异是什么，为什么实机加载 32-bit？
- 哪个条件分支应返回 `SND_DEVICE_OUT_HIFI_HEADPHONES`，MoKee 当前缺少的是代码、property、
  board flag、device enum、平台映射还是运行条件？
- 是否存在其他 `leo` ROM 或 MSM8994 + 外置 DAC 设备的已实现范例？

对每个候选给出 commit、文件、函数和精确代码位置；若源码只能相似匹配，明确标为“类比证据”。

## 5. 工作包 B：MIUI 独立 HiFi 音量

对 stock 与 MoKee 的 32-bit HAL 做可复现的静态差异分析：

- `strings`/UTF-16 字符串；
- 动态符号、导入导出、ELF section；
- 属性 API、mixer API、参数解析相关调用的交叉引用；
- 在可用工具范围内定位 `persist.audio.hifi.volume` 的引用函数；
- 搜索 `30` 不能单独作为证据，必须结合控制流、字符串或 API 参数；
- 识别其最终可能控制的是 Android volume index、软件衰减、QUAT 数字增益、ESS DAC 数字音量、
  OPA/模拟开关还是其他级。

输出至少包含：

| 结论 | stock 证据 | MoKee 证据 | 反证 | 置信度 |
|---|---|---|---|---|

若无法从 stripped blob 证明映射曲线，给出下一步最小动态观测需求，不得编造函数语义。

## 6. 工作包 C：44.1/48 kHz 与 QUAT 双时钟

定位并建立完整调用图：

```text
App AudioTrack / direct/offload profile
→ AudioPolicy output selection
→ AudioFlinger mixer/direct thread
→ Qualcomm primary HAL output config
→ ALSA frontend
→ msm8994 QUAT backend fixup/startup/hw_params
→ ES9018 codec/machine driver
→ 45.1584 / 49.152 MHz clock selection
```

必须回答：

- 固定 48 kHz 的每一个位置，以及其中哪些只是默认值、哪些是强制覆盖；
- `QUAT_MI2S SampleRate` kcontrol 是否真正影响 backend，还是被 fixup 覆盖；
- 44.1 kHz 时钟选择函数是否能在播放时动态使用；
- Android 10 的 mixed、direct、offload 三条输出路径中，哪条最可能保留 44.1 kHz；
- 如果 Apple Music 只创建普通 mixed AudioTrack，系统层面能否安全地让 primary output 跟随
  44.1 kHz；
- 需要修改 AudioPolicy、HAL、kernel 的最小候选点分别是什么。

不要把“硬件有 44.1 kHz 晶振”直接写成“Android 可以 bit-perfect”；中间每一层都要闭合。

## 7. 研究方法和网络边界

- 优先官方/原始源码：AOSP、LineageOS/MoKee 源码、可验证的 CAF 镜像或官方 Xiaomi kernel；
- 每个网页或仓库结论记录 URL、访问日期、commit/tag；
- 可以进行针对性浅克隆或单文件下载，但本机空间紧张，禁止克隆完整 AOSP/ROM 历史；
- 临时源码放在你的 worktree 内被 Git 忽略的 `research-cache/`，或系统临时目录；
- 不下载、不分发 ROM、GApps、Spotify/Apple Music APK 或专有音频 blob；
- 不上传本项目私有文件给任何外部服务；
- 网络资料可能过时，必须与本地二进制和实机记录交叉验证。

## 8. 交付物

在你的工作树创建：

```text
docs/research/AGY-MSM8994-HIFI-EVIDENCE.md
docs/research/agy-hal-evidence.tsv
docs/research/agy-samplerate-evidence.tsv
```

主文档必须包含：

1. 证据摘要，不超过两页；
2. 源码谱系和 commit 锁定结果；
3. HAL 路由定位；
4. 独立 HiFi 音量的二进制证据；
5. 44.1/48 kHz 全链调用图；
6. 相似设备实现的可移植性判断；
7. 相互矛盾的证据与可能解释；
8. `已证明 / 高可信 / 待验证 / 已否定` 表；
9. 给架构负责人最重要的五条输入；
10. 下一轮只读采集建议。

TSV 每行至少包含：`claim_id, layer, claim, evidence_type, source, commit_or_sha256, path_or_symbol,
excerpt_or_command, confidence, counterevidence, next_test`。

完成后可以在你的分支进行一个本地提交，但不要推送、不要合并到 `main`。

## 9. 严格禁止

- 不运行 `adb`、`fastboot` 或任何设备控制命令；
- 不修改或重打包 system/boot/ROM；
- 不修改主工作树 `/Users/km/Desktop/Leo-Audio-OS`；
- 不删除、移动或上传私有资产；
- 不推送 GitHub、不创建 release；
- 不读取或输出用户账户、token、序列号、代理节点或个人数据；
- 不把字符串命中、相似设备代码或模型推断写成已验证的 leo 事实；
- 不以“可能可行”替代精确的证据缺口。

需要新增真机观测时，只提交最小采集方案；由项目主代理评估并执行。
