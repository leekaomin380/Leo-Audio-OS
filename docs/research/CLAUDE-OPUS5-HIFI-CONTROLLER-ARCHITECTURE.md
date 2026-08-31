# Leo HiFi Controller 架构独立审计（Claude Opus 5）

日期：2026-08-29
审计者身份：独立首席架构审计者（非项目主代理）
基线提交：`d25ccfc`（`research/claude-opus5-hifi-architecture`，派生自 `a6b95bf` 之后）
工作树：`/Users/km/Desktop/Leo-Audio-OS-claude-opus5`
执行边界：本轮**未连接设备**，未运行 `adb`/`fastboot`/`heimdall`，未写任何分区，未修改主工作树，未修改任何私有资产。全部结论来自
（a）项目已固化文档与 manifest，（b）对本地只读私有二进制的静态反汇编，（c）已归档的 M2 实机采集文本。

---

## 0. 一页执行摘要与推荐方案

### 0.1 本轮最重要的五条结论

| # | 结论 | 与项目现有结论的关系 |
| --- | --- | --- |
| **C1** | MIUI 的 HiFi **设备选择**是一个纯布尔量。`platform_get_output_snd_device()` 在有线耳机分支里只读 `my_data->hifi` 一个字节，为真返回 `34 (hifi-headphones)`，为假返回 `6 (headphones)`。没有阻抗、格式、采样率或流类型参与。 | 收敛并证实 `docs/reviews/2026-08-28` §8「缺口纯粹在 HAL 的输出设备选择逻辑」，并给出确切判据 |
| **C2** | MIUI 的**独立 HiFi 音量不是 Android 音量流**，而是 HAL 内部函数 `set_hifi_volume()` 向 ALSA kcontrol **`Volume`**（2 元素数组）写入 `reg = ⌊v×0.4⌋ + 213`，`v∈[0,100]`。HAL 自己用 `property_set("persist.audio.hifi.volume", …)` 持久化。 | 回答 `docs/reviews/2026-08-29` §5/§6「未证明单位、写入者、映射曲线与最终增益级」 |
| **C3** | **MIUI 本身也没有为 deep-buffer 消除 `44.1 → 48` SRC。** `platform_check_and_set_codec_backend_cfg()` 只在 `usecase->id == 3`（`compress-offload-playback`，本代 HAL 亦承载 direct-PCM）时才调用 `platform_set_hifi_backend_cfg()`。MIUI H1 日志里的 `HiFi backend bitwidth 0, samplerate 0` 正是"该路径从未被设置过"的直接证据。 | **修正** `docs/ROADMAP.md` Phase 5B 与 `docs/reviews/2026-08-29` §8 的隐含前提——"对齐 MIUI 即可拿到 44.1"不成立 |
| **C4** | `SND_DEVICE_OUT_*` 枚举在两代之间**编号不同**：MIUI `headphones=6 / hifi-headphones=34`；MoKee 因在索引 6 插入 `line`，`headphones=7`，OUT 段末尾为 `35 (voice-speaker-protected)`。把 MIUI 日志里的 `34` 搬进 MoKee 会命中 `speaker-protected`。 | 新增风险项；`docs/reviews/2026-08-28` §4 记录了 34 但未标注代际不可移植 |
| **C5** | `hifi-headphones` 在 stock 与 MoKee 的 `audio_platform_info.xml` / `audio_platform_info_i2s.xml` 中**都没有 `acdb_id`**。MIUI 原厂即以"device 34 缺少 ACDB ID"的告警状态运行 HiFi。 | **必须修改** `docs/17` §5 的证据门：现写法（"Forte ACDB/loader 没有失败"）对 HiFi 设备**永远不可能以"有校准"方式通过** |

### 0.2 推荐方案（一句话）

> 在 MoKee 的 32-bit `hal/msm8974/platform.c` + `hal/audio_hw.c` 上实现一个**只有一个真实状态写入者、全部经读回确认、默认 fail-safe 到 `headphones` 的 Leo HiFi Controller**；独立音量由 HAL 拥有并写入 ES9018 的 `Volume` kcontrol，通过**新的 `vendor.leo.audio.*` property 与 HAL `set_parameters` 键**驱动，**不改 framework**、**不复用 MIUI 的 `persist.audio.hifi*` 语义**；采样率目标从"消除 SRC"下调为"**在受控单流场景做 44.1 直通实验，其余场景诚实报告实际输出率**"。

理由：C1/C2 证明能力缺口小且边界清晰（三个函数 + 一张表 + 一个 kcontrol）；C3 证明 SRC 是 Android 混音模型问题而非 MIUI 移植问题，把它放进 M3 会污染一个本来可以干净验收的里程碑。

### 0.3 与项目当前方案的三个主要分歧

1. 项目把"独立 HiFi 音量"列为**需要复刻 MIUI 的 framework 语义**（`docs/reviews/2026-08-29` §5「Android framework 仍使用普通有线耳机的 `STREAM_MUSIC` 音量标尺」）。实测二进制显示 MIUI 的独立音量**完全在 HAL 内**，framework 只是一个 `setParameters("hifi_volume=N")` 的调用者。Leo 可以用自己的特权服务充当该调用者，framework 零改动。
2. 项目把 44.1 SRC 与 HiFi 路由并列为 M3 目标（ROADMAP Phase 5B 第 3 条）。本审计建议**拆分**：44.1 属于 M3.5/M4 的独立里程碑，且第一版明确不承诺 bit-perfect。
3. 项目的 `HIFI_ACTIVE` 证据门包含 "ACDB load 无失败"。C5 表明该条对 HiFi 设备是**结构性不可满足**的，必须改写为"ACDB 缺失是已知且预期的原厂行为"。

---

## 1. 分层架构与数据/控制流

### 1.1 所有权矩阵（问题 A 的直接回答）

| 关注点 | 唯一写入者 | 只读观察者 | 明确禁止 |
| --- | --- | --- | --- |
| HiFi 模式意图 `requested_mode` | Leo Audio Policy Service（system_server 之外的特权服务）→ 经 HAL `set_parameters` | Leo Home、维护页 | 任何普通 App、任何 init 脚本 |
| 输出设备选择（`SND_DEVICE_OUT_LEO_HIFI_HEADPHONES`） | audio HAL `platform_get_output_snd_device()` | 经 `get_parameters` / `dumpsys` | AudioPolicyManager 不参与；不得用 `audio_policy_configuration.xml` 强行绑定 |
| ESS/QUAT 供电、时钟、mute、OPA、模拟 switch | **kernel**（`es9018.c` + `msm8994.c` machine driver，由 QUAT MI2S DAI startup/shutdown 驱动） | HAL 读 sysfs/日志 | HAL 与用户态**不得**直接操作这些 GPIO/regulator |
| QUAT 后端位宽/采样率（`QUAT_MI2S BitWidth` / `SampleRate`） | audio HAL（`platform_set_hifi_backend_cfg()` 等价物） | 维护页读回 | 不得由 App、init.rc 或 `tinymix` 常驻脚本写 |
| HiFi 独立增益（ES9018 `Volume` kcontrol） | audio HAL（`set_hifi_volume()` 等价物） | 维护页读回；普通界面只显示 0–100 的抽象刻度 | 普通 UI 不得暴露原始寄存器值；不得写 `RX*/HPH*` 等 WCD 控件 |
| HiFi 音量持久化 | audio HAL（写 `vendor.leo.audio.hifi.volume`） | — | 不复用 `persist.audio.hifi.volume`（见 §4.4） |
| `effective_mode` / generation / 失败码 | audio HAL（只在读回成功后推进） | Status Service → UI | UI 不得从 `requested_mode` 推断 `effective_mode` |

**必须单写入者**：`requested_mode`、`hifi_volume`、后端 cfg、`effective_mode`。
**只能被观察**：ESS 上下电时序、阻抗值、QUAT 时钟、ACDB 结果、SELinux denial。

**是否需要改 framework：不需要。** 依据：`platform_set_parameters()` 与 `platform_get_parameters()` 已经是 HAL 的标准 HIDL 通道（Android 10 `android.hardware.audio@2.0` 的 `setParameters`/`getParameters`），任何持有 `MODIFY_AUDIO_SETTINGS`（或更严格的 signature 权限）的特权组件都能调用，无需修改 AudioService、AudioPolicyManager 或 AudioFlinger。MIUI 走的就是这条路（HAL 侧证据见 §2.2）。

### 1.2 控制流

```text
[Leo Home / 维护页]  ── 只读查询 ─────────────────┐
        │ (signature permission)                  │
        ▼                                         │
[Leo Audio Policy Service]  ── setParameters ─────┼──► audio HIDL 2.0 service (32-bit)
   持有意图: hifi_enabled, hifi_volume            │        │
   持久化交给 HAL，不自己写 property              │        ▼
                                                  │   audio.primary.msm8994.so
                                                  │    ├─ adev_set_parameters
                                                  │    │   └─ platform_set_parameters
                                                  │    │        ├─ "leo_hifi_mode"   → my_data->hifi
                                                  │    │        └─ "leo_hifi_volume" → set_hifi_volume()
                                                  │    ├─ platform_get_output_snd_device()
                                                  │    │        └─ hifi ? LEO_HIFI_HEADPHONES : HEADPHONES
                                                  │    ├─ select_devices() → enable_audio_route()
                                                  │    │        └─ audio_route_apply_and_update_path(
                                                  │    │             "deep-buffer-playback hifi-headphones")
                                                  │    └─ Leo HiFi Controller（新增，见 §3.3）
                                                  │         读回: mixer / sysfs / stream state
                                                  │         推进: HIFI_ARMING → HIFI_ACTIVE / DEGRADED
                                                  ▼
                              get_parameters("leo_hifi_status") ── 结构化只读快照
```

硬件侧（**不由 HAL 直接驱动**，只被观察）：

```text
QUAT_MI2S_RX Audio Mixer MultiMedia1 = 1
   → msm8994_quat_mi2s_snd_startup()   [switch on mbhc vddio; LPASS→slave; QUAT clk]
   → es9018 DAPM bias on               [5 路 regulator → 选晶振 → 解 reset → THD 补偿
                                        → soft start 150 ms → OPA/switch → unmute]
   → ES9018K2M → OPA1612 → 耳机插孔
```

---

## 2. 证据：MIUI 原厂 HiFi 到底做了什么

全部证据可用下列工具复现（macOS 26，`/usr/bin/objdump` = LLVM objdump 17）。文件哈希见 §10.1。

### 2.1 能力缺口的精确形状

```bash
/usr/bin/objdump -T resources/private/stock-system-tree/lib/hw/audio.primary.msm8994.so | grep -i hifi
```

```text
00012d0c g DF .text 000000dc  platform_get_hifi_property
00013008 g DF .text 00000090  platform_set_hifi_property
00013098 g DF .text 00000050  platform_get_hifi
000176a0 g DF .text 000002a8  platform_set_hifi_backend_cfg
00017948 g DF .text 000000f4  platform_check_hifi_backend_cfg
```

64-bit stock HAL（`4b3fb296…`）导出同名 5 个符号，地址 `0x13ccc / 0x13f5c / 0x13fd4 / 0x17bc8 / 0x17df8`。

MoKee 32-bit HAL（`701019bd…`）**导出 0 个**同类符号，且整个文件不含字符串
`hifi-headphones`、`QUAT_MI2S BitWidth`、`QUAT_MI2S SampleRate`、`SND_DEVICE_OUT_HIFI_HEADPHONES`、`persist.audio.hifi*`：

```bash
grep -rail hifi resources/private/phase5b-mokee/selected/
# → 仅 system/vendor/etc/mixer_paths.xml
```

两份 HAL 的日志 tag 都是 `msm8974_platform` / `audio_hw_primary`，即**同一套 CAF 源码布局**
（`hardware/qcom/audio/hal/msm8974/platform.c` 与 `hal/audio_hw.c`）。这是"最小源码补丁可行"的结构性依据。

### 2.2 设备选择：一个布尔量

`platform_get_output_snd_device` @ `0x142bc`，有线耳机分支 `0x145dc–0x14614`：

```text
145dc: tst  r4, #4                  ; devices & AUDIO_DEVICE_OUT_WIRED_HEADSET
145e0: beq  0x14604
145e4: bl   audio_extn_get_anc_enabled
145ec: bne  0x14604
145f0: bl   audio_extn_should_use_fb_anc
145f4: mov  r7, #26                 ; SND_DEVICE_OUT_ANC_HEADSET
145fc: movwne r7, #0x1b             ; SND_DEVICE_OUT_ANC_FB_HEADSET
14600: b    0x1451c
14604: ldrb r0, [r8, #0x74]         ; my_data->hifi
14608: mov  r7, #34                 ; SND_DEVICE_OUT_HIFI_HEADPHONES
1460c: cmp  r0, #0
14610: movweq r7, #0x6              ; SND_DEVICE_OUT_HEADPHONES
14614: b    0x1451c
```

等价 C：

```c
} else {                       /* 非 ANC 有线耳机 */
    snd_device = my_data->hifi ? SND_DEVICE_OUT_HIFI_HEADPHONES
                               : SND_DEVICE_OUT_HEADPHONES;
}
```

`my_data->hifi`（偏移 `+0x74`，1 字节）的两个写入点：

* `platform_get_hifi_property()` @ `0x12d0c`：`property_get("persist.audio.hifi", buf, "false")`，`strncmp(buf,"true",5)==0` 则返回 1；
* `platform_set_parameters()` @ `0x15b78+0x4c4`：解析 `str_parms` 键 **`hifi_mode`**，值 `"true"`/`"false"`，同时 `property_set("persist.audio.hifi", …)`，并在值发生变化时遍历 `adev->usecase_list`，对每个 `type == PCM_PLAYBACK` 的 usecase 调用 `select_devices(adev, uc->id)` 触发重路由。

`platform_set_hifi_property()` @ `0x13008` 只是 `property_set("persist.audio.hifi", enable ? "true" : "false")`。
`platform_get_hifi()` @ `0x13098` 只是返回 `my_data->hifi` 并打日志。

**判定**：MIUI 的 HiFi 判据里不含耳机阻抗、耳机类型、采样率、位宽或流类型。`docs/17` §4「第一版不承诺按阻抗自动切换」与原厂行为一致，可保留。

### 2.3 独立音量：ES9018 的 `Volume` kcontrol

静态函数 `set_hifi_volume(adev, left, right)` @ `0x12de8`（未导出，位于 `platform_get_hifi_property` 与 `platform_set_hifi_property` 之间）：

```text
12e34: ldr  r1, ="Volume"                  ; 字符串 @0x2c28e
12e38: ldr  r0, [r5, #0x9c]                ; adev->mixer
12e40: bl   mixer_get_ctl_by_name
12e4c: beq  <error: "%s: Could not get ctl for mixer cmd - %s">
12e50: add  r0, r6, r6, lsl #2             ; left*5
12e60: lsl  r0, r0, #3                     ; left*40
12e68: smmul r0, r0, #0x51EB851F           ; ÷100 magic
12e80: asr  r4, r0, #5
12e88: add  r0, r0, #213                   ; +213
    （右声道同样处理）
12eb4: add  r1, sp, #12
12ebc: mov  r2, #2
12ec0: bl   mixer_ctl_set_array            ; 写入 2 个元素
```

即：

```c
static void set_hifi_volume(struct audio_device *adev, int left, int right)
{
    struct mixer_ctl *ctl = mixer_get_ctl_by_name(adev->mixer, "Volume");
    if (!ctl) { ALOGE("set_hifi_volume: Could not get ctl for mixer cmd - Volume"); return; }
    int v[2] = { left  * 40 / 100 + 213,
                 right * 40 / 100 + 213 };
    mixer_ctl_set_array(ctl, v, 2);
}
```

调用者只有两个：

| 调用点 | 上下文 |
| --- | --- |
| `platform_init` @ `0x116f0` | `property_get("persist.audio.hifi.volume", buf, "0")` → `atoi` → `clamp(0,100)` → 存入 `my_data->hifi_volume`（`+0x78`）→ `set_hifi_volume(adev, v, v)` |
| `platform_set_parameters` @ `0x162d8` | 解析键 **`hifi_volume`** → `atoi` → `clamp(0,100)` → 存 `+0x78` → `set_hifi_volume()` → `property_set("persist.audio.hifi.volume", <原始字符串>)` |

映射表（`v` = 0…100）：

| `hifi_volume` | 0 | 25 | 30 | 40 | 50 | 75 | 100 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 写入 `Volume` 的寄存器值 | 213 | 223 | **225** | **229** | 233 | 243 | 253 |

M2 实机采集（`resources/private/phase5b-mokee/m2-runtime-20260828/tinymix-B-state.txt`）第 907 号控件：

```text
907  INT  2  Volume                                   205 205
```

**这是本轮对"响度偏低"最直接的解释**：MoKee 从不写这个控件，它停在内核驱动默认值 **205**，而 MIUI 的 HiFi 音量映射区间是 **[213, 253]**，最低点也比 205 高 8 步。项目 `docs/reviews/2026-08-29` §4 排除了 `QUAT_MI2S_RX Volume`（已在最大值 8192）是正确的，但漏掉了 ES9018 自身的数字音量级。

MoKee 内核（`kernel-image.bin`，`fbbd8d46…`）确实包含该驱动与该控件名：

```bash
strings -a resources/private/phase5b-mokee/boot-audit-v0.1/kernel-image.bin | grep -i es9018
# es9018_i2c_probe / es9018_hw_params / es9018_set_bias_on / es9018_set_bias_off
# ../../../../../../kernel/xiaomi/leo/sound/soc/codecs/es9018.c
strings -a … | grep -x Volume    # → Volume
```

### 2.4 采样率：MIUI 也没做 deep-buffer 的 44.1

`platform_set_hifi_backend_cfg(adev, bit_width, sample_rate)` @ `0x176a0` 的能力是**完整**的：

```text
0x176f0  mixer_get_ctl_by_name(adev->mixer, "QUAT_MI2S BitWidth")
0x17700  bit_width == 24 ? "S24_LE" : "S16_LE"     → mixer_ctl_set_enum_by_string
0x1785c  mixer_get_ctl_by_name(adev->mixer, "QUAT_MI2S SampleRate")
         44100→"KHZ_44P1"  48000→"KHZ_48"   64000→"KHZ_64"
         88200→"KHZ_88P2"  96000→"KHZ_96"  176400→"KHZ_176P4"
        192000→"KHZ_192"   其它→"KHZ_48"
```

但它**只有一个调用者**：`platform_check_and_set_codec_backend_cfg()` @ `0x17ec4+0x18c`。而该函数在 `0x1807c` 处的守卫是：

```text
17fbc: bl   voice_is_in_call
17fc4: bne  0x17fd8                  ; 通话中 → 用默认 48000/16
17fcc: ldr  r0, [r4, #0xa0]          ; adev->mode
17fd0: cmp  r0, #3                   ; AUDIO_MODE_IN_COMMUNICATION
17fd4: bne  0x1807c
1807c: ldr  r0, [r5, #0x8]           ; usecase->id
18080: cmp  r0, #3
18084: bne  0x18058                  ; ★ 不是 usecase 3 → 直接返回，不动 HiFi 后端
18088: ldr  r0, [r5, #0x1c]          ; usecase->stream.out
1808c: cmp  r0, #0
18090: beq  0x17ff8                  ; NULL → 48000/16
18094: ldr  r5, [r0, #0xb4]          ; out->sample_rate
18098: ldr  r7, [r0, #0x158]         ; out->bit_width
```

`usecase->id == 3` 是什么？从二进制里的 `use_case_table` 直接读出（stock `.data.rel.ro`，vaddr `0x32528` / 文件偏移 `0x31528`）：

```text
[0] deep-buffer-playback      [1] low-latency-playback
[2] multi-channel-playback    [3] compress-offload-playback   ← id 3
[4..11] compress-offload-playback2..9
[12] audio-ull-playback       [13] play-fm  …
```

MoKee 32-bit HAL 的同一张表（vaddr = 文件偏移 `0x29010`）**顺序完全一致**，`id 3` 同样是 `compress-offload-playback`。

**结论 C3**：MIUI 只为 compress-offload（本代 CAF HAL 同时承载 `direct_pcm`）路径设置 HiFi 后端速率。deep-buffer 与 low-latency 一律不设置，`QUAT_MI2S SampleRate` 保持内核默认 `KHZ_48`。

这与项目归档的 MIUI H1 日志完全吻合：

```text
enable_audio_route: apply mixer and update path: deep-buffer-playback hifi-headphones
W msm8974_platform: HiFi backend bitwidth 0, samplerate 0
```

该告警来自 `platform_check_and_set_codec_backend_cfg` @ `0x17fa8`，打印的是 `adev->0x16c` / `adev->0x168`，即 HiFi 后端 cfg 的缓存值。**打印 0,0 意味着 `platform_set_hifi_backend_cfg` 从未被调用过。**

因此：`docs/reviews/2026-08-29` §8「该问题有可能在 MoKee 中改善」在方向上成立，但**不能以"对齐 MIUI"为手段**——MIUI 在 Spotify/Apple Music 这类 deep-buffer 场景下与 MoKee 的 SRC 行为是一样的。

### 2.5 策略层不是阻塞点

MoKee `audio_policy_configuration.xml`（`b299109d…`）：

```xml
<mixPort name="primary output" flags="…FAST|…PRIMARY">
    <profile format="AUDIO_FORMAT_PCM_16_BIT" samplingRates="44100,48000" …/>
<mixPort name="deep_buffer" flags="AUDIO_OUTPUT_FLAG_DEEP_BUFFER">
    <profile format="AUDIO_FORMAT_PCM_16_BIT" samplingRates="44100,48000" …/>
<mixPort name="direct_pcm" flags="AUDIO_OUTPUT_FLAG_DIRECT">
    <profile … samplingRates="8000,…,44100,48000,…,176400,192000"/>
```

MIUI `audio_policy.conf`（`cfedbe8d…`）等价条目同样声明 `44100`，`direct_pcm` 另带 `AUDIO_OUTPUT_FLAG_DIRECT_PCM`（Android 9 后取消该 flag）。

即：**策略与内核都支持 44.1；真正的阻塞点是 AudioPolicyManager 不会为一条 44.1 kHz 的 `AudioTrack` 重开 primary/deep-buffer 输出线程**——deep-buffer/primary 输出在设备连接时以一个固定 config 打开，之后由 AudioFlinger 的 `MixerThread` 做 SRC。只有 `DIRECT`/`OFFLOAD` 输出才按 track 参数逐次打开。

### 2.6 ACDB

```bash
grep -n acdb resources/private/phase5b-mokee/selected/system/vendor/etc/audio_platform_info*.xml
```

`audio_platform_info_i2s.xml`（`06ba2074…`）只声明 7 个设备的 `acdb_id`（handset/speaker 系列），
`audio_platform_info.xml`（`8fa54477…`）只声明 4 个 `acdb_id`。**两者都没有 `SND_DEVICE_OUT_HIFI_HEADPHONES`。**
stock 侧同名文件语义相同（`manifests/mokee-audio-delta-v0.1.tsv` 记为"仅注释差异"）。

与 `docs/03` §"新发现的优化候选"第 5 条记录的"HiFi 启动时出现 device 34 缺少 ACDB ID"互为印证：**这是原厂的常态，不是缺陷。**

### 2.7 枚举编号的代际差异

从两份 HAL 的 `device_table` 直接读出（stock `.data.rel.ro` vaddr `0x32628` / 文件偏移 `0x31628`；MoKee vaddr = 文件偏移 `0x251e0`）：

| index | MIUI (Android 7) | MoKee (Android 10) |
| ---: | --- | --- |
| 5 | speaker-reverse | speaker-reverse |
| 6 | **headphones** | **line** |
| 7 | speaker-and-headphones | **headphones** |
| … | … | … |
| 33 | voice-speaker-protected | anc-handset |
| 34 | **hifi-headphones** | **speaker-protected** |
| 35 | handset-mic (IN 段开始) | voice-speaker-protected |
| 36 | handset-mic-ext | handset-mic (IN 段开始) |

MoKee 侧 `platform_get_output_snd_device` @ `0x17d04` 的对应分支：

```text
17f20: mov  r0, #7                  ; SND_DEVICE_OUT_HEADPHONES
17f24: tst  r4, #12                 ; WIRED_HEADSET | WIRED_HEADPHONE
17f28: bne  <return>
```

MoKee 无 ANC 分支（不调用 `audio_extn_get_anc_enabled`），补丁点比 MIUI 更简单。

---

## 3. 最小补丁面（问题 B 的直接回答）

### 3.1 目标源码

MoKee `mkq-mr1-caf-msm8994`，`hardware/qcom/audio` @ `7f4cac748b6f62897294cdaece9d1aec27e1e927`
（该提交号取自 `docs/reviews/2026-08-28-phase5b-m2-mokee-runtime-baseline.md` §8；本审计未能联网复核该提交，标记为**待核对**，但产物 `701019bd…` 的 log tag 与符号布局与该代 CAF HAL 一致）。

构建产物必须是 **32-bit** `audio.primary.msm8994.so`：M2 实机证据 `05-hal-state.txt` 显示
`pid 442 /vendor/bin/hw/android.hardware.audio@2.0-service` 加载的是 32-bit HAL；64-bit 副本在本机不承载播放。

### 3.2 文件/模块清单（第一版可用实现）

| # | 文件 | 改动 | 行数量级 | 风险 |
| --- | --- | --- | ---: | --- |
| P1 | `hal/msm8974/platform.h` | 在 `SND_DEVICE_OUT_*` 末尾（`voice-speaker-protected` 之后）追加 `SND_DEVICE_OUT_LEO_HIFI_HEADPHONES`，同步 `SND_DEVICE_OUT_END` / `SND_DEVICE_IN_BEGIN` | ~5 | 低，但见 §11 风险 1 |
| P2 | `hal/msm8974/platform.c` `device_table[]` | 追加 `"hifi-headphones"`（名称必须与 `mixer_paths.xml` 逐字一致） | 1 | 低 |
| P3 | `hal/msm8974/platform.c` `acdb_device_table[]` | 追加 `ACDB_ID_NONE` 占位并显式记录"无校准是预期行为" | 1 | 低 |
| P4 | `hal/msm8974/platform.c` `platform_get_output_snd_device()` | 有线耳机分支改为 `my_data->leo_hifi ? LEO_HIFI_HEADPHONES : HEADPHONES` | ~4 | 中 |
| P5 | `hal/msm8974/platform.c` `platform_init()` | 读 `vendor.leo.audio.hifi.enable` / `vendor.leo.audio.hifi.volume`，clamp，缓存，`leo_set_hifi_volume()` | ~20 | 低 |
| P6 | `hal/msm8974/platform.c` 新增 `leo_set_hifi_volume()` | `mixer_ctl_set_array("Volume", …)`；**加读回校验**（MIUI 原版没有） | ~30 | 中 |
| P7 | `hal/msm8974/platform.c` `platform_set_parameters()` | 新键 `leo_hifi_mode` / `leo_hifi_volume`；变更时遍历 `usecase_list` 调 `select_devices()` | ~40 | 中 |
| P8 | `hal/msm8974/platform.c` `platform_get_parameters()` | 新键 `leo_hifi_status`（返回结构化只读快照，见 §6.4） | ~40 | 低 |
| P9 | `hal/msm8974/platform.c` 新增 `leo_set_hifi_backend_cfg()` + 在 `platform_check_and_set_codec_backend_cfg()` 中挂钩 | 写 `QUAT_MI2S BitWidth` / `SampleRate` 并读回 | ~60 | **高**（M3.5 才启用，见 §5） |
| P10 | `hal/audio_hw.c` `enable_audio_route()` / `disable_audio_route()` | Leo HiFi Controller 状态机钩子：ARMING/ACTIVE/DEGRADED 判定与 generation 推进 | ~120 | 中 |
| P11 | `device/xiaomi/leo/*` | `vendor.leo.audio.*` 的 `property_contexts` + SELinux `type` 与 `allow` | ~15 | 中（M5 Enforcing 时才关键） |

**不改**：kernel、DTB、`mixer_paths.xml`、`mixer_paths_i2s.xml`、`audio_platform_info*.xml`、`audio_policy_configuration.xml`、`audioserver`、AudioFlinger、AudioPolicyManager、Dirac、ACDB 库。
这与 `docs/reviews/2026-08-28` §8 的裁决一致，并被本审计的符号级证据进一步收紧。

### 3.3 Leo HiFi Controller 的内部结构

```c
struct leo_hifi_state {
    uint64_t generation;          /* 单调递增，每次转换 +1              */
    int64_t  ts_ns;               /* CLOCK_BOOTTIME                      */
    enum leo_hifi_mode requested; /* 策略意图                            */
    enum leo_hifi_mode effective; /* 只在读回成功后写                    */
    uint32_t fail_code;           /* 见 §6.3                             */
    /* 读回快照 */
    int   snd_device;             /* platform 侧实际选中的设备           */
    int   quat_mm1;               /* QUAT_MI2S_RX Audio Mixer MultiMedia1 读回 */
    int   quat_rate_enum;         /* QUAT_MI2S SampleRate 读回           */
    int   quat_bw_enum;           /* QUAT_MI2S BitWidth 读回             */
    int   ess_vol[2];             /* "Volume" 读回                       */
    int   ess_bound;              /* /sys/bus/i2c/devices/6-0048/driver 存在 */
    int   active_streams;         /* PCM_PLAYBACK 且 out != NULL 的数量  */
};
```

单锁：复用 `adev->lock`；**不引入第二把锁**，避免与 `select_devices()` 的既有锁序冲突。
所有 `mixer_ctl_set_*` 之后立即 `mixer_ctl_get_*` 读回；读回不一致 → `HIFI_DEGRADED` + `fail_code`。

### 3.4 四种实现手段的失败模式（问题 B 第三问）

| 手段 | 失败模式 | 裁决 |
| --- | --- | --- |
| **源码补丁 MoKee HAL**（推荐） | 需要 Linux 构建主机与完整 `hardware/qcom/audio` 依赖；构建产物 ABI/命名空间必须与 MoKee 的 `android.hardware.audio@2.0-service` 完全一致 | **采用**。补丁面已收敛到 11 处、约 340 行 |
| **薄 shim**（`LD_PRELOAD`/包装 so 拦截 `platform_get_output_snd_device`） | 该函数是 `.so` **内部**调用（stock 里连 PLT 都没有生成，MoKee 里也是内部调用），无法从外部拦截；且 Android 10 linker namespace 禁止 vendor 进程加载任意 so | **否决**（结构性不可行，非风险偏好问题） |
| **配置改动**（只改 XML/property） | `mixer_paths.xml` 已含五条 hifi 路径，但**没有任何代码会请求它们**——`audio_route_apply_and_update_path()` 的路径名由 `device_table[snd_device]` 拼出，而 MoKee 的表里根本没有 `hifi-headphones` 条目 | **否决**（能力不在配置层） |
| **二进制替换**（把 MIUI 的 32-bit HAL 放进 MoKee） | Android 7 → 10 的 `audio_hw_device_t` 版本、`str_parms` ABI、linker namespace（`/vendor/lib` vs `/system/lib`）、`libacdbloader` 代际（`mokee-audio-delta` 已标 ABI-generation difference）、SELinux `hal_audio_default` 域全部不匹配 | **否决**（`docs/16` §9 已明令禁止，本审计的 ABI 证据支持该禁令） |
| **init.rc / 常驻 `tinymix` 脚本** | 无法感知流生命周期，与 `select_devices()` 竞态（M2 已实测到 `MultiMedia5` 抢路由），且违反 `docs/17` §7 单写入者原则 | **否决** |

### 3.5 哪些 MIUI 行为可重新实现，哪些必须放弃

| MIUI 行为 | 处置 |
| --- | --- |
| `hifi_mode` 布尔 + 设备选择 | **重新实现**（逻辑已完全反汇编，无专有算法） |
| `set_hifi_volume` 线性映射 `0.4v+213` | **重新实现**，但作为**可配置曲线**而非硬编码（见 §4.3） |
| `hifi_volume` 的 framework 调用者 | **自研**（MIUI 侧组件不在本地闭包中，也不可再分发） |
| `platform_set_hifi_backend_cfg` 的速率枚举映射 | **重新实现**（枚举字符串已由内核 `KHZ_*` 定义，非专有） |
| ES9018 上下电/时钟/THD 补偿时序 | **不重新实现**，继续由 MoKee 内核 `es9018.c` 负责（DTB 语义已由 M0/M1 证明一致） |
| Forte ACDB 二进制 | 继续使用设备本地已有副本（7 份逐字节相同），**不进 Git** |
| Dirac | 保持 MoKee 现状；A/B 之前不动（`docs/03` 已列为独立课题） |

---

## 4. HiFi 独立音量模型（问题 D 的直接回答）

### 4.1 应该调哪一级增益

| 候选增益级 | 裁决 | 理由 |
| --- | --- | --- |
| Android `STREAM_MUSIC` index | ❌ 不作为 HiFi 专用级 | 它是全局的，改它会污染外放/普通耳机；MIUI 也没有为 HiFi 单独建流 |
| AudioFlinger 软件衰减（`out_set_volume`） | ❌ | 16-bit 源上做软件衰减直接损失有效位数 |
| `QUAT_MI2S_RX Volume` | ❌ | M2 实测已在最大值 8192；这是 AFE 侧数字增益，向下调只会损失位深 |
| **ES9018 `Volume` kcontrol** | ✅ **主控级** | MIUI 原厂选择；发生在 DAC 内部数字域，ESS 的 32-bit 内部通路对 16-bit 源做衰减不引入可闻量化损失；且这是唯一"HiFi 专属"的增益点 |
| OPA1612 / 模拟级 | ❌ | 参考机硬件 3.2 上 `opa_gpio` 无效（`docs/04` §5），无可控模拟增益 |
| WCD9330 `RX*/HPH*` | ❌ 明令禁止 | HiFi 路径下该模拟出口被刻意切断；写它会制造假阳性（`docs/reviews/2026-08-29` §4 已指出） |

### 4.2 状态所有者与恢复规则

```text
真值来源：HAL 内 my_data->leo_hifi_volume（0..100）
持久化 ：HAL 在每次成功应用后写 vendor.leo.audio.hifi.volume
冷启动 ：platform_init 读 property → clamp → 应用 → 读回校验
路由切入：HIFI_ARMING 阶段，在 QUAT 路由生效之后、宣布 ACTIVE 之前，重新应用一次
路由退出：切回 headphones 时不改 "Volume"（它只影响 ESS 支路，且下次进入会重设）
失败    ：读回不一致 → 不进入 ACTIVE；保持上一次已确认值；上报 fail_code
```

**避免模式切换时的突发响度**（问题 D 第三问）：

1. `Volume` 的写入**必须发生在 QUAT 路由建立之前**（此时 ESS 尚未 unmute，`es9018.c` 的 soft-start 150 ms 之后才解除静音）。写入顺序固定为
   `设置 Volume → 应用 hifi-headphones mixer path → 等待 startup 日志/读回 → 宣布 ACTIVE`。
2. 首次启用 HiFi 且 `vendor.leo.audio.hifi.volume` 不存在时，**默认值取 0（→ 寄存器 213）**，即映射区间的最低端，而不是继承任何普通耳机刻度。
3. 设一个**硬上限** `vendor.leo.audio.hifi.volume.max`（构建期固定，默认 60，即寄存器 237），在完成 SPL 对照验收（§8 A7）之前不放开到 100。
4. 单次调整步长上限 5（避免 UI 拖拽产生 0→100 的跳变）；HAL 侧对 `|new-old| > 5` 的请求分帧应用，每帧 20 ms。

### 4.3 `Volume` 的语义仍未证明

**已证明**：控件名为 `Volume`，类型 INT，2 元素，MoKee 上现值 `205 205`，MIUI HAL 的写入区间为 `[213, 253]`。
**未证明**：该寄存器是衰减还是增益、是否 invert、每步 dB 数、上下限。ESS9018K2M 的音量寄存器（15/16）按数据手册是 0.5 dB/步的衰减，若 `es9018.c` 用 `SOC_DOUBLE_R_*_TLV(..., invert=1)` 注册，则 205 ≈ −25 dB、213 ≈ −21 dB、253 ≈ −1 dB。**这只是假设**（§10 分类 C）。

**最小证伪实验**（只读 + 一次可逆写，交由项目主代理执行）：

```text
前提：QUAT 路由已按 2026-08-29 的方式建立，固定曲目、固定音量刻度
1) tinymix 读回 "Volume" → 记录
2) 依次写 213 / 225 / 237 / 249，每次读回并记录主观响度与（若有）SPL
3) 恢复原值 205
判据：单调递增 → invert=1 假设成立；单调递减 → 语义为直接衰减，映射曲线需整体重算
风险：若步进过大可能产生突发响度，故必须从 213（最低端）开始向上试
```

### 4.4 `persist.audio.hifi.volume` 的处置

| 选项 | 裁决 |
| --- | --- |
| 直接复用 | ❌ 该 property 在 MoKee 上无 `property_contexts` 条目；且它承载 MIUI 语义（HAL 写入的是**未 clamp 的原始字符串**，`platform_init` 才 clamp），语义不干净 |
| 迁移 | ⚠️ 仅在维护页提供一次性导入：若检测到旧值则读入并按同一曲线换算，之后只写新 property |
| **替代（推荐）** | ✅ 新建 `vendor.leo.audio.hifi.volume`（0–100，`u:object_r:vendor_leo_audio_prop:s0`），`persist.` 前缀改由 `vendor.` + 显式持久化语义承担；`persist.audio.hifi` 同理替换为 `vendor.leo.audio.hifi.enable` |

`manifests/audio-property-contract-v0.1.tsv` 与本轮证据存在**一处直接冲突**：manifest 记 `persist.audio.hifi.volume = 40`，而 `docs/reviews/2026-08-28` §4 与 `2026-08-29` §5 引用的 MIUI logcat 记 `30`。两者不可能同时描述同一时刻。列为争议项 D-1（§10.4）。

### 4.5 向 UI 暴露什么

```text
普通 Leo Home：  「HiFi · ESS9018 · 已激活」 + 一个 0–100 的抽象刻度（受上限约束）
隐藏维护页：      requested / effective / generation / fail_code /
                 snd_device 名 / QUAT MM1 读回 / QUAT rate,bw 读回 /
                 "Volume" 读回原始值 / ESS I2C 绑定 / 活动流数 / 最近 denial
永不暴露：        任意 mixer 控件写入面、I2C 直写、property 写入、原始寄存器可编辑框
```

---

## 5. 44.1 / 48 kHz 决策表（问题 C 的直接回答）

### 5.1 前提：三层都必须同时是 44.1

```text
① AudioTrack (App)         44.1  ← Apple Music / Spotify 已经是
② HAL 输出流 / 前端 PCM     48.0  ← ★ 当前的 SRC 发生点（AudioFlinger MixerThread）
③ QUAT_MI2S 后端           48.0  ← 由 QUAT_MI2S SampleRate kcontrol 决定
④ ES9018 晶振              49.152 MHz ← 由 ③ 推导（es9018.c 按 sample_rate 选晶振）
```

**只改 ③ 是有害的**：若前端保持 48 kHz 而后端设为 44.1 kHz，SRC 只是从 AudioFlinger 移到 ADSP/AFE，且引入项目从未验证过的 backend fixup 路径与 `docs/04` §7.4 记录的 LPASS slave 固定 3.072 MHz IBIT 参数风险。**任何"把 QUAT SampleRate 设成 KHZ_44P1 就完事"的做法应被明确禁止。**

### 5.2 决策表

| 场景 | 流数 | 内容率 | 输出路径 | ③ 后端目标 | 是否可宣称直通 | 处置 |
| --- | ---: | --- | --- | --- | --- | --- |
| S1 Leo 自有播放器，单流，有线 HiFi，本地/缓存 44.1 PCM | 1 | 44.1 | **DIRECT (direct_pcm)** | KHZ_44P1 / S24_LE | ✅ 端到端 44.1，可宣称"无 SRC" | **M3.5 实验目标** |
| S2 第三方 App（Apple Music/Spotify），单流，44.1 | 1 | 44.1 | deep-buffer | KHZ_48 | ❌ | 保持 48，界面显示"48 kHz（重采样）" |
| S3 第三方 App，48 kHz 内容 | 1 | 48 | deep-buffer | KHZ_48 | ✅ 无 SRC（但非 44.1 家族） | 保持 |
| S4 音乐 + 系统提示音 | ≥2 | 混合 | deep-buffer 混音 | KHZ_48 | ❌ | **强制 48**；不得为单条流切时钟家族 |
| S5 88.2 / 176.4 kHz 内容 | 1 | 88.2/176.4 | DIRECT | KHZ_88P2 / KHZ_176P4 | 未验证 | M4 之后再评估；第一版不支持 |
| S6 通话 / VoIP | — | — | — | KHZ_48 强制 | — | 与 MIUI 一致（`voice_is_in_call()` / `mode==IN_COMMUNICATION` 守卫） |
| S7 息屏后台播放 | 1 | 同 S1/S2 | 不变 | 不变 | 同上 | 息屏**不得**触发速率重协商 |
| S8 切歌（同一 App，同采样率） | 1 | 同 | 不变 | **不变** | 同上 | 见 §5.4 迟滞 |
| S9 切歌（跨采样率 44.1→48） | 1 | 变 | DIRECT 需重开流 | 重协商 | — | 见 §5.4 |

**默认时钟家族**：48 kHz。理由——S2/S3/S4 覆盖绝大多数实际使用，且 48 kHz 是内核 `msm8994.c:245-247` 的默认值，切换次数越少风险越低。

### 5.3 要让 S1 成立需要什么

1. **Leo 自有播放器**用 `AudioTrack` + `AudioAttributes` 请求 `AUDIO_OUTPUT_FLAG_DIRECT`（Android 10 上通过 `AudioTrack.Builder#setPerformanceMode` 无法直接指定 DIRECT，需要 `AudioFormat` 精确匹配 + `AudioAttributes` 的 `FLAG_HW_AV_SYNC` 之外的路径；**这条本身需要验证**，列为未知 U-3）。
2. HAL 侧：在 `platform_check_and_set_codec_backend_cfg()` 的 HiFi 分支保留 `usecase->id == USECASE_AUDIO_PLAYBACK_OFFLOAD` 守卫（与 MIUI 一致），追加"当前 `snd_device == LEO_HIFI_HEADPHONES`"这一条件。
3. 内核：`KHZ_44P1` 枚举已存在（kernel 字符串已证），`es9018.c` 按 `sample_rate` 选 45.1584 MHz 晶振（`docs/04` §2）。
4. **必须验证**：`docs/04` §7.4 的开放项——LPASS slave 分支写死 3.072 MHz IBIT 参数在 44.1 kHz 下是否只是接口占位值。ES9018 是 I²S master（`CBM_CFM`），BCLK 由 codec 提供，因此 LPASS 的 IBIT 设置**很可能**只是名义值；但这是推断，不是事实。

### 5.4 动态切换的危害与迟滞策略（问题 C 第三问）

| 危害 | 触发条件 | 缓解 |
| --- | --- | --- |
| 爆音 / pop | 在 ESS 未静音时改 `QUAT_MI2S SampleRate` | 速率变更**只允许在 QUAT 后端关闭（引用计数为 0）时**发生；即必须 teardown → 改控件 → 重新 startup |
| 变速 / 音调错误 | 前端与后端速率不一致 | 单一真值：速率由 `out->sample_rate` 推导，写后立即读回比对 |
| 锁相延迟 | 晶振切换 + ESS soft start 150 ms | 用户可感的"切歌卡顿"；因此 **S8 同速率切歌绝不重协商** |
| stream teardown | DIRECT 输出关闭/重开 | 每次跨速率切歌都会 teardown；设 **≥2 s 迟滞**：速率变更请求在 2 s 内被同速率请求覆盖则取消 |
| HAL 重启 | 写控件失败后错误处理不当 | 所有 mixer 写入失败一律走 `ERROR_FALLBACK`，绝不重试到超时 |

### 5.5 什么时候只能承认 SRC（问题 C 第四问）

以下任一成立即**必须**显示"重采样"而非"直通"，且不得使用 bit-perfect 字样：

* 活动播放流数 > 1；
* 输出路径不是 DIRECT；
* `QUAT_MI2S SampleRate` 读回值与 `out->sample_rate` 不对应；
* 存在任何活动 effect（Dirac 未旁路）；
* 系统音量不在最大刻度（Android 侧数字衰减已改变样本值）；
* 位深转换发生（16-bit 源进 S24_LE 容器**不算** SRC，但也不构成"提升"，界面不得显示 24-bit 为音质指标）。

---

## 6. 状态机与故障回退表（问题 E 的直接回答）

### 6.1 状态集（对 `docs/17` §3 的修订见 §9）

| 状态 | 语义 | 进入条件 |
| --- | --- | --- |
| `IDLE` | 无活动输出流 | 活动 PCM_PLAYBACK usecase 数 = 0 |
| `SPEAKER` | 外放 | `snd_device ∈ {speaker*}` |
| `WIRED_STANDARD` | 有线耳机走 WCD9330 | `snd_device == headphones(7)` |
| `HIFI_ARMING` | 正在建立 HiFi | `requested=HIFI` 且路由切换已发起，读回未闭合 |
| `HIFI_ACTIVE` | 全部证据同 generation 闭合 | 见 §6.2 |
| `HIFI_DEGRADED` | 有声但证据不全 | 任一非致命读回失败 |
| `ERROR_FALLBACK` | 已回退到 `headphones` | 致命失败（见 §6.3） |

### 6.2 `HIFI_ACTIVE` 的证据门（修订版）

必须**在同一个 generation 内**全部成立：

| # | 证据 | 采集方式 | 失败等级 |
| ---: | --- | --- | --- |
| E1 | AudioPolicy 输出设备 ∈ {WIRED_HEADSET, WIRED_HEADPHONE} | `usecase->devices` | 致命 |
| E2 | `platform_get_output_snd_device()` 返回 `LEO_HIFI_HEADPHONES` | HAL 内部 | 致命 |
| E3 | ES9018 已绑定：`/sys/bus/i2c/devices/6-0048/driver` 指向 `es9018` | HAL 启动时读一次并缓存 | 致命 |
| E4 | `QUAT_MI2S_RX Audio Mixer MultiMedia1` 读回 = 1 | `mixer_ctl_get_value` | 致命 |
| E5 | `SLIM RX1 MUX` / `SLIM RX2 MUX` 读回 ≠ `AIF1_PB`（WCD 模拟出口未同时打开） | 读回 | **致命**（防 M2 §7.2 的 MultiMedia5 假阳性） |
| E6 | `QUAT_MI2S BitWidth` / `SampleRate` 读回与 Controller 期望一致 | 读回 | 非致命 → DEGRADED |
| E7 | `Volume` 读回 = 期望值 | 读回 | 非致命 → DEGRADED |
| E8 | 活动 PCM_PLAYBACK 流数 ≥ 1 且 `pcm_state` 为 RUNNING | HAL 内部 | 致命 |
| E9 | 本 generation 内无 mixer 写失败、无 `dlopen`/linker 错误 | HAL 内部计数 | 致命 |
| ~~E10~~ | ~~ACDB load 成功~~ | — | **删除**：见 C5，`hifi-headphones` 无 ACDB ID 是原厂常态 |
| E10' | ACDB 查询返回"无该设备条目"且**未产生错误** | HAL 记录 | 非致命，记入维护页 |

阻抗值（`HPHL/HPHR Impedance`）**不作为证据门**：M2 §7.1 已证明它在 QUAT 后端启动前无效，属于结果而非前提。它可作为维护页展示项。

### 6.3 失败码

| code | 含义 | 目标状态 |
| ---: | --- | --- |
| 0 | 无 | — |
| 1 | `mixer_get_ctl_by_name` 失败（控件不存在） | ERROR_FALLBACK |
| 2 | mixer 写入返回错误 | ERROR_FALLBACK |
| 3 | 写入成功但读回不一致（致命项） | ERROR_FALLBACK |
| 4 | 写入成功但读回不一致（非致命项 E6/E7） | HIFI_DEGRADED |
| 5 | ES9018 未绑定 / sysfs 缺失 | ERROR_FALLBACK（且永久禁用本次 boot 的 HiFi） |
| 6 | 检测到并发 SLIMBUS 模拟出口（E5 失败） | ERROR_FALLBACK |
| 7 | 后端速率协商失败 | HIFI_DEGRADED（保持 48 kHz 继续出声） |
| 8 | 超时（见 §6.4） | ERROR_FALLBACK |

### 6.4 路径表：前置条件 / 写入顺序 / 读回 / 超时 / 回滚 / 终态

| 路径 | 前置 | 写入顺序 | 读回证据 | 超时 | 回滚 | 终态 |
| --- | --- | --- | --- | ---: | --- | --- |
| **首次播放（HiFi 已启用）** | 耳机已插；`requested=HIFI`；E3 成立 | ① `Volume`（先设增益，ESS 仍静音）→ ② `select_devices()` 触发 `enable_audio_route("deep-buffer-playback hifi-headphones")` → ③ 若 §5 允许则设后端 cfg | E4,E5,E7,E8 → 再 E6 | 300 ms（含 ESS soft start 150 ms 的裕量） | 调 `disable_audio_route` + 重新 `select_devices` 到 `headphones` | ACTIVE / DEGRADED / ERROR_FALLBACK |
| **暂停 3 秒** | AudioFlinger standby delay = 3 s（`docs/03` 已实测） | 不主动写任何控件 | 观察 usecase 数归零 | — | — | `IDLE`（ESS 由内核有序下电） |
| **快速切歌（同速率）** | 同一 usecase 未 teardown | **不做任何写入** | E4/E8 保持 | — | — | ACTIVE 保持，generation **不变** |
| **快速切歌（跨速率）** | S9 | 迟滞 2 s；到期后 teardown → 改后端 → 重建 | 全套 | 600 ms | 退回 48 kHz 并置 code 7 | ACTIVE(48) / DEGRADED |
| **拔耳机** | `WiredAccessoryManager` 事件 | 立即 `select_devices()` → speaker/idle；**不写 `Volume`** | `snd_device` 变化 | 200 ms | — | `SPEAKER` / `IDLE` |
| **插耳机（未播放）** | — | **不做任何硬件动作**（`docs/04` §6：插入不启动 DAC） | — | — | — | `WIRED_STANDARD`（显示"耳机 · 标准"，因为 HiFi 尚未成立） |
| **息屏** | — | 无动作 | 周期性（30 s）轻量读回 E4 | — | 若 E4 变 0 → 重新评估 | 状态不变或降级 |
| **多个播放器** | 活动流 ≥ 2 | 不切换时钟家族（S4） | E8 计数 | — | — | ACTIVE，但速率标注为"混音 48 kHz" |
| **HAL 崩溃** | `android.hardware.audio@2.0-service` 重启 | 冷路径：`platform_init` 重新读 property 并重建 | 全套，generation 从 0 重新开始 | 启动内 2 s | 若 E3 失败 → 本次 boot 禁用 HiFi | 由 `platform_init` 决定 |
| **AudioFlinger / audioserver 重启** | HIDL 客户端重连 | 同上 | 全套 | 2 s | — | 同上 |
| **ESS probe 缺失** | `/sys/bus/i2c/devices/6-0048/driver` 不存在 | **不发起任何 HiFi 尝试** | E3 | — | — | `WIRED_STANDARD`，code 5，维护页显示"ESS 未探测到" |
| **QUAT 写入失败** | `mixer_ctl_set_value` != 0 | 立即停止后续写入 | — | — | 逆序撤销已写控件 → `headphones` | `ERROR_FALLBACK`，code 2 |
| **ACDB 失败** | loader 报错（非"无条目"） | 不阻塞路由 | E10' | — | — | `HIFI_DEGRADED` |
| **速率切换失败** | 后端读回 ≠ 期望 | 回写 `KHZ_48` 并读回 | E6 | 300 ms | 回到 48 kHz | `HIFI_DEGRADED`，code 7 |
| **重启后恢复** | 冷启动 | `platform_init`：读 property → clamp → 应用 `Volume` → **不主动建立路由** | E3 + `Volume` 读回 | — | — | `IDLE`；首次播放时才 ARMING |
| **MultiMedia5 竞态**（M2 §7.2） | 主路由被切断时 AudioFlinger 另开 SLIMBUS_0_RX ← MultiMedia5 | 每次读回都检查 E5 | E5 | — | 检测到即降级，**绝不静默维持 ACTIVE** | `HIFI_DEGRADED` 或 `ERROR_FALLBACK` code 6 |

**不允许的转换**（继承 `docs/17` §4 第 6 条并加强）：
`ERROR_FALLBACK → HIFI_ACTIVE` 必须经过完整 `HIFI_ARMING`；
`HIFI_DEGRADED → HIFI_ACTIVE` 同样必须新起一个 generation，不得靠"下一次读回碰巧对了"就升级。

---

## 7. 分阶段实现顺序

| 阶段 | 内容 | 完成判据 | 不做 |
| --- | --- | --- | --- |
| **M3-0（离线）** | 建 Linux 构建主机；同步 `mkq-mr1-caf-msm8994` 的 `hardware/qcom/audio` + `device/xiaomi/leo`；**无修改**构建出 32-bit `audio.primary.msm8994.so`，与设备上的 `701019bd…` 做符号表/节区结构对照 | 双次构建产物自身一致；符号集合与 `701019bd…` 差异可逐项解释 | 不刷机 |
| **M3-A** | P1–P4 + P10 的**只读部分**：只加 snd_device、只加状态机与 `dumpsys`/`get_parameters` 观测，`platform_get_output_snd_device` 仍返回 `headphones` | 设备行为与原版 MoKee 逐项一致；结构化状态可读出 | 不改路由 |
| **M3-B** | 打开 P4：`leo_hifi_mode=true` 时选 `LEO_HIFI_HEADPHONES` | 单流播放可进入 `HIFI_ACTIVE`；A/B/A 因果复现（E5 必须通过）；拔插、暂停、息屏、HAL 重启五项通过 | 不动音量、不动速率 |
| **M3-C** | P5–P7：独立音量（先只允许 0–60 上限） | §4.3 证伪实验完成；SPL 对照通过；无削波、无爆音 | 不动速率 |
| **M3-D** | P8 + Status Service（只读 binder，signature 权限） | 维护页可读全部 §6.2 证据；普通 UI 只显示摘要 | UI 无写能力 |
| **M3.5** | P9：仅 S1 场景的 44.1 DIRECT 直通实验 | 端到端读回 44.1；迟滞、teardown、回退全部通过；**允许结论为"不可行，维持 48"** | 不为 S2 做任何 hack |
| **M4** | 白名单最小化（`docs/16` §10 不变） | — | — |
| **M5** | `user` + Enforcing + P11 | — | — |

**关键顺序约束**：M3-B 与 M3-C 不得合并——音量变化会掩盖路由问题，路由变化会掩盖音量问题；这正是 M2 中"听感有声"被内核日志证伪的同类陷阱。

---

## 8. 真机验收矩阵

每项都必须同时记录：可见状态、`leo_hifi_status` 快照、AudioPolicy 输出、`tinymix` 读回（至少 E4/E5/E6/E7 涉及的控件）、`dmesg` 中 `msm8994_quat_mi2s_snd_startup/shutdown`、温度、恢复结果。

| ID | 场景 | 通过判据 | 阻断条件 |
| --- | --- | --- | --- |
| A1 | 冷启动 → 插耳机 → 不播放 | `WIRED_STANDARD`；QUAT 全 Off；ESS 未上电 | 显示 HiFi |
| A2 | 开始播放（HiFi 启用） | `HIFI_ACTIVE`；E1–E9 全通过；`bit width=6` 出现在 dmesg | E5 未通过却显示 ACTIVE |
| A3 | A/B/A 因果 | 关闭 QUAT → 无声；恢复 → 有声；全程 `HPHL DAC Switch=Off` | 出现 MultiMedia5 旁路而状态未降级 |
| A4 | 暂停 3 s / 5 s | 3 s 后 usecase 归零，QUAT 时钟关闭；状态 `IDLE` | DAC 保持上电 |
| A5 | 同速率快速切歌 ×20 | generation 不变；无爆音；无 teardown | 每次切歌都重协商 |
| A6 | 跨速率切歌（44.1↔48，仅 M3.5） | 迟滞生效；读回一致；无变速 | 出现变速或爆音 |
| A7 | **SPL 对照** | 固定曲目、固定耳机、固定 Android 刻度下，MoKee HiFi 与 MIUI HiFi 的 SPL 差 ≤ 2 dB | 差值 > 3 dB 或出现削波 |
| A8 | 音量扫描 0→上限 | 单调、无爆音、每步读回一致 | 任一步读回不一致 |
| A9 | 拔耳机（播放中） | 有序下电；无爆音；`SPEAKER`/`IDLE` | 拔出后 ESS 仍上电 |
| A10 | 息屏连续播放 2 h | 状态稳定；温度不高于 MIUI 参照 +2 ℃；无欠载 | 状态漂移或降级未上报 |
| A11 | `killall audio@2.0-service` | 自动重启；property 恢复；重新 ARMING | 重启后直接宣称 ACTIVE |
| A12 | `killall audioserver` | 同上 | 同上 |
| A13 | 模拟 ESS 未绑定（构造 sysfs 读失败） | code 5；`WIRED_STANDARD`；不尝试 QUAT | 仍尝试并出声 |
| A14 | 模拟 mixer 写失败（构造控件名错误） | code 1/2；逆序撤销；`ERROR_FALLBACK` | 残留半配置状态 |
| A15 | 重启后恢复 | 音量恢复；不自动建路由；首播时才 ARMING | 冷启动即宣称 ACTIVE |
| A16 | 多流（音乐 + 提示音） | 保持 48 kHz；界面标注"混音" | 为单流切时钟家族 |
| A17 | 外放 | HiFi 完全关闭；`Volume` 不被写 | HiFi 路径残留 |
| A18 | 与 MIUI 黄金参照主观对照 | 无可确认退化（`docs/VISION` 成功标准 2） | — |

---

## 9. 对 `docs/17-LEO-AUDIO-STATE-CONTRACT.md` 的逐条修订建议

| 位置 | 现文 | 建议 | 依据 |
| --- | --- | --- | --- |
| §2 架构边界图 | `Leo HiFi Controller（audio HAL）→ 供电/时钟/QUAT MI2S/ESS9018/ACDB 的有序控制` | 改为：HAL 只控制 **mixer 路由 + QUAT 后端 cfg + ESS `Volume`**；**供电、时钟、mute、OPA、模拟 switch 由内核 `es9018.c` 在 QUAT DAI startup/shutdown 中自动完成，HAL 只观察** | `docs/04` §5；M2 §5（`hifi-headphones` mixer path 为空） |
| §2 末段 | "控制器在 M3 首先作为 …最小源码补丁/重写目标" | 补充明确目标：`hardware/qcom/audio/hal/msm8974/platform.c` 与 `hal/audio_hw.c`，**32-bit 产物**；并列出 §3.2 的 11 处补丁点 | 本文 §2.1、§3.2 |
| §3 状态表 | 7 状态 | 保留。补充：`requested_mode` 与 `effective_mode` 之外，增加 `generation`、`fail_code`、`evidence_bitmap`（E1–E9 各一位），使"部分证据缺失"可精确表达 | 本文 §6.2 |
| §4 转换 3 | "ESS、QUAT、mixer、ACDB 与流参数全部核验" | 删除 ACDB 作为**必要**条件；改为"ACDB 查询无错误（`hifi-headphones` 无 ACDB 条目属预期）" | 本文 C5 |
| §4 末段 | "第一版不承诺按照耳机阻抗自动切换" | **保留并加强**：MIUI 原厂的 HiFi 判据里根本不含阻抗（§2.2 反汇编证据）；同时补充"阻抗在 QUAT 后端启动前无效，不可作为策略输入" | 本文 §2.2；M2 §7.1 |
| §5 证据门 | 7 条 | 按本文 §6.2 替换为 E1–E9 + E10'；**新增 E5（SLIM MUX 必须已断开）**——这是 M2 实测过的假阳性来源，现文完全没有覆盖 | M2 §6.2、§7.2 |
| §5 末段 | "M2 必须先采集原版 MoKee 实测基线，才能确定上述各项的确切节点、控制名称和阈值" | 已闭合，改为直接列出确切控件名：`QUAT_MI2S_RX Audio Mixer MultiMedia1`、`SLIM RX1/RX2 MUX`、`HPHL DAC Switch`、`QUAT_MI2S BitWidth`、`QUAT_MI2S SampleRate`、`Volume`、`/sys/bus/i2c/devices/6-0048/driver` | M2 §2/§5/§6；本文 §2.3 |
| §6 普通 Leo Home | "采样率/位宽只有在 HAL 已实际确认时才显示" | 加一条：**当输出经过 SRC 时必须显式标注"重采样"**，且禁止把 24-bit 容器显示为音质指标 | 本文 §5.5 |
| §6 维护页 | 现列表 | 增加：`Volume` 读回值、`SLIM RX MUX` 读回、活动流数、evidence bitmap、迟滞计时器状态 | 本文 §6.2 |
| §7 安全 | "使用新的 `vendor.leo.audio.*` 只读发布状态可作为早期调试辅助，但不是长期可信控制面" | 修订：`vendor.leo.audio.hifi.enable` / `.volume` **就是**长期控制面（HAL 是唯一写入者，Service 是唯一请求者）；只读状态另用 `get_parameters("leo_hifi_status")` | 本文 §1.1、§4.4 |
| §7 新增 | — | 增加一条：**禁止复用 `persist.audio.hifi` / `persist.audio.hifi.volume`**，理由是 MIUI 语义未完全证明且 property 类型上下文缺失 | 本文 §4.4 |
| §8 阶段表 | M3-A/B/C + M4/M5 | 按本文 §7 细化为 M3-0/A/B/C/D + M3.5，明确 M3-B 与 M3-C 不得合并 | 本文 §7 |
| §9 验收矩阵 | 现列表 | 用本文 §8 的 A1–A18 替换，特别是补 A3（A/B/A）、A7（SPL）、A13/A14（故障注入）、A16（多流） | 本文 §8 |
| **新增 §10** | — | **采样率契约**：明确"第一版默认 48 kHz 时钟家族"、"只在 S1 场景尝试 44.1"、"任何情况下不宣称 bit-perfect，除非 §5.5 全部条件成立" | 本文 §5 |

---

## 10. 证据分类表

### 10.1 事实（本轮可复现）

| ID | 事实 | 复现方式 |
| --- | --- | --- |
| F1 | stock 32-bit HAL `0b8e3f62…` 导出 `platform_{get,set}_hifi_property`、`platform_get_hifi`、`platform_{set,check}_hifi_backend_cfg` | `objdump -T … \| grep -i hifi` |
| F2 | stock 64-bit HAL `4b3fb296…` 导出同名 5 符号 | 同上 |
| F3 | MoKee 32/64-bit HAL（`701019bd…` / `6939be82…`）导出 0 个同类符号，且整个 MoKee `selected/` 树中只有 `mixer_paths.xml` 含 "hifi" | `grep -rail hifi resources/private/phase5b-mokee/selected/` |
| F4 | `platform_get_output_snd_device` @0x142bc+0x348：`my_data->hifi ? 34 : 6` | `objdump -d --start-address=0x145c0 --stop-address=0x14650` |
| F5 | `my_data->hifi` 位于 platform 结构 +0x74，由 `persist.audio.hifi` 与 `set_parameters("hifi_mode")` 写入 | 0x12d0c、0x13008、0x15b78+0x4c4 反汇编 |
| F6 | `set_hifi_volume` @0x12de8 向 kcontrol `"Volume"` 写 2 元素数组，值 = `v*40/100 + 213` | 0x12de8–0x12ec4 反汇编 + 字符串 @0x2c28e |
| F7 | `set_hifi_volume` 的调用者只有 `platform_init`(@0x116f0) 与 `platform_set_parameters`(@0x162d8) | BL 目标扫描 |
| F8 | `platform_set_parameters` 处理键 `hifi_mode` / `hifi_volume`，并分别 `property_set` 到 `persist.audio.hifi` / `persist.audio.hifi.volume` | 0x1603c–0x16110、0x1628c–0x162e8 |
| F9 | `platform_get_parameters` 亦支持 `hifi_mode` / `hifi_volume` 读回 | 0x16cb4+0x138 / +0x1b0 |
| F10 | `platform_set_hifi_backend_cfg` 写 `QUAT_MI2S BitWidth`（`S16_LE`/`S24_LE`）与 `QUAT_MI2S SampleRate`（`KHZ_44P1/48/64/88P2/96/176P4/192`，default `KHZ_48`） | 0x176a0–0x17948 |
| F11 | 该函数唯一调用点在 `platform_check_and_set_codec_backend_cfg` @0x17ec4+0x18c，且被 `usecase->id == 3` 守卫 | 0x1807c–0x1809c |
| F12 | `use_case_table[3] == "compress-offload-playback"`，stock 与 MoKee 顺序一致 | stock 文件偏移 0x31528（vaddr 0x32528）/ MoKee 0x29010 |
| F13 | `enable_audio_route` 中 HiFi 相关分支条件为 `usecase->type==PCM_PLAYBACK && usecase->id==3 && snd_device==34 && hifi` | 0x68f4–0x6938 |
| F14 | snd_device 编号代际差异：MIUI 6/34，MoKee 7/(无) | `device_table`：stock 文件偏移 0x31628（vaddr 0x32628）/ MoKee 0x251e0 |
| F15 | MoKee `platform_get_output_snd_device` @0x17d04+0x21c：有线耳机 → 7 | 0x17f20–0x17f28 |
| F16 | MoKee/stock 的 `audio_platform_info*.xml` 均无 `hifi-headphones` 的 `acdb_id` | 直接读文件 |
| F17 | MoKee `audio_policy_configuration.xml` 的 `primary output` / `deep_buffer` 声明 `44100,48000`；`direct_pcm` 声明全速率 | 直接读文件 |
| F18 | MIUI `audio_policy.conf` 同样声明 44100，且 `direct_pcm` 带 `AUDIO_OUTPUT_FLAG_DIRECT_PCM` | 直接读文件 |
| F19 | MoKee 内核映像含 `es9018.c` 全套符号、`ess,es9018`、`HiFi Headphone`、kcontrol `Volume`、`KHZ_44P1` 枚举 | `strings kernel-image.bin` |
| F20 | M2 实机：控件 907 `Volume` INT 2 值 = `205 205`；1015 `QUAT_MI2S BitWidth = S24_LE`；1016 `QUAT_MI2S SampleRate = KHZ_48`；823 `QUAT_MI2S_RX Volume = 8192` | `m2-runtime-20260828/tinymix-B-state.txt`、`05-hal-state.txt` |
| F21 | M2 实机：实际承载 HAL 的进程是 32-bit `android.hardware.audio@2.0-service` (pid 442) | `05-hal-state.txt` |

**文件哈希（SHA-256）**

```text
0b8e3f6290532499ac19c881fc8cbe36c8212f3dd83fe4aa3527ff6265fe038a  stock-system-tree/lib/hw/audio.primary.msm8994.so
4b3fb296226c77219dc44695512f7743d708315cec5c756a88ee6e9077385de1  stock-system-tree/lib64/hw/audio.primary.msm8994.so
cfedbe8d84022e883baadfd517cbbaa1f6f51c18c45dd9feb6e66a28e4fd3b66  stock-system-tree/etc/audio_policy.conf
701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47  phase5b-mokee/selected/system/vendor/lib/hw/audio.primary.msm8994.so
6939be82ada44c5772dcfe6977443eccdc03ee2bc85199e412112ebeefe47ee0  phase5b-mokee/selected/system/vendor/lib64/hw/audio.primary.msm8994.so
b299109dceeb1ffce8b022e2213dc0cced1472e2cbc5e6486d4c36687d3d6d03  phase5b-mokee/selected/system/vendor/etc/audio_policy_configuration.xml
13db0e6e5bd04e02c36a6b84e815f492d730e107866b91e605ee653364084bb4  phase5b-mokee/selected/system/vendor/etc/mixer_paths.xml
06ba207478720a4c02f7a66066da67a167d3102698672056910f4a4e6571148d  phase5b-mokee/selected/system/vendor/etc/audio_platform_info_i2s.xml
8fa544779068490bcc81bd264380d508fe831b06e2023ad9381be79dedffe523  phase5b-mokee/selected/system/vendor/etc/audio_platform_info.xml
fbbd8d466e920ef4d96aba5756a194fb578e8c385c22f4839bbb5a51519b3089  phase5b-mokee/boot-audit-v0.1/kernel-image.bin
```

工具：`/usr/bin/objdump`（LLVM，macOS 26）、`strings`、`shasum -a 256`、自写 ELF 段/字符串解析脚本。
反汇编中的 PC 相对字符串一律按 ARM 语义 `target = addr(add) + 8 + literal` 解析。

### 10.2 高可信推断

| ID | 推断 | 依据 | 证伪方式 |
| --- | --- | --- | --- |
| H1 | kcontrol `"Volume"` 由 `es9018.c` 注册（而非 Tomtom） | 1017 个控件中它是唯一无前缀的 `Volume`；Tomtom 控件全部带前缀；内核含 `es9018.c` 且 `Volume` 字符串独立存在 | 在设备上 `cat /proc/asound/card0/...` 或对比 `es9018` 驱动 unbind 前后的控件数 |
| H2 | MoKee 上"同刻度更轻"的主因是 `Volume` 停在 205（低于 MIUI 区间 [213,253]） | F6 + F20 | §4.3 的四点扫描实验 |
| H3 | 本代 CAF HAL 中 `direct_pcm` 复用 `USECASE_AUDIO_PLAYBACK_OFFLOAD` | `audio_policy.conf` 的 `direct_pcm` 带 `DIRECT_PCM` flag，而 HAL 只有 offload 一族 compress usecase；F11 的守卫也只认 id 3 | 读 `hardware/qcom/audio` 源码 `out_open`/`get_usecase_from_...` |
| H4 | ES9018 是 I²S master，故 LPASS slave 分支写死的 3.072 MHz IBIT 参数在 44.1 kHz 下只是名义值 | `docs/04` §2 的 `CBM_CFM` 证据 | M3.5 实测 44.1 直通 |
| H5 | MIUI 侧存在一个 framework/App 组件调用 `setParameters("hifi_volume=N")` | F8（HAL 侧解析器存在，且 `persist.` 值会被更新） | 在 MIUI 参照系统中 `grep -r hifi_volume /system/framework /system/priv-app` |
| H6 | `platform_check_hifi_backend_cfg`（导出但无内部调用者）是被内联进 `platform_check_and_set_codec_backend_cfg` 的同源代码 | 两者逻辑逐条同构；前者无 PLT 项 | 读源码 |

### 10.3 假设（未验证，影响设计）

| ID | 假设 | 若为假的后果 |
| --- | --- | --- |
| S1 | ES9018 `Volume` 寄存器语义为 invert 衰减，步长 0.5 dB，205→约 −25 dB | §4 的映射曲线与上限值全部需要重算；A7 判据不变 |
| S2 | MoKee 的 `hardware/qcom/audio` 可在 `mkq-mr1-caf-msm8994` 上独立构建出与设备一致的 32-bit HAL | M3-0 直接失败，需回退到"整树构建"，成本大幅上升 |
| S3 | Android 10 的 AudioPolicyManager 会为显式请求 DIRECT 的 44.1 track 打开 `direct_pcm` 输出 | S1 场景不可达，44.1 目标整体作废，只能承认 SRC |
| S4 | `vendor.leo.audio.*` 可在当前 Permissive 下工作、并在 M5 Enforcing 时通过新增 `property_contexts` 解决 | M5 前需要额外 SELinux 工作量 |

### 10.4 未知与争议

| ID | 未知/争议 | 处置 |
| --- | --- | --- |
| U1 | ES9018 `Volume` 控件的 min/max/TLV | 需设备上 `tinymix` 详细模式或内核源码 |
| U2 | MIUI 中 `hifi_volume` 的实际调用者与调用时机 | 需 MIUI 参照系统只读采集（见 §12） |
| U3 | Android 10 上如何让一个普通播放器可靠拿到 DIRECT 44.1 输出 | M3.5 前的独立调研 |
| U4 | 44.1 kHz 下 QUAT backend + LPASS slave 的实际行为 | 只能实机验证 |
| U5 | `hifi-headphones` 无 ACDB ID 时，HAL 究竟走了哪条 fallback | 需读 `platform_send_audio_calibration` 源码 |
| **D-1** | **争议**：`manifests/audio-property-contract-v0.1.tsv` 记 `persist.audio.hifi.volume = 40`，而 `docs/reviews/2026-08-28` §4 与 `2026-08-29` §5 引用的 MIUI logcat 记 `30` | 需重新核对采集时间戳；在澄清前，**两个值都不得写进任何默认配置** |
| **D-2** | **争议**：`docs/ROADMAP.md` Phase 5B 第 3 条把"消除 44.1→48 非必要 SRC"与 HiFi 路由并列为同一里程碑目标 | 本审计建议拆分（§7）；理由是 C3 证明二者根因不同 |
| **D-3** | **争议**：`docs/17` §5 把 "Forte ACDB/loader 没有失败" 列为 `HIFI_ACTIVE` 证据门 | 本审计认为该条对 HiFi 设备结构性不可满足，建议改写（§9） |

---

## 11. 项目主方案最可能犯错的三个地方

### 风险 1：把 MIUI 的 `34` 直接搬进 MoKee

`docs/reviews/2026-08-28` §4 明确记录了 `SND_DEVICE_OUT_HIFI_HEADPHONES = 34`，§8 又把它写成"剩余缺口"的一部分。但 F14 证明 MoKee 的 34 是 `speaker-protected`。任何以数字而非符号名进行的移植（补丁、日志比对、测试断言、`audio_platform_info.xml` 的数字化写法）都会静默走错设备，而且**很可能仍然出声**（走扬声器保护路径或空路径），因此不会立刻暴露。

**缓解**：补丁中一律使用符号名；在 M3-A 增加一条自检——启动时断言 `strcmp(device_table[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES], "hifi-headphones") == 0`，不成立则拒绝启用 HiFi。

### 风险 2：把"对齐 MIUI"当成 44.1 直通的路线

`docs/reviews/2026-08-29` §8 的执行顺序第 2 步是"审计 …确定是否能为 `hifi-headphones` 选择 44.1 kHz backend 及对应时钟"。这个提法暗含"MIUI 做到了、我们照做"的前提。C3 证明这个前提**是错的**：MIUI 在 deep-buffer 下同样是 48 kHz，其 `HiFi backend bitwidth 0, samplerate 0` 告警就是铁证。

如果按现有顺序推进，最可能的失败形态是：团队在 M3 里花大量预算去"复刻"一个原厂根本不存在的能力，或者更糟——只把 `QUAT_MI2S SampleRate` 改成 `KHZ_44P1` 就宣布成功，而前端仍是 48 kHz，SRC 只是搬到了 ADSP，同时引入了 `docs/04` §7.4 从未验证过的 slave 时钟路径。

**缓解**：把 44.1 拆成独立里程碑 M3.5，且第一条验收就是"读回前端 PCM 与 QUAT backend 两侧速率必须同为 44100"，任一不满足即判定为未达成，不允许部分成功。

### 风险 3：`HIFI_ACTIVE` 证据门漏掉 SLIMBUS 旁路，而 ACDB 门永远过不了

`docs/17` §5 的七条证据里，**没有一条**覆盖 M2 §7.2 实测到的 `MultiMedia5 → SLIMBUS_0_RX` 竞态。而 M2 的第一次实验正是因为这条旁路而产生假阳性——"关闭 QUAT 仍有声"。同一份文档却把结构性不可满足的 ACDB 条件列为必要门。

净效果是**双向错误**：真正危险的假阳性没有被拦住，而一个无害的正常状态会把系统永久钉在 `HIFI_DEGRADED`。后者更隐蔽——团队可能会为了"让状态变绿"去伪造 ACDB ID，从而给 HiFi 设备套上一份**为别的设备标定的校准**。

**缓解**：立刻按 §6.2 替换证据门（新增 E5，删除 E10、改为 E10'）；并在补丁中显式注释"`hifi-headphones` 无 ACDB 条目是原厂行为，禁止借用其他设备的 ACDB ID"。

---

## 12. GO / NO-GO 条件

### 12.1 进入 M3-0（建构建主机、同步源码）— GO 条件

1. `docs/17` 已按 §9 修订并冻结（至少 §5 证据门与 §4 转换 3）；
2. 争议 D-1 已澄清或明确标记为"两值均不可用作默认"；
3. Linux 构建主机可用，且磁盘可用空间在同步 `hardware/qcom/audio` + `device/xiaomi/leo` 后仍 ≥ 6 GiB（`docs/16` §14 停止线）；
4. 本审计的 F1–F21 已由项目主代理独立复核至少 5 条（建议 F4、F6、F11、F14、F20）。

**NO-GO**：以上任一不成立。

### 12.2 进入 M3-B（首次真正改变路由）— GO 条件

1. M3-0 的无修改构建产物已与 `701019bd…` 完成符号级对照，差异逐项可解释；
2. M3-A 在设备上运行，行为与原版 MoKee 逐项一致（至少 A1、A4、A9、A17）；
3. `leo_hifi_status` 可读出完整 evidence bitmap；
4. 回滚材料双份可读、recovery/fastboot 救援入口已实测（沿用 `docs/18` 的 M2 前置门）；
5. 设备所有者当场明确授权。

**NO-GO**：符号对照有无法解释的差异；或 M3-A 出现任何与原版不一致的音频行为；或回滚材料未闭合。

### 12.3 进入 M3-C（首次写 `Volume`）— GO 条件

1. A2、A3 通过，且 A3 中 E5 明确通过（SLIM MUX 已断开）；
2. §4.3 的证伪实验完成，`Volume` 的单调方向已确定；
3. 音量上限已按实验结果设定，且 ≤ 实测无削波点的下一档；
4. SPL 测量条件（曲目、耳机、位置、仪器）已固定并记录。

**NO-GO**：`Volume` 语义未确定；或实验中出现任何爆音/削波。

### 12.4 进入 M3.5（44.1 实验）— GO 条件

1. M3-B、M3-C 全部验收通过并稳定运行 ≥ 一次完整 2 小时息屏播放（A10）；
2. U3 已有明确答案：存在一条可复现的、让 Leo 自有播放器拿到 DIRECT 44.1 输出的路径；
3. 速率变更的 teardown/迟滞/回退代码已通过故障注入（A14 的速率版本）；
4. 已接受"结论可能是不可行"这一前提，并预先约定：不可行时**维持 48 kHz 并在界面标注重采样**，不做任何 hack。

**NO-GO**：U3 无答案；或前两个里程碑存在未闭合的降级现象。

### 12.5 全局 NO-GO（任一成立即停止）

* 需要修改 AudioFlinger、AudioPolicyManager 或 audioserver 才能达成目标；
* 需要把 Android 7 的任何二进制放进 Android 10 运行环境；
* 需要关闭 SELinux 或依赖常驻 root 才能工作；
* `HIFI_ACTIVE` 的判定被简化为"耳机有声"或"property 为 true"；
* 界面在证据不完整时显示"已激活"；
* 为让状态变绿而给 `hifi-headphones` 借用其他设备的 ACDB ID。

---

## 13. 需要项目主代理执行的最小只读采集请求

本审计**不执行**任何设备操作。以下四项若能补齐，可把本文的 H/S 级结论升格为事实。

| # | 目标 | 最小动作 | 风险 | 预期证据 |
| ---: | --- | --- | ---: | --- |
| R1 | 确定 `Volume` 控件的归属与范围 | 在 MoKee 上只读：`tinymix` 详细输出 / `/proc/asound/card0/` 下与该控件相关的条目 | 无（只读） | 控件 min/max、注册者线索 |
| R2 | 确定 `Volume` 的单调方向 | §4.3 的四点扫描（213/225/237/249），完成后恢复 205 | 低（起点为映射最低端；需人耳在场且从低到高） | 主观/SPL 单调性 |
| R3 | 确定 MIUI 中 `hifi_volume` 的写入者 | 在 MIUI 参照系统只读 `grep -r "hifi_volume" /system/framework /system/priv-app /system/app` | 无 | 组件名，用于确认"framework 零改动"结论 |
| R4 | 澄清 D-1 | 核对两次采集的时间戳与来源，确定 `persist.audio.hifi.volume` 究竟是 30 还是 40 | 无 | 单一可信值或"两次采集处于不同状态"的说明 |

以上均**不需要**写入分区、不需要 recovery、不需要重启到 fastboot。

---

## 14. 本轮验证记录

* 逐项重算并核对本文引用的 10 个私有文件 SHA-256，与 `manifests/mokee-audio-delta-v0.1.tsv` 及 `docs/03` 登记值全部一致，无 mismatch；
* 对 stock 32-bit HAL 完成全量反汇编（35,302 行），对 5 个 HiFi 函数、`platform_get_output_snd_device`、`platform_set/get_parameters`、`enable_audio_route`、`platform_check_and_set_codec_backend_cfg` 逐指令解析；所有 PC 相对字符串引用均经独立脚本解析并回读原始字节；
* 对 `use_case_table` 与 `device_table` 直接从 `.data` 段读出，未依赖任何字符串顺序猜测；
* 对 MoKee 32-bit HAL 完成同名函数定位与差异对照；
* 对 MoKee `kernel-image.bin`（arm64 未压缩 Image）做字符串检索，确认 `es9018.c`、`Volume`、`KHZ_44P1`；
* 引用的每条实机数据均来自 `resources/private/phase5b-mokee/m2-runtime-20260828/` 已归档文本，未新增任何设备交互；
* 本轮未执行 `adb`/`fastboot`/`heimdall`，未写任何分区，未修改主工作树 `/Users/km/Desktop/Leo-Audio-OS`，未修改任何镜像、私有资产或回退包，未把任何专有二进制复制进 Git；
* MIUI 归档 `runtime-states/20260824-153316-H1` 在本机不可访问，因此文中所有 MIUI logcat 引用均标注为"项目文档转引"，未被本审计独立复核。

---

## 附录 A：复现命令清单

```bash
cd /Users/km/Desktop/Leo-Audio-OS
S=resources/private/stock-system-tree/lib/hw/audio.primary.msm8994.so
M=resources/private/phase5b-mokee/selected/system/vendor/lib/hw/audio.primary.msm8994.so

# F1/F3 能力缺口
/usr/bin/objdump -T "$S" | grep -i hifi
/usr/bin/objdump -T "$M" | grep -i hifi        # 空
grep -rail hifi resources/private/phase5b-mokee/selected/

# F4 设备选择
/usr/bin/objdump -d --start-address=0x145c0 --stop-address=0x14650 "$S"

# F6 音量
/usr/bin/objdump -d --start-address=0x12de8 --stop-address=0x12f48 "$S"

# F10/F11 后端速率
/usr/bin/objdump -d --start-address=0x176a0 --stop-address=0x17948 "$S"
/usr/bin/objdump -d --start-address=0x17ec4 --stop-address=0x180dc "$S"

# F15 MoKee 补丁点
/usr/bin/objdump -d --start-address=0x17f18 --stop-address=0x17f60 "$M"

# F19 内核
strings -a resources/private/phase5b-mokee/boot-audit-v0.1/kernel-image.bin | grep -iE "es9018|KHZ_44P1"

# F20 实机
grep -nE "Volume|QUAT_MI2S" resources/private/phase5b-mokee/m2-runtime-20260828/tinymix-B-state.txt
```

`use_case_table` / `device_table` 的读取需要一个 ELF 段解析脚本：先按程序头建立 vaddr ↔ 文件偏移映射
（stock 的第二个 `PT_LOAD` 为 `off=0x31510 → vaddr=0x32510`，故 `.data.rel.ro` 中文件偏移与 vaddr 相差 `0x1000`；
MoKee 的各 `PT_LOAD` 中两者相等），再在数据段中搜索目标字符串 vaddr 的 32-bit 小端字，
然后连续读取指针数组并逐项解析 C 字符串。
