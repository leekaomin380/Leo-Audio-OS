# MoKee 实机：HiFi 路由启用与独立音量状态发现

日期：2026-08-29  
范围：MoKee M2 候选的**运行时**验证；不修改 `system`、`boot`、HAL、mixer XML 或持久配置。

## 1. 本轮目标

在已经启动、显示密度校正且可以播放的 MoKee 系统中，验证耳机播放能否从默认的
Tomtom/WCD9330 通路切换至 Mi Note Pro 原生的 ESS9018 → OPA1612 通路；同时记录与
MIUI 黄金参照相比的音量行为。

本轮仅操作 ALSA mixer 运行态。其效果可被音频服务的重新路由或重启清除，不能被视为
持久功能，更不能作为发布实现。

## 2. 前置事实

- 当前输出：有线耳机，AudioFlinger 活动输出为 `AudioOut_1D`，`48000 Hz / PCM 16-bit /
  stereo`；
- 声卡：`msm8994-tomtom-mtp-snd-card`；
- ESS9018 已由 I2C `6-0048` 驱动绑定；
- 耳机阻抗读数为约 `34–36 kΩ`，属 QUAT 后端已启动时的有效量级；
- MoKee 默认把 `MultiMedia1` 送至 `SLIMBUS_0_RX` 与 WCD9330 的模拟耳机路径，不会主动
  选择 `hifi-headphones`。

上述事实与 `2026-08-28-phase5b-m2-mokee-runtime-baseline.md` 的 M2 基线一致。

## 3. 实际应用的临时路由

播放持续期间，读取后写入并再次读回以下 mixer 状态：

```text
QUAT_MI2S_RX Audio Mixer MultiMedia1 = On
HPHL DAC Switch                      = Off
SLIM RX1 MUX                         = ZERO
SLIM RX2 MUX                         = ZERO
```

意义：将活动流送入 `QUAT_MI2S`，并切断 WCD9330 的 `SLIM → HPHL DAC` 模拟出口，以防
AudioFlinger 另开 SLIMBUS 流造成“仍有声音”的假阳性。

## 4. 结果与结论

用户在该状态下持续听到声音，并明确感受到声音质感改变。结合已经完成的 A/B/A 断路实验，
本轮是对同一结论的实际内容播放复现：**播放流已能够经 QUAT_MI2S → ESS9018 → OPA1612
到达耳机插孔。**

同时，用户报告：在相同 Android 音量刻度下，HiFi 路径的响度明显低于默认路径。

这不是 `QUAT_MI2S_RX Volume` 未打开：其值已读回为 `8192`，即该控件的最大值。也不应
通过提高 `RX1/RX2 Digital Volume` 来补偿，因为那是被刻意切断的 WCD9330 模拟链相关控件，
会混淆或破坏验证条件。

## 5. 新的关键发现：MIUI 存在独立的 HiFi 音量状态

设备所有者确认，MIUI 原生系统中，“HiFi 模式”与普通耳机模式具有**相互独立的音量控制状态**。
这与此前 MIUI 运行记录中的属性相吻合：

```text
persist.audio.hifi        = true
persist.audio.hifi.volume = 30
```

因此，原厂 HiFi 实现不是单一的路由开关，而至少包含：

1. 输出设备选择：`SND_DEVICE_OUT_HIFI_HEADPHONES` / `hifi-headphones`；
2. QUAT/ESS 后端的有序上电、时钟和路由；
3. 与普通耳机音量分开的 HiFi 音量状态、映射曲线与恢复逻辑。

MoKee 当前仅临时完成第 2 项的一部分，Android framework 仍使用普通有线耳机的
`STREAM_MUSIC` 音量标尺；当前观测到的较低响度正符合这一差异。

## 6. 边界与禁止推断

- “听到声音且质感改变”不等于已经复刻 MIUI 的完整增益、失真、动态范围或保护策略；
- 未证明 `persist.audio.hifi.volume` 的单位、取值范围、写入者或与实际模拟增益的对应关系；
- 未验证曲目切换、暂停/恢复、息屏、插拔、音频服务重启后临时路由是否被重置；
- 未授权且不应盲目切换 `QUAT_MI2S_RX_DL_HL Switch` 或其他未知高增益控件；这类操作可能
  造成削波、突发响度或绕开原厂保护时序；
- 当前状态不是可宣布的 `HIFI_ACTIVE`，依据 `docs/17-LEO-AUDIO-STATE-CONTRACT.md` 应当
  归为“已验证的临时路由/待完整闭包”，而不是对用户界面宣称完整 HiFi 成功。

## 7. 后续工作（不在本轮执行）

1. 在 MIUI 参照系统采集普通耳机与 HiFi 两态的 mixer、AudioPolicy/HAL 日志、properties 与
   音量变化序列；重点锁定 `persist.audio.hifi.volume` 的读写点和映射函数；
2. 在 MoKee 的 32-bit `audio.primary.msm8994.so` 源码补丁中复现**设备切换与独立 HiFi
   音量状态**，而不是用 init 脚本或普通 App 直接写 mixer；
3. 为 Leo HiFi Controller 增加 `requested_hifi_volume`、`effective_gain_profile` 与可读回的
   故障状态，但普通 Leo Home 只显示简洁状态，不暴露危险增益控制；
4. 将音量匹配作为单独验收项：固定曲目、固定耳机、固定 SPL 测量条件下，与 MIUI 参照进行
   对比；验证无削波、无爆音、暂停后正确下电及故障安全回退。

## 8. 新增目标：最小化不必要的 SRC

本机实测 Apple Music 的 44.1 kHz track 进入 Android 音频栈后，AudioFlinger/HAL 与
QUAT 后端均为 48 kHz。此前 Spotify 的 44.1 kHz 流也有同一行为。因此在当前 MoKee 中，
`44.1 → 48 kHz` SRC 已被确证。

该问题**有可能在 MoKee 中改善**，但不能用“强行把所有输出固定为 44.1 kHz”的方式处理。
官方内核硬件资料显示 leo 具有两个时钟家族：44.1 kHz 家族对应 45.1584 MHz，48 kHz 家族
对应 49.152 MHz；当前 QUAT backend 的默认 48 kHz fixup 则是直接原因之一。

后续按以下顺序进行：

1. 先对 Apple Music 的真实播放状态采集 track、AudioFlinger、HAL、ALSA PCM、QUAT 采样率；
2. 审计 Android 10 AudioPolicy、32-bit Qualcomm HAL 与 `msm8994` machine driver，确定是否
   能为 `hifi-headphones` 选择 44.1 kHz backend 及对应时钟；
3. 只在单应用、单流、有线 HiFi 的受控情景中试验 44.1 kHz 直通；48 kHz 内容、系统提示音、
   多路混音与通话路径必须有明确回退策略；
4. 以读回的端到端采样率、无爆音/无变速、暂停下电、插拔与重启恢复作为验收条件；
5. 若 Android 混音模型或 App 输出本身不允许完整直通，交付目标改为“选择质量可控、可报告
   的 SRC”，而不是虚假的 bit-perfect 标识。

在完成上述证据前，当前安全做法是由用户以 Android 常规音量逐级调高至舒适水平，不自动写入
未知的增益控件。
