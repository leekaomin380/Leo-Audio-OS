# Phase 5B M2：未修改 MoKee 实机基准与 ESS 路由因果验证

日期：2026-08-28
候选：`MK100.0-leo-221019-RELEASE`，未经音频覆盖、未经删包、未注入 GApps/Magisk
写入范围：仅 `system`（`695eba5e…fe7b`）；`boot` 为临时 `fastboot boot`，未持久写入

## 0. 裁定

1. **MoKee 原版不把耳机音频路由到 ESS9018。** 它走 SLIMBUS_0 → WCD9330 "Tomtom"
   内置耳放。`docs/HANDOFF-2026-08-26-PHASE-5B-MOKEE.md` §11 中「原版 MoKee 可通过
   ESS 输出普通耳机音频」这一条**高可信推断被实机否定**。
2. **但 ESS 硬件链在 MoKee 上完整可用。** 手动改写单个 mixer 控件即可让音频经
   QUAT MI2S → ES9018 → OPA1612 输出，并已通过 A/B/A 因果验证。
3. 因此 M1 的架构裁决**成立且范围进一步缩小**：缺口纯粹在 HAL 的输出设备选择逻辑，
   内核、DTB、mixer XML、声卡枚举**均无需改动**。

## 1. 运行时身份

```
ro.build.fingerprint  Xiaomi/mokee_leo/leo:10/QQ3A.200805.001/eng.buildb.20221022.184840:userdebug/dev-keys
ro.mk.version         MK100.0-leo-221019-RELEASE
Android 10 / SDK 29 / security patch 2022-08-05
SELinux Permissive · ro.secure=0 · ro.debuggable=1 · ro.adb.secure=0
/ 挂载于 mmcblk0p41 只读（system-as-root）；/data mmcblk0p43 ext4 未加密
```

与 `manifests/mokee-m2-baseline-candidate-v0.1.json` 及 M0/M1 静态审计的每一条预测一致。

## 2. ESS9018 驱动已 probe 并绑定

```
/sys/bus/i2c/devices/6-0048/name    = es9018
/sys/bus/i2c/devices/6-0048/driver → /sys/bus/i2c/drivers/es9018
/sys/bus/i2c/devices/6-0048/resetb → gpio886（读回 1，已解复位）
/sys/bus/i2c/drivers/ 中存在 es9018
```

I2C bus 6 地址 0x48，与静态审计的 DTB `es9018@48` 节点一致。该驱动 probe 时不打印
内核日志，sysfs 绑定是比日志更强的证据。

声卡：`msm8994-tomtom-mtp-snd-card`（单卡，1017 个控件）。
QUAT MI2S 前后端 PCM 设备 `00-44`、`00-70`、`00-71` 均在位。

## 3. 与 MIUI 黄金链的运行时对照

对照样本：归档 `runtime-states/20260824-153316-H1`（Phase 4 写入前的 MIUI，插耳机播放态）。

| 项 | MIUI 黄金链 | MoKee 原版 |
| --- | --- | --- |
| 声卡名 | `msm8994-tomtom-mtp-snd-card` | **完全相同** |
| 播放路由 | `QUAT_MI2S_RX Audio Mixer MultiMedia1` = **On** | `SLIMBUS_0_RX Audio Mixer MultiMedia1` = **On** |
| QUAT 路由 | On | 全部 Off |
| 前端 PCM | S16_LE / 48000 / 2ch / period 960 / buffer 4800 | **完全相同** |
| QUAT_MI2S BitWidth | `S24_LE` | `S24_LE` |
| QUAT_MI2S SampleRate | `KHZ_48` | `KHZ_48` |
| QUAT_MI2S_RX Volume | 8192 | 8192 |

**声卡名相同**，故 MoKee HAL 未走 I2S 分支的原因不是声卡枚举差异。
内核控件三项取值完全一致，仅索引号偏移 4（MoKee 多 4 个控件）。

MoKee 实际通路（实测）：

```
MultiMedia1 → SLIMBUS_0_RX → SLIM RX1/RX2 MUX = AIF1_PB
            → RX1/RX2 MIX1 INP1 → RX1/RX2 INTERP = MIX2
            → CLASS_H_DSM MUX = DSM_HPHL_RX1 → HPHL DAC Switch = On
            → HPHL/HPHR Volume 19
```

MIUI 侧该 Tomtom 通路基本闲置（仅 `SLIM RX1 MUX`，无 `HPHL DAC Switch On`、无 Class-H）。

## 4. MIUI 的 HiFi 调用链

从归档 logcat 还原（`runtime-states/20260824-153316-H1/audio-logcat.txt`）：

```
persist.audio.hifi        = true
persist.audio.hifi.volume = 30

platform_get_output_snd_device: exit: snd_device(hifi-headphones)
select_devices: out_snd_device(34: hifi-headphones) in_snd_device(0: )
hw_info_append_hw_type: device_name = hifi-headphones
enable_snd_device: snd_device(34: hifi-headphones)
enable_audio_route: apply mixer and update path: deep-buffer-playback hifi-headphones
W msm8974_platform: HiFi backend bitwidth 0, samplerate 0
```

要点：

- `SND_DEVICE_OUT_HIFI_HEADPHONES` 的枚举值为 **34**；
- 应用的 mixer path 名为 **`deep-buffer-playback hifi-headphones`**，即使用
  **deep-buffer** 而非 low-latency 或 compress-offload；
- 前端 PCM 两侧均为 `S16_LE / 48000`。**24-bit 只存在于 QUAT backend**，
  位宽转换发生在 AFE/backend 侧，不在前端。这回答了 `docs/HANDOFF` §8.3
  关于「16-bit 流如何进入 24-bit QUAT backend」的问题。

## 5. mixer_paths.xml：差异只有一个控件

MoKee 的 `/vendor/etc/mixer_paths.xml` 与 MIUI stock 逐字节相同，**已包含全部五条
hifi 路径**：`hifi-headphones`、`deep-buffer-playback hifi-headphones`、
`low-latency-playback hifi-headphones`、`audio-ull-playback hifi-headphones`、
`compress-offload-playback hifi-headphones`。

```xml
<path name="deep-buffer-playback">                    <!-- MoKee 走的 -->
    <ctl name="SLIMBUS_0_RX Audio Mixer MultiMedia1" value="1" />
</path>

<path name="deep-buffer-playback hifi-headphones">    <!-- MIUI 走的 -->
    <ctl name="QUAT_MI2S_RX Audio Mixer MultiMedia1" value="1" />
</path>

<path name="hifi-headphones">                          <!-- 空 -->
</path>
```

`hifi-headphones` 路径为空，说明 **ESS 的上电、时钟与 mute 时序不由 mixer 控制**，
而由内核 es9018 codec 驱动与 machine driver 在 QUAT MI2S DAI 启动时完成。

`mixer_paths_i2s.xml` 中不含任何 hifi 路径；HAL 实际读取的是 `mixer_paths.xml`。

## 6. 运行时路由实验与因果验证

音源：本地生成 440 Hz / -20 dBFS / 44.1 kHz / 16-bit / 立体声 WAV，
经 Phonograph（`com.kabouzeid.gramophone.mokee`）以 deep-buffer 播放。
前端 PCM 实测为 `S16_LE / 48000`（AudioFlinger 重采样 44.1→48）。

### 6.1 后端启动的客观证据

翻转 `QUAT_MI2S_RX Audio Mixer MultiMedia1` 即触发 machine driver：

```
msm8994_quat_mi2s_snd_startup: dai name qcom,msm-dai-q6-mi2s-quat.211
                               substream=subdevice #0 stream=0 bit width=6
msm8994_quat_mi2s_snd_startup: switch on mbhc vddio.
```

`bit width=6` 对应 `S24_LE`（对照同日志中 TERT MI2S 的 `bit width=2` = S16_LE）。
**QUAT 后端以 24-bit 启动，与 MIUI 一致。** 该日志在三次独立切换中复现。

### 6.2 A/B/A 因果验证

第一次尝试失效：关闭 QUAT 路由后 AudioFlinger 立即另开
`SLIMBUS_0_RX Audio Mixer MultiMedia5`，经 Tomtom 耳放出声，造成假阳性。
该混淆由内核日志法而非听感发现。

消除混淆后的判定配置：

| 态 | QUAT←MM1 | HPHL DAC Switch | SLIM RX1/2 MUX | pcm0p | 听感 |
| --- | --- | --- | --- | --- | --- |
| A | **On** | Off | ZERO | RUNNING | **有声** |
| B | **Off** | Off | ZERO | RUNNING | **无声** |

B 态下 `SLIMBUS_0_RX ← MultiMedia5` 仍出现，但其模拟出口已被
`HPHL DAC Switch=Off` 与 `SLIM RX MUX=ZERO` 切断，故不成为混淆源。

**结论：耳机插孔上的音频仅经 QUAT_MI2S → ES9018 → OPA1612 抵达。因果闭合。**

本实验全部为运行时 mixer 写入，不持久，重启即清除，未修改任何文件或分区。

## 7. 附带发现

### 7.1 MBHC 阻抗检测依赖 QUAT 后端

```
QUAT 启动前   HPHL Impedance 36371472   HPHR 289993      （无效值）
QUAT 启动后   HPHL Impedance 34923      HPHR 35481   HPH Type 2
MIUI 参照     HPHL Impedance 34876      HPHR 37467
```

`msm8994_quat_mi2s_snd_startup` 中的 `switch on mbhc vddio` 为 MBHC 供电，
阻抗检测随即给出与 MIUI 同量级的合理值。**MoKee 原版阻抗检测失效的根因是它从不
启动 QUAT 后端**，而非检测电路或驱动缺陷。这为 `docs/17` §4「第一版不承诺按阻抗
自动切换」提供了具体依据：在 HiFi 路径建立之前，阻抗值不可信，不能作为策略输入。

### 7.2 MultiMedia5 竞态

每次主路由被切断，AudioFlinger 即另开 `SLIMBUS_0_RX ← MultiMedia5`。
M3 的 HAL 补丁必须处理流切换期间的竞态，否则会出现「HiFi 路由被系统静默绕过」
而状态显示仍为已激活的情况——这正是 `docs/17` §3 中 `HIFI_DEGRADED` 与
`effective_mode` 只反映读回结果的设计理由。

### 7.3 显示 bring-up 缺陷（非音频）

```
wm size            720x1280
fb0 virtual_size   720,2560
Physical density   560 (xxxhdpi)
dmesg              mdss_fb_register: FrameBuffer[0] 720x1280 registered successfully!
```

面板实为 1440×2560。设备所有者确认该机原生运行于 2560×1440，MIUI 另提供降至
1080p 的省电选项——**720×1280 不是该机任何一个合法模式**，属 bring-up 缺陷而非配置选择。

MoKee 内核仅按 720×1280 注册 framebuffer，而 density 仍按 1440×2560 面板上报
（`ro.sf.lcd_density=560`），两者相差一倍，导致全部视觉元素放大约一倍，自开机动画起即可见。

补充证据（本轮实测）：

- bootloader 传入的 `mdss_mdp.panel=1:dsi:0:qcom,mdss_dsi_jdi_scale_wqhd_command:1:none`。
  该 cmdline 由 aboot 生成，而本项目从未写过 firmware，**故 MIUI 与 MoKee 收到的是同一条**；
- stock 与 MoKee 的 DTB25 面板节点**清单与尺寸定义完全相同**（含
  `qcom,mdss_dsi_jdi_scale_wqhd_command`）。两份 DTS 全量差异仅 68 行，其中与显示相关的
  只有 MoKee **缺少 5 处 `qcom,mdss-dsi-panel-id` 属性**；
- `wm density 280` 可使几何恢复正常（布局正确、画面偏软），属**权宜手段**，
  它不恢复丢失的像素，也不触及 framebuffer 本身。

因此缺陷位于内核 mdss 的面板匹配或 DTB `panel-id` 缺失，而非 Android 层配置；
正式修复很可能需要内核或 DTB 改动，即需要 Linux 构建主机。

M0/M1 静态审计已在 §3 明确将「显示面板 DTB 差异」划出审计范围，此缺陷落在该已知
未审计区域内，**不属意外**。修复归入 M4 / Phase 5C 的显示 bring-up 工作。

### 7.4 实际运行的 HAL 为 32-bit

```
pid 442  /vendor/bin/hw/android.hardware.audio@2.0-service  → audio.primary.msm8994.so（32-bit）
pid 474  /system/bin/audioserver                            （64-bit）
```

`manifests/mokee-audio-delta-v0.1.tsv` 中 `audio-hal-64` 一行要求的 runtime_test
（确认实际进程 ABI）由此闭合：**M3 的补丁目标为 32-bit HAL
`701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47`。**

`org.mokee.audiofx` 在运行，属 M4 删减候选。

## 8. 对 M3 的意义

已排除的可能：

- 内核——ESS 驱动已 probe、绑定、reset GPIO 在位；
- DTB——音频目标节点语义与 stock 一致（M0/M1 已证）；
- mixer 控件——QUAT 三项控件齐备且默认值与 MIUI 相同；
- mixer XML——五条 hifi 路径已随 `mixer_paths.xml` 在设备上；
- 声卡枚举——两系统同名同卡；
- 模拟通路——A/B/A 已证明 ESS→OPA1612→插孔可出声。

剩余缺口：**MoKee HAL 的 `platform_get_output_snd_device()` 从不返回
`SND_DEVICE_OUT_HIFI_HEADPHONES`(34)**，以及与之配套的 `persist.audio.hifi`
判定、位宽/采样率设置与音量映射。

M3 的补丁面因此限定为 MoKee 的 Android 10 QCOM audio HAL 源码
（`mkq-mr1-caf-msm8994` / `7f4cac748b6f62897294cdaece9d1aec27e1e927`），
**不触碰内核、DTB、mixer XML、audioserver 或 framework**。

## 9. 尚未闭合

1. 音质未做任何评估。本轮仅用 440 Hz 测试音验证路由因果，不构成听感或仪器对照；
2. Spotify 全部验收未做（清除 userdata 后无 GApps、无登录态），按 `docs/18` §6.2
   记为 M2 未闭合项；
3. 外放路由、拔耳机下电时序、息屏、长时播放、温度与功耗未测；
4. SELinux AVC denial 未系统采集（当前为 Permissive，不具发布参考价值）；
5. ESS 的 switch/OPA/45M/49M GPIO 的具体控制点未定位——本轮由 machine driver
   自动完成，M3 需确认其在各种流切换下是否可靠；
6. `boot` 全程未持久写入。M2 结束后设备已回滚，最终状态见
   `docs/reviews/2026-08-28-phase5b-rollback-and-fault-handling.md`；
7. 本记录不构成任何写入授权。
