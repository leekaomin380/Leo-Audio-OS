# M3 HiFi 架构第二轮综合裁决（草案）

日期：2026-08-29
裁决者：Claude Opus 5（独立首席架构审计者）
本方基线：`805989e` — [`docs/research/CLAUDE-OPUS5-HIFI-CONTROLLER-ARCHITECTURE.md`](CLAUDE-OPUS5-HIFI-CONTROLLER-ARCHITECTURE.md)（保留不改）
对方材料：`research/agy-gemini31pro-audio-evidence` @ `702f7e8`（只读审阅，未 cherry-pick、未修改其工作树）
执行边界：本轮未连接设备、未运行 `adb`/`fastboot`、未修改镜像、未推送、未合并。

> **本轮最重要的进展**：ES9018 `Volume` 控件的 min/max、invert、TLV、dB 步长与单调方向
> **已经离线闭合为事实**——不再是未知项。方法是从项目已持有的 MoKee 内核映像中直接
> 提取 `snd_kcontrol_new` 数组、`soc_mixer_control` 与 TLV 表（§4）。双方上一轮都把它
> 当成"必须实机才能回答"的问题，这个判断是错的。

---

## 0. 十项裁决速览

| # | 议题 | 裁决 | 等级 |
| ---: | --- | --- | --- |
| 1 | MoKee 实际加载的 32-bit HAL 哈希与源码谱系是否闭合 | **哈希链路可解释但缺最后一环**（无设备端实测哈希）；**源码谱系未闭合**，双方各执一说且均不可离线验证 | 事实 / 未知 |
| 2 | `platform_check_hifi_backend_cfg` 真实控制流 | `usecase->id != 3` → **直接返回 0，不写任何值**。agy「主动写 0xbb80」**错误**。且该函数**零调用者**，真实路径是 `platform_check_and_set_codec_backend_cfg`（由 `select_devices` 调用） | 事实 |
| 3 | deep-buffer / DIRECT PCM / compress-offload 的采样率处理 | 三者在 HAL 里的差别**只有 usecase id**；且判据是 `id == 3` **严格相等**，`offload2..9`(4..11) 同样拿不到 HiFi 后端配置 | 事实 + 未知（DIRECT PCM 的 id 分配） |
| 4 | ES9018 `Volume` 的 min/max/invert/TLV/方向/步长 | `min=0 max=255 reg=15 rreg=16 invert=1`；TLV = `DB_SCALE(-127.50 dB, 0.50 dB/step)`；**控件值越大越响** | **事实（本轮新闭合）** |
| 5 | `persist.audio.hifi.volume` 是否与 Android 软件音量叠加 | **叠加**。ES9018 数字衰减与 AudioFlinger 软件衰减串联，互不感知 | 高可信推断 |
| 6 | `Volume = 205` 是否足以解释 MoKee HiFi 响度小 | **足以**。205 = −25.0 dB；MIUI 在 `hifi_volume=30` 时为 225 = −15.0 dB，**差 10.0 dB** | 事实（映射）+ 高可信推断（因果唯一性） |
| 7 | M3 是否只含自动路由、独立音量、状态机 | **是，但必须加一项**：HiFi 进入/退出时**确定性写死 `KHZ_48` / `S24_LE`**，因为"不碰"不等于"正确"（陈旧速率风险，§3.4） | 裁决 |
| 8 | M3.5 的 44.1 无 SRC 前置条件 | 七项硬前置，见 §7.2；其中"证明 DIRECT PCM 拿到 `id == 3`"是**否决性**前置 | 裁决 |
| 9 | `hifi-headphones` 无 ACDB ID 如何成为可接受的已知状态 | 显式建模为 `ACDB_ABSENT_EXPECTED`，写入白名单常量并在状态里单独上报；**禁止**借用其他设备 ACDB ID | 裁决 |
| 10 | MultiMedia5→SLIMBUS 旁路如何进入致命证据门 | 三条并联硬断言（E5a/E5b/E5c），任一不满足即 `ERROR_FALLBACK`，见 §8.3 | 裁决 |

---

## 1. agy 与 Claude 的共识、分歧与最终裁决

### 1.1 共识（双方独立得出，互为交叉验证）

| # | 共识 | 双方证据 |
| ---: | --- | --- |
| K1 | MoKee 32-bit HAL 完全缺少小米专有 HiFi 逻辑（枚举、属性、函数、QUAT 控件名） | agy：`strings` 空集；Claude：`objdump -T` 导出符号空集 + 全树 `grep -rail hifi` |
| K2 | Stock HAL 通过 `platform_get_hifi` 判定并返回 `SND_DEVICE_OUT_HIFI_HEADPHONES` | agy：符号存在；Claude：`platform_get_output_snd_device` @`0x145dc–0x14614` 逐指令 |
| K3 | `persist.audio.hifi.volume` → `set_hifi_volume` → ALSA `"Volume"` 控件 | 双方一致 |
| K4 | 只有 `usecase->id == 3` 的路径能把流的真实采样率下发到 QUAT 后端 | 双方一致 |
| K5 | 仅改 XML 无法点亮 HiFi，必须动 HAL 代码 | 双方一致 |
| K6 | 消除 SRC 不能只改 HAL 后端，必须保证前后端同率，否则更糟 | 双方一致（Claude 第一轮 §5.1；agy 修正后 §5） |
| K7 | 内核/DTB/mixer XML/声卡枚举均无需改动 | 双方一致，且与 `docs/reviews/2026-08-28` §8 一致 |

### 1.2 分歧与裁决

| # | agy 主张 | Claude 主张 | **裁决** | 依据 |
| ---: | --- | --- | --- | --- |
| **X1** | `usecase->id != 3` 时 HAL **主动写入** `0xbb80`(48000)/`16` 并更新缓存 | `id != 3` 时函数**直接返回 0，不写任何值**；48000 仅用于通话/VoIP 分支与 `stream.out == NULL` 兜底 | **Claude 成立，agy 错误** | 见 §3.1 逐指令 |
| **X2** | 修复点是 `platform_check_hifi_backend_cfg` | 该符号**导出但零调用**；活路径是被内联进 `platform_check_and_set_codec_backend_cfg` 的同源代码，调用者是 `select_devices` | **Claude 成立** | §3.2 PLT 与 BL 扫描 |
| **X3** | MoKee `audio_policy_configuration.xml` 含 `hifi-headphones` | 只有 `mixer_paths.xml` 含 hifi 路径；policy XML 不含 | **Claude 成立，agy 错误** | §3.5 |
| **X4** | `<ctl name="Volume" value="205" />` 来自 `mixer_paths.xml` | Claude 第一轮写作"内核驱动默认值 205" | **agy 成立，Claude 第一轮错误** | `mixer_paths.xml:410`，MoKee 与 stock **同一行同一值** |
| **X5** | ES9018 `Volume` 语义因缺 `es9018.c` 源码而"未知" | 第一轮同样列为未知 | **双方均可被超越**：语义可从项目已持有的 MoKee 内核映像离线提取，现已闭合为事实 | §4 |
| **X6** | MoKee HAL 谱系 = LineageOS `android_hardware_qcom_audio` @ `e20a6987…` | 项目 M2 记录 = `mkq-mr1-caf-msm8994` @ `7f4cac74…` | **均未闭合**；两者不可离线验证，且互相冲突。以项目自身 M2 记录为工作假设，真正闭合留给 M3-0 的构建对照 | §2 |
| **X7** | 建议"强制 Apple Music 走 Offload/Direct 模式" | 应用侧 PCM 流无法被强制进 compress-offload；只可能走 direct PCM，而 direct PCM 的 usecase id 归属 agy 自己标为未知 | **Claude 成立**；agy 该建议自相矛盾 | §5.3 |
| **X8** | `Volume` 写入"绕过 Android 软件音量"（rev1 已降级为"待验证"） | 二者**串联叠加**，不是绕过 | **Claude 成立**；agy 的降级方向正确但未给出结论 | §5 |

### 1.3 Claude 第一轮需要自我更正的两处

1. **§4.3 / §2.3**：把 `Volume = 205` 说成"停在内核驱动默认值"。**错误**——205 由 `mixer_paths.xml:410` 的 `<!-- HIFI -->` 顶层默认块在 `audio_route_init` 时写入，MIUI 与 MoKee 是同一份文件、同一行、同一值。结论方向不变（MoKee 从不覆盖它，MIUI 在 `platform_init` 覆盖），但归因必须改。
2. **§10.2 H1**（`Volume` 属于 es9018）：由"高可信推断"升级为**事实**（§4）。

---

## 2. 裁决 1：HAL 哈希与源码谱系

### 2.1 哈希链路

```text
MoKee ROM zip   e1d32441513d49108802cc426b0891f7c3be577f2cb41d4030b4fe2ddf614390
   ↓ transfer-list v4 重建
system.img      695eba5e…fe7b            （M2 实际写入设备的镜像）
   ↓ 只读提取
selected/system/vendor/lib/hw/audio.primary.msm8994.so
                701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47
   ↓ M2 运行时
pid 442 /vendor/bin/hw/android.hardware.audio@2.0-service → audio.primary.msm8994.so（32-bit）
```

**裁决**：链路**可解释但缺最后一环**。M2 采集的是 `/proc/442/maps` 里的**文件名**，不是设备端文件的 SHA-256。
「设备上运行的就是 `701019bd…`」目前是**高可信推断**（同一镜像、只读挂载、无 OTA addon 覆盖该路径），不是事实。
补齐成本极低：一条 `sha256sum /vendor/lib/hw/audio.primary.msm8994.so`（只读）。列为采集请求 R5（§10）。

附加事实（本轮新增，双方均未提供）：

```text
.note.android.ident  API level
  stock  0x18 = 24  → Android 7.0     ✔
  MoKee  0x1d = 29  → Android 10      ✔
.comment
  stock  GCC 4.9 20150123 + Android clang 3.8.256229
  MoKee  该节已被 strip，无编译器指纹
```

MoKee HAL 内不含任何 `__FILE__` 形式的源码路径字符串。**因此源码谱系无法从二进制离线闭合。**

### 2.2 源码谱系

| 主张 | 来源 | 可离线验证 |
| --- | --- | --- |
| `mkq-mr1-caf-msm8994` @ `7f4cac748b6f62897294cdaece9d1aec27e1e927` | `docs/reviews/2026-08-28-phase5b-m2-mokee-runtime-baseline.md` §8 | 否 |
| LineageOS `android_hardware_qcom_audio` @ `e20a6987ebc734a1e554836874da3b13383a2e4d` | agy `702f7e8`（自述为"结构类比"，但 TSV 仍填入 `commit_or_sha256` 且 confidence=High） | 否 |

**裁决**：**未闭合**。两者互相冲突且都没有本地产物支撑。
处置：以项目自身 M2 记录为工作假设（它至少与 MoKee 发行版身份同源），把 agy 的 LineageOS commit 降级为"结构参考，不作为 commit 级证据"。
唯一可接受的闭合方式是 **M3-0 的无修改构建 + 与 `701019bd…` 的符号级对照**（这已经是我第一轮 §7 的 M3-0 完成判据）。

**对 agy 的具体要求**：`agy-hal-evidence.tsv` 的 HAL-04、`agy-samplerate-evidence.tsv` 的 SR-04/SR-05 三行，`commit_or_sha256` 字段填了一个无法验证的 commit 且 confidence 标 High，应改为 `N/A` + confidence `Inference`，否则会把一个未验证的外部 commit 固化成项目证据。

---

## 3. 裁决 2 与 3：真实控制流与三类通路

### 3.1 `platform_check_hifi_backend_cfg` 逐指令（stock 32-bit HAL `0b8e3f62…`）

```text
17948 <platform_check_hifi_backend_cfg>:          ; (adev, usecase, *out_bw, *out_sr)
17960: bl   voice_is_in_call
17964: cmp  r0, #0
17968: bne  0x17978                 ; 通话中 → 默认分支
1796c: ldr  r0, [r6, #0xa0]         ; adev->mode
17970: cmp  r0, #3                  ; AUDIO_MODE_IN_COMMUNICATION
17974: bne  0x179fc                 ; 非 VoIP → usecase 检查
17978: … log "%s: Use default bw and sr for voice/voip calls "
17998: movw r1, #0xbb80             ; 48000  ← 只有通话/VoIP/空流兜底才到这里
1799c: mov  r2, #16
…
179f4: add  sp, sp, #8              ; return r0
179f8: pop  {r4,r5,r6,r7,r11,pc}
179fc: ldr  r1, [r7, #0x8]          ; usecase->id
17a00: mov  r0, #0                  ; ★ 返回值先置 false
17a04: cmp  r1, #3
17a08: bne  0x179f4                 ; ★★ id != 3 → 直接返回 0，*out_bw/*out_sr 未被写
17a0c: ldr  r0, [r7, #0x1c]         ; usecase->stream.out
17a10: cmp  r0, #0
17a14: beq  0x17998                 ;  NULL → 才退回 48000/16
17a18: ldr  r1, [r0, #0xb4]         ; out->sample_rate
17a1c: ldr  r2, [r0, #0x158]        ; out->bit_width
17a20: b    0x179a0
```

**裁决 X1：agy 的 SR-01 与 `AGY-CORRECTION-NOTES.md` §2「`usecase->id != 3`：执行 `movw r1, #0xbb80` 主动硬编码为 48 kHz」是错误的。**
`bne 0x179f4` 跳向的是 `return 0`，不是 `0x17998`。agy 引用的片段 `cmp r0,#3 ; bne ... movw r1,#0xbb80` 把两处不同的 `cmp #3`（`adev->mode == 3` 与 `usecase->id == 3`）拼在一起，并把分支方向读反了。

这不是措辞之争。两种读法给出**完全不同的补丁方案**：

| 读法 | 推出的补丁 | 实际后果 |
| --- | --- | --- |
| agy：主动写 48000 | "删掉硬编码即可" | **无效补丁**——没有这行代码可删 |
| 实际：不写 | 必须**新增**写入逻辑，并额外承担"控件残留旧值"的风险（§3.4） | 补丁面更大，但方向正确 |

### 3.2 谁真正被调用

```text
platform_check_hifi_backend_cfg      → .so 内无 PLT 桩、无 BL       ⇒ 零调用者（死符号）
platform_check_and_set_codec_backend_cfg @0x17ec4
   ← BL@0x751c  ∈ select_devices @0x7048+0x4d4
   → BL@0x18050 platform_set_hifi_backend_cfg@plt
```

`platform_check_and_set_codec_backend_cfg` 内联了同一段逻辑（`0x1807c: cmp usecase->id,#3 ; bne 0x18058` → 跳过整个 HiFi 后端处理直接返回）。

**裁决 X2：任何"patch `platform_check_hifi_backend_cfg`"的方案都是空操作。** 补丁点是 `select_devices` → `platform_check_and_set_codec_backend_cfg`。

### 3.3 三类通路的差别只有 usecase id

从 stock 与 MoKee 两份 HAL 的 `use_case_table` 直接读出（顺序一致）：

```text
[0] deep-buffer-playback        [1] low-latency-playback
[2] multi-channel-playback      [3] compress-offload-playback     ← 唯一被认可的 id
[4..11] compress-offload-playback2 .. 9
[12] audio-ull-playback         …
```

| 通路 | usecase id | HiFi 后端是否被配置 | 前端速率 |
| --- | ---: | --- | --- |
| mixed / primary | 0 或 1 | **否** | AudioFlinger MixerThread 固定率（实测 48 kHz） |
| deep-buffer | 0 | **否** | 同上 |
| low-latency / ULL | 1 / 12 | **否** | 48 kHz |
| DIRECT PCM (`direct_pcm`) | **未知**，见下 | 取决于 id | 按流参数打开 |
| compress-offload 第 1 路 | 3 | **是** | 按流参数 |
| compress-offload 第 2–9 路 | 4–11 | **否**（`cmp #3` 严格相等） | 按流参数 |

**本轮新发现（双方此前均未指出）**：判据是**严格等于 3**，不是 `is_offload_usecase()` 范围判断。
因此在 MIUI 上，只要第一路 offload 会话被占用、第二路流拿到 `USECASE_AUDIO_PLAYBACK_OFFLOAD2`(4)，
**HiFi 后端速率就不会被配置**。这是原厂实现的一个真实脆弱点，我们的控制器**不得照抄**——
必须用 `is_offload_usecase(uc->id)` 或显式集合 `{3..11}`。

**DIRECT PCM 的 id 归属：未知。** CAF 一代把 `AUDIO_OUTPUT_FLAG_DIRECT_PCM` 并入 offload usecase 族，
Android 9 后该 flag 取消。stock `audio_policy.conf` 的 `direct_pcm` 确实带 `AUDIO_OUTPUT_FLAG_DIRECT_PCM`；
MoKee 的 `direct_pcm` mixPort 只带 `AUDIO_OUTPUT_FLAG_DIRECT`。**无法离线判定**，与 agy 的 SR-05 结论一致。
这是 M3.5 的否决性前置（§7.2 P3）。

### 3.4 由"不写"引出的陈旧速率风险（新增，必须进设计）

因为 `id != 3` 时 HAL **什么都不做**，`QUAT_MI2S SampleRate` / `BitWidth` 保留上一次被写入的值：

```text
场景：DIRECT/offload 播放 44.1 kHz  → HAL 写 KHZ_44P1
      流结束，无任何代码把它写回 KHZ_48
      普通 App 走 deep-buffer 48 kHz → HAL 不检查、不写
      ⇒ 前端 48 kHz / QUAT 后端 KHZ_44P1，速率错配
```

全 `.so` 内 `QUAT_MI2S SampleRate` 的唯一写入点是 `platform_set_hifi_backend_cfg`，而它唯一的调用点是
`0x18050`。**没有任何 teardown/reset 路径。**

**裁决**：M3 的 Leo HiFi Controller **必须在每次进入 HiFi 路由时确定性写入目标速率/位宽并读回**，
而不是"沿用当前值"。第一版目标值固定为 `KHZ_48` / `S24_LE`。这就是 §0 裁决 7 里那条附加要求的来源。

### 3.5 XML 事实核对

```bash
grep -in hifi .../mokee/.../audio_policy_configuration.xml   # → 无匹配
grep -n  'name="Volume"' .../mokee/.../mixer_paths.xml       # → 410: <ctl name="Volume" value="205" />
```

`mixer_paths.xml` 第 405–415 行是一个显式的 `<!-- HIFI -->` **顶层默认块**（不在任何 `<path>` 内，
因此由 `audio_route_init` 在 HAL 启动时一次性下发）：

```xml
<!-- HIFI -->
<ctl name="Volume" value="205" />
<ctl name="Automute Level" value="120" />
<ctl name="Filter Shape" value="Minimum Phase" />
<ctl name="DPLL DSD Bandwidth" value="1" />
<ctl name="DPLL I2S Bandwidth" value="1" />
<ctl name="THD Compensation" value="0" />
<ctl name="THD2 Compensation" value="255" />
<ctl name="THD3 Compensation" value="1" />
<ctl name="Custom Filter" value="OFF" />
<ctl name="Smartpa Preset" value="0" />
```

MoKee 与 stock 的 `mixer_paths.xml` 逐字节相同（`13db0e6e…`），所以**两套系统都把 `Volume` 初始化为 205**；
差别只在 MIUI 的 `platform_init` 随后用 `set_hifi_volume()` 覆盖它，MoKee 没有。

---

## 4. 裁决 4：ES9018 `Volume` 控件语义（本轮闭合为事实）

### 4.1 提取方法（可复现，全离线）

对象：`resources/private/phase5b-mokee/boot-audit-v0.1/kernel-image.bin`
SHA-256 `fbbd8d466e920ef4d96aba5756a194fb578e8c385c22f4839bbb5a51519b3089`（arm64 未压缩 Image，`text_offset = 0x80000`）

1. 解出内核虚拟基址：设 `VA(f) = BASE + f`，用 ES9018 控件名字符串（`Automute Level` @`0x17954f7` 等）
   在文件中反查绝对指针，得 **`BASE = 0xffffffc000080000`**（= `PAGE_OFFSET(0xffffffc000000000) + TEXT_OFFSET(0x80000)`，与 3.10 arm64 一致）。
2. 定位 `snd_kcontrol_new` 数组：`name` 位于结构 `+16`，`struct` 大小 80 字节（arm64）。
   从 `Automute Level` 的指针 `-16` 起以 80 字节步长枚举，得到 **完整 17 项 ES9018 控件表**：

```text
[-1] Automute Time      [ 0] Automute Level     [ 1] Automute Loopback
[ 2] Volume Ramp Rate   [ 3] Mute               [ 4] Filter Shape
[ 5] Channel Select     [ 6] Channel Analog Swap[ 7] DPLL DSD Bandwidth
[ 8] DPLL I2S Bandwidth [ 9] THD Compensation   [10] Volume        ← access=0x13, 有 TLV
[11] THD2 Compensation  [12] THD3 Compensation  [13] Custom Filter
[14] Coefficient Stage1 [15] Coefficient Stage2 [16] HPH Impedance
```

与 M2 实机 `tinymix` 第 897–913 号控件**逐项一一对应**。这同时把第一轮的 H1（"`Volume` 属于 es9018"）
从推断升格为**事实**。

3. `Volume` 的 `private_value` → `struct soc_mixer_control` @`0xffffffc001d45ff8`（32 字节，8×u32）：

```text
min          = 0
max          = 255
platform_max = 255
reg          = 15    (0x0F)   ← ES9018 Volume1（左）
rreg         = 16    (0x10)   ← ES9018 Volume2（右）
shift        = 0
rshift       = 0
invert       = 1     ★
```

对照校验：`Automute Level` 的同结构为 `min=0 max=127 pmax=127 reg=5 rreg=5 shift=0 rshift=0 invert=0`，
实机值 120 ≤ 127 ✔；`THD Compensation` 为 `min=0 max=255 reg=13 rreg=13 invert=0` ✔。结构解读自洽。

4. `Volume` 的 `tlv.p` → `0xffffffc0011452e8`：

```text
p[0] = 1        SNDRV_CTL_TLVT_DB_SCALE
p[1] = 8        data 长度（字节）
p[2] = -12750   最小值 = -127.50 dB
p[3] = 50       步长 = 0.50 dB，无 mute 标志位
```

### 4.2 结论

```text
控件值 v ∈ [0, 255]
硬件寄存器 = 255 - v        （invert = 1）
增益(dB)   = -127.50 + 0.50 × v
⇒ v 越大越响；v = 255 → 0 dB；v = 0 → -127.5 dB
```

与 ESS9018K2M 数据手册一致：寄存器 15/16 为**衰减**，0 = 0 dB，0.5 dB/步，255 = −127.5 dB。
`invert = 1` 正是把"寄存器越大越小声"翻转成"控件越大越响"。

| 语境 | 控件值 | 寄存器 | 增益 |
| --- | ---: | ---: | ---: |
| `mixer_paths.xml` 默认（MIUI 与 MoKee 共有） | 205 | 50 | **−25.0 dB** |
| MIUI `hifi_volume = 0` | 213 | 42 | −21.0 dB |
| MIUI `hifi_volume = 30`（logcat 记录值） | 225 | 30 | **−15.0 dB** |
| MIUI `hifi_volume = 40`（property manifest 记录值） | 229 | 26 | −13.0 dB |
| MIUI `hifi_volume = 100` | 253 | 2 | −1.0 dB |
| 控件上限 | 255 | 0 | 0.0 dB |

即 MIUI 的 `hifi_volume` 是一条 **`dB = −21.0 + 0.2 × v`** 的线性 dB 曲线，总跨度 **20 dB**。

附带事实：`Volume Ramp Rate = 2` 是 ES9018 自带的音量斜坡控件，驱动侧已有渐变，
但它不替代 HAL 侧的步长限制（§6.3）。

### 4.3 对上一轮"不得指定默认寄存器值"约束的处理

任务约束是"**未知方向未闭合前**不得指定默认寄存器值"。**方向现已闭合为事实**（invert=1 + DB_SCALE，
且证据直接取自 MoKee 实际启动的那份内核映像），因此该约束的前提已解除，可以给出默认值。
但仍保留一道**实机读回门**：首次写入前必须先读回 `Volume` 确认为 205，写入后必须读回确认命中目标值（§6.2）。

---

## 5. 裁决 5 与 6：叠加关系与响度缺口

### 5.1 是否与 Android 软件音量叠加

```text
AudioTrack 样本
  → AudioFlinger MixerThread：应用 stream/track 音量（软件乘法衰减）
  → HAL out_write → MultiMedia1 → QUAT_MI2S_RX（AFE 数字域，QUAT_MI2S_RX Volume = 8192 满值）
  → ES9018 数字音量寄存器 15/16 ← "Volume" 控件（-25.0 dB @205）
  → ESS 模拟输出 → OPA1612（固定增益）→ 耳机插孔
```

- stock HAL 的 `out_set_volume` 只对 compress/offload 会话有 mixer 级音量（证据：`Compress Playback %d Volume` 字符串族，
  实机第 929/938/944… 号控件，全部 `8192 8192`）；**deep-buffer/mixer 路径没有任何 per-stream mixer 音量控件**，
  Android 音量只能由 AudioFlinger 在软件混音器里施加。
- ES9018 `Volume` 由 HAL 独立写入，与 Android 音量索引无任何数据通路。

**裁决**：**两者串联叠加**，总增益 = `软件衰减(Android index) × 10^(dB_ES9018/20)`。
agy 第一轮的"绕过软衰减"是错的，rev1 降级为"待验证"方向正确但没给结论；正确表述是**叠加**。
等级：**高可信推断**（架构必然性 + 控件集合证据），实机证伪只需一步：改变 Android 音量后读回 `Volume`，应保持不变。

**直接后果**：把 `Volume` 从 205 抬到 MIUI 区间，等于在 Android 刻度之外整体 +4…+12 dB，
因此**必须有上限**，否则 Android 满刻度 + `Volume=253` 会把 OPA1612 推到接近满摆幅。

### 5.2 205 是否足以解释响度缺口

| 对比 | 增益 | 差值 |
| --- | ---: | ---: |
| MoKee 现状（205） | −25.0 dB | — |
| MIUI @ `hifi_volume=30`（225） | −15.0 dB | **10.0 dB** |
| MIUI @ `hifi_volume=40`（229） | −13.0 dB | **12.0 dB** |

**裁决：足以，且是主导因素。** 10–12 dB 在主观上约等于"响度减半"，与用户描述的"相同 Android 音量刻度下明显更轻"完全吻合。

同时排除其他候选：`QUAT_MI2S_RX Volume` 实机为 8192（该控件最大值，无衰减）；
WCD 侧 `RX*/HPH*` 在 HiFi 态被刻意切断，不参与；AFE 位宽 S24_LE 不影响电平。

**残留不确定性**：无法排除"还存在第二个较小的差异源"（例如 ACDB 缺失导致的 AFE 增益差、或 Dirac 效果差异）。
因此判据写成"**足以解释**"，而不是"**唯一原因**"。实机 A7（SPL 对照）会给出最终数字。

**争议 D-1 的新意义**：`hifi_volume` 究竟是 30 还是 40，现在直接对应 **10.0 dB 还是 12.0 dB** 的目标差值，
不再是无关紧要的记录差异。必须澄清（采集请求 R4）。

---

## 6. 音量模型与安全默认值

### 6.1 模型

```c
/* 唯一真值：HAL 内 my_data->leo_hifi_volume ∈ [0, LEO_HIFI_VOL_MAX] */
/* 映射（沿用 MIUI 曲线，但参数化，不硬编码在调用点） */
#define LEO_HIFI_CTL_BASE   213      /* v=0  → -21.0 dB */
#define LEO_HIFI_CTL_SLOPE_NUM 2     /* 每 1 单位 = 0.4 控件步 = 0.2 dB */
#define LEO_HIFI_CTL_SLOPE_DEN 5
static int leo_hifi_vol_to_ctl(int v) {
    return LEO_HIFI_CTL_BASE + (v * LEO_HIFI_CTL_SLOPE_NUM) / LEO_HIFI_CTL_SLOPE_DEN;
}
/* 硬性钳位，永不越过 */
#define LEO_HIFI_CTL_FLOOR  205      /* = mixer_paths.xml 默认，-25.0 dB，任何情况下不低于此 */
#define LEO_HIFI_CTL_CEIL   237      /* 第一版硬上限，-9.0 dB，见 6.2 */
```

### 6.2 安全默认值（方向已闭合，可以指定）

| 参数 | 第一版取值 | 增益 | 理由 |
| --- | ---: | ---: | --- |
| `vendor.leo.audio.hifi.volume` 缺省 | **0** | −21.0 dB | MIUI 曲线的最低点；比现状 205 只高 4.0 dB，是"可听到差别但不可能造成危险"的最小有效步 |
| 第一版硬上限 `LEO_HIFI_VOL_MAX` | **60** | −9.0 dB（控件 237） | 比 MIUI 实测使用点（−15 dB）高 6 dB 的余量，同时距 0 dB 仍有 9 dB 安全裕度 |
| 绝对下限 | 控件 205 | −25.0 dB | 与出厂 XML 一致，保证任何失败路径回到已知安全点 |
| 单次调整步长上限 | 5 单位（1.0 dB） | — | 与 ES9018 `Volume Ramp Rate=2` 叠加，双重防跳变 |
| 模式切入时的写入时机 | **在 QUAT 路由建立之前** | — | 此时 ESS 仍处 mute / soft-start 前，不会产生突发响度 |

上限 60 在完成 A7（SPL 对照）并确认无削波后，方可由**构建期常量**（非运行时 property）放宽。

### 6.3 恢复与失败规则

```text
冷启动    platform_init: 读 property → clamp[0,MAX] → 写控件 → 读回校验
          读回失败 → 写回 205 → 记录 fail_code=4 → 不阻塞启动
进入 HiFi HIFI_ARMING 第一步重写一次并读回（防止其他组件改动过）
退出 HiFi 不改 Volume（它只作用于 ESS 支路；下次进入必重设）
写失败    立即写回 205 并读回；仍失败 → ERROR_FALLBACK, fail_code=2
越界请求  拒绝并保持原值，上报 fail_code=9（新增）
```

---

## 7. M3 与 M3.5 的精确边界

### 7.1 M3 —— **含**以下四项，**不含**其他任何内容

| 项 | 内容 | 判据 |
| --- | --- | --- |
| **M3-a 自动路由** | 有线耳机 + `leo_hifi_mode` 为真 → 选择 `SND_DEVICE_OUT_LEO_HIFI_HEADPHONES`；应用 `deep-buffer-playback hifi-headphones` | 实机 A/B/A 因果复现，旁路门通过 |
| **M3-b 独立音量** | ES9018 `Volume` 的写入、读回、钳位、持久化 | A7/A8 通过 |
| **M3-c 状态机** | 七状态 + generation + fail_code + evidence bitmap + 只读发布 | A11–A15 通过 |
| **M3-d 后端确定性**（本轮新增） | 进入 HiFi 时**显式写入 `KHZ_48` / `S24_LE` 并读回**；退出时同样确定性写回 `KHZ_48` | 读回一致；跨会话不残留旧值 |

M3-d 不是"做 44.1"，恰恰相反——它是把后端**钉死在 48 kHz**，消除 §3.4 的陈旧速率风险，
让 M3 的所有观测都建立在一个确定的后端状态上。没有这一项，M3.5 的对照实验将无基线。

**M3 明确不含**：任何 44.1 kHz 尝试、任何 DIRECT/offload 通路改造、任何 AudioPolicy XML 改动、
任何 framework 改动、任何 ACDB 注入、任何 Dirac 变更、任何删包。

### 7.2 M3.5 —— 44.1 kHz 无 SRC 实验的前置条件

全部满足才允许开始；任一不满足即**不开始**（不是"边做边看"）。

| ID | 前置条件 | 类型 | 验证方式 |
| --- | --- | --- | --- |
| **P1** | M3-a…M3-d 全部验收通过，并完成一次 ≥2 h 息屏连续播放无降级 | 硬门 | A10 |
| **P2** | 后端速率写入/读回/回退代码已通过故障注入（写失败、读回不符、超时三种） | 硬门 | A14-rate |
| **P3** | **已实测证明存在一条可复现路径，使 Leo 自有播放器打开的 44.1 kHz 输出在 HAL 内拿到 `is_offload_usecase()` 为真的 usecase** | **否决性硬门** | 运行时读 `leo_hifi_status.usecase_id` |
| **P4** | 已确认前端 PCM 与 QUAT 后端两侧速率可同时读回，且读回接口不依赖日志 | 硬门 | `/proc/asound/card0/pcm*p/sub0/hw_params` + `tinymix` |
| **P5** | 已明确迟滞策略（≥2 s）与 teardown 顺序，并在 48 kHz 下先行演练过一次"假重协商" | 硬门 | 演练记录 |
| **P6** | 已接受"结论可能为不可行"，并预先约定不可行时维持 48 kHz + 界面标注"重采样" | 契约 | 书面确认 |
| **P7** | `docs/04` §7.4 的 LPASS slave 固定 3.072 MHz IBIT 参数问题已列为本实验的**首要观察项**，实验设计中包含"变速/音调错误"的显式判据 | 硬门 | 实验方案 |

P3 是否决性的：如果 DIRECT PCM 拿不到 offload usecase，44.1 在本平台上就**没有用户可达的通路**，
M3.5 应直接判定为"不可行"并终止，而不是转而去改 deep-buffer 的后端速率（那只会把 SRC 从 AudioFlinger 移到 ADSP）。

---

## 8. 状态机、旁路检测、ACDB 与回退

### 8.1 状态与失败码（在第一轮 §6 基础上的增量）

新增失败码：

| code | 含义 | 目标状态 |
| ---: | --- | --- |
| 9 | 音量请求越界 | 保持原状态，不降级 |
| 10 | 后端速率/位宽读回与目标不符（M3-d） | `HIFI_DEGRADED` |
| 11 | 检测到活动 offload 会话不在 `{3..11}` 认可集合内 | `HIFI_DEGRADED` |

### 8.2 证据门（在第一轮 E1–E9 基础上的修订）

| # | 证据 | 等级 | 变化 |
| ---: | --- | --- | --- |
| E1 | AudioPolicy 输出设备为有线耳机 | 致命 | — |
| E2 | HAL 选中 `LEO_HIFI_HEADPHONES` | 致命 | — |
| E3 | `/sys/bus/i2c/devices/6-0048/driver` → `es9018` | 致命 | — |
| E4 | `QUAT_MI2S_RX Audio Mixer MultiMedia<N>` 读回 = On（N = 本 usecase 的前端） | 致命 | 由固定 MM1 改为按 usecase 解析 |
| **E5** | **旁路三联断言**（§8.3） | **致命** | 强化 |
| E6 | `QUAT_MI2S BitWidth` / `SampleRate` 读回 = Controller 目标值 | **致命**（M3-d 之后） | 由非致命升级；因为 M3-d 之后目标值是确定写入的，读回不符意味着有第三方在改控件 |
| E7 | `Volume` 读回 = 期望值且 ∈ [205, 上限] | 非致命 → DEGRADED | 增加范围断言 |
| E8 | 活动 PCM_PLAYBACK 流 ≥ 1 且 `pcm_state` = RUNNING | 致命 | — |
| E9 | 本 generation 内无 mixer 写失败 / linker 错误 | 致命 | — |
| **E10'** | ACDB 查询结果 ∈ `{OK, ABSENT_EXPECTED}` | 非致命 | 见 §8.4 |

阻抗值仍**不作为证据门**（M2 §7.1 已证其在 QUAT 启动前无效）。

### 8.3 裁决 10：MultiMedia5 → SLIMBUS 旁路的致命证据门

M2 的假阳性形态是：主路由被切断后 AudioFlinger 立刻另开 `SLIMBUS_0_RX ← MultiMedia5`，
经 WCD9330 内置耳放出声（`16-falsification.txt` 记录了该状态下 `SLIMBUS_0_RX Audio Mixer MultiMedia5 = On`）。
只检查"QUAT 已开"完全无法发现它。

**三联断言（全部为致命，任一失败 → `ERROR_FALLBACK`, fail_code=6）**：

```text
E5a  数字侧：对 N ∈ [1..16]，"SLIMBUS_0_RX Audio Mixer MultiMedia<N>" 读回必须全为 Off
     （实机控件 641–656，共 16 项；MoKee 正常耳机态下 MM1=On，HiFi 态必须全 Off）

E5b  模拟侧："HPHL DAC Switch" 读回必须为 Off
     （实机控件 806；这是 WCD 耳放到插孔的实际模拟闸门，声卡只有 HPHL 一个该名控件）

E5c  通路侧："SLIM RX1 MUX" 与 "SLIM RX2 MUX" 读回必须为 ZERO
     （实机控件 814 / 813）
```

**采样时机**：不能只在进入时查一次。必须在
① `HIFI_ARMING` 结束前，
② 每次 `select_devices()` 之后，
③ 息屏/后台期间每 30 s 的轻量巡检，
三处各查一次，且三次必须属于同一 generation 才允许维持 `HIFI_ACTIVE`。

**为什么是致命而非降级**：M2 已证明该旁路会**真实出声**。若只降级为 `HIFI_DEGRADED` 而继续播放，
用户听到的是 WCD 耳放的声音，界面却仍在谈论 HiFi——这正是 `docs/17` §9 定义的阻断缺陷。
正确行为是主动回退到 `headphones`（标准路径），让声音来源与界面陈述一致。

### 8.4 裁决 9：ACDB 缺失如何成为"可接受的已知状态"

事实基础：stock 与 MoKee 的 `audio_platform_info.xml` / `audio_platform_info_i2s.xml` 均未为
`SND_DEVICE_OUT_HIFI_HEADPHONES` 声明 `acdb_id`；MIUI 原厂即以"device 34 缺少 ACDB ID"告警运行。

**处置四条**：

1. **建模为常量而非异常**：在 `platform.c` 的 `acdb_device_table[]` 中为新枚举填入显式常量
   `ACDB_ID_NONE`（值 0 或 -1，取该 HAL 分支既有约定），并在同行加注释说明这是原厂行为。
2. **状态里单列一位**：`evidence bitmap` 中 E10' 有独立位，取值三态 `OK / ABSENT_EXPECTED / ERROR`。
   `ABSENT_EXPECTED` **不降级**，`ERROR`（loader 报错、linker/SELinux denial）降级为 `HIFI_DEGRADED`。
3. **维护页显式呈现**：显示为「ACDB：无该设备条目（原厂一致）」，而不是空白或"失败"。
   普通 Leo Home 完全不呈现此项。
4. **写入禁令**：在补丁与文档中双重标注——**禁止**为 `hifi-headphones` 借用 `headphones`(ACDB 10) 或任何
   其他设备的 ACDB ID。借用会把为 WCD 模拟链标定的 EQ/增益/限幅套到 ESS 数字链上，属于"为了让状态变绿而
   引入不可听觉验证的滤波器"，是本项目明确禁止的行为。

### 8.5 回退

统一回退动作（任何致命失败）：

```text
1. 停止后续所有 mixer 写入（不重试到超时）
2. 逆序撤销本 generation 已写控件：QUAT 后端 cfg → 路由 → Volume 回 205
3. select_devices() 切回 SND_DEVICE_OUT_HEADPHONES
4. generation += 1，effective_mode = ERROR_FALLBACK，记录 fail_code 与首个失败的证据位
5. 不自动重试；下一次 select_devices 才允许重新 ARMING
```

---

## 9. 第一版最小补丁清单与"不使用跨版本数字枚举"的实现方式

### 9.1 补丁文件与函数

目标：MoKee `hardware/qcom/audio`，**32-bit** `audio.primary.msm8994.so`
（对照基线 `701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47`）

| # | 文件 | 函数 / 位置 | 改动 | 量级 |
| ---: | --- | --- | --- | ---: |
| P1 | `hal/msm8974/platform.h` | `enum { SND_DEVICE_OUT_* }` | 在 `SND_DEVICE_OUT_VOICE_SPEAKER_PROTECTED` **之后**、`SND_DEVICE_OUT_END` **之前**追加 `SND_DEVICE_OUT_LEO_HIFI_HEADPHONES`；同步 `SND_DEVICE_OUT_END` / `SND_DEVICE_IN_BEGIN` | ~5 |
| P2 | `hal/msm8974/platform.c` | `device_table[]` | 追加 `[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES] = "hifi-headphones"`（**指定初始化器**，见 §9.2） | 1 |
| P3 | `hal/msm8974/platform.c` | `acdb_device_table[]` | `[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES] = ACDB_ID_NONE` + 注释 | 1 |
| P4 | `hal/msm8974/platform.c` | `platform_init()` | 启动自检（§9.3）；读 `vendor.leo.audio.hifi.enable` / `.volume`；`leo_set_hifi_volume()` | ~40 |
| P5 | `hal/msm8974/platform.c` | **新增** `leo_set_hifi_volume()` | 写 `"Volume"` 2 元素数组 + 读回 + 钳位 + 步长限制 | ~50 |
| P6 | `hal/msm8974/platform.c` | **新增** `leo_set_hifi_backend()` | 写 `QUAT_MI2S BitWidth` / `SampleRate` 到目标枚举字符串 + 读回（M3-d） | ~50 |
| P7 | `hal/msm8974/platform.c` | `platform_get_output_snd_device()` | 有线耳机分支：`my_data->leo_hifi ? SND_DEVICE_OUT_LEO_HIFI_HEADPHONES : SND_DEVICE_OUT_HEADPHONES` | ~4 |
| P8 | `hal/msm8974/platform.c` | `platform_check_and_set_codec_backend_cfg()` | 挂入 `leo_set_hifi_backend()`；判据用 `is_offload_usecase()` 而非 `== 3` | ~25 |
| P9 | `hal/msm8974/platform.c` | `platform_set_parameters()` | 新键 `leo_hifi_mode` / `leo_hifi_volume`；变更时遍历 `usecase_list` 调 `select_devices()` | ~45 |
| P10 | `hal/msm8974/platform.c` | `platform_get_parameters()` | 新键 `leo_hifi_status`（结构化只读快照） | ~45 |
| P11 | `hal/msm8974/platform.c` | **新增** `leo_hifi_check_bypass()` | E5a/E5b/E5c 三联断言 | ~45 |
| P12 | `hal/audio_hw.c` | `enable_audio_route()` / `disable_audio_route()` / `select_devices()` | 状态机钩子：ARMING/ACTIVE/DEGRADED/FALLBACK、generation、evidence bitmap | ~130 |
| P13 | `device/xiaomi/leo/` | `property_contexts` + SELinux te | `vendor.leo.audio.*` 类型与 allow 规则（M5 才关键） | ~15 |

合计约 **456 行**，13 处，**不触碰** kernel、DTB、任何 XML、audioserver、AudioFlinger、AudioPolicyManager、ACDB 库、Dirac。

### 9.2 不使用跨版本数字枚举的强制约定

风险来源（第一轮 §11 风险 1，本轮再次确认）：

```text
MIUI  : headphones = 6,  hifi-headphones = 34
MoKee : line       = 6,  headphones      = 7,  34 = speaker-protected
```

**四条硬约定**：

1. **补丁中零裸数字**。所有 snd_device 一律用符号名；新增枚举的数值由编译器决定，**任何文档、日志、
   测试断言、TSV 都不得记录其数值**——只记录名字 `SND_DEVICE_OUT_LEO_HIFI_HEADPHONES` 与 `"hifi-headphones"`。
2. **表用指定初始化器**（designated initializer）：

   ```c
   static const char * const device_table[SND_DEVICE_MAX] = {
       [SND_DEVICE_NONE]                        = "none",
       ...
       [SND_DEVICE_OUT_LEO_HIFI_HEADPHONES]     = "hifi-headphones",
   };
   ```

   这样即使上游在枚举中间插入设备，表项也不会错位。若当前分支使用的是顺序初始化器，**先把它改成指定
   初始化器**，这一步本身是可回归验证的机械变更。
3. **编译期断言**：

   ```c
   _Static_assert(SND_DEVICE_OUT_LEO_HIFI_HEADPHONES < SND_DEVICE_OUT_END,
                  "leo hifi device must stay inside OUT range");
   _Static_assert(SND_DEVICE_OUT_END <= SND_DEVICE_IN_BEGIN,
                  "OUT/IN boundary broken");
   ```
4. **运行期启动自检**（`platform_init` 内，早于任何路由）：

   ```c
   if (strcmp(device_table[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES], "hifi-headphones") != 0) {
       ALOGE("leo: device_table mismatch, HiFi permanently disabled this boot");
       my_data->leo_hifi_supported = false;      /* 本次 boot 不再尝试 HiFi */
   }
   ```

   自检失败**不是**降级，而是本次启动彻底禁用 HiFi——因为表错位意味着我们不知道会写到哪个设备。

同样约定适用于 usecase：判据写 `is_offload_usecase(uc->id)`，不写 `uc->id == 3`（§3.3）。

### 9.3 mixer 控件名的处理

所有控件名（`"Volume"`、`"QUAT_MI2S SampleRate"`、`"SLIMBUS_0_RX Audio Mixer MultiMedia%d"`、
`"HPHL DAC Switch"`、`"SLIM RX%d MUX"`）集中为一张 `static const char *` 表，
`platform_init` 时逐项 `mixer_get_ctl_by_name()` 预解析并缓存指针；任一解析失败即
`leo_hifi_supported = false`。这样"控件不存在"在启动时就被发现，而不是在播放中途。

---

## 10. 证据等级表

### 10.1 事实（本轮可复现，全离线）

| ID | 事实 | 复现 |
| --- | --- | --- |
| G1 | `platform_check_hifi_backend_cfg` 在 `usecase->id != 3` 时返回 0 且不写出参 | `objdump -d --start-address=0x179fc --stop-address=0x17a24` |
| G2 | 该符号无 PLT 桩、无 BL，零调用者 | 全量反汇编 grep + BL 扫描 |
| G3 | 活路径为 `platform_check_and_set_codec_backend_cfg`（`0x17ec4`），由 `select_devices`（`0x7048+0x4d4`）调用 | PLT `0x59f4` 的 BL 扫描 |
| G4 | HiFi 后端判据为 `id == 3` 严格相等，`offload2..9` 不覆盖 | `0x1807c: cmp r0,#3` |
| G5 | `QUAT_MI2S SampleRate` 的唯一写入点是 `platform_set_hifi_backend_cfg`，唯一调用点 `0x18050`，无 teardown 复位 | BL 扫描 |
| G6 | MoKee `audio_policy_configuration.xml` 不含 `hifi` | `grep -in hifi` |
| G7 | `mixer_paths.xml:410` `<ctl name="Volume" value="205" />` 位于 `<!-- HIFI -->` 顶层默认块；MoKee 与 stock 逐字节相同 | `sed -n '405,415p'` + SHA-256 |
| G8 | MoKee 内核 ES9018 `snd_kcontrol_new` 数组共 17 项，与实机 tinymix 897–913 一一对应 | 内核映像结构解析（§4.1） |
| G9 | `Volume`：`min=0 max=255 reg=15 rreg=16 shift=0 rshift=0 invert=1` | `soc_mixer_control` @`0xffffffc001d45ff8` |
| G10 | `Volume` TLV = `DB_SCALE(min=-127.50 dB, step=0.50 dB)`，access=0x13 | tlv @`0xffffffc0011452e8` |
| G11 | 由 G9+G10：控件值越大越响；205 = −25.0 dB，225 = −15.0 dB | 计算 |
| G12 | `.note.android.ident` API level：stock=24，MoKee=29 | `objdump -s -j .note.android.ident` |
| G13 | MoKee HAL 已 strip `.comment`，无编译器指纹，无源码路径字符串 | `objdump -s -j .comment` / `strings` |
| G14 | 实机存在 `SLIMBUS_0_RX Audio Mixer MultiMedia1..16`（641–656）、`HPHL DAC Switch`（806，声卡内唯一）、`SLIM RX1/RX2 MUX`（814/813） | `tinymix-B-state.txt` |
| G15 | 反证态下 `SLIMBUS_0_RX Audio Mixer MultiMedia5 = On` 而 `HPHL DAC Switch = Off`、`SLIM RX1/2 MUX = ZERO` | `16-falsification.txt` |

### 10.2 高可信推断

| ID | 推断 | 依据 | 证伪 |
| --- | --- | --- | --- |
| I1 | 设备上运行的 32-bit HAL 即 `701019bd…` | 同一镜像、只读挂载、OTA 未覆盖该路径 | 设备端 `sha256sum` |
| I2 | ES9018 `Volume` 与 Android 软件音量串联叠加 | deep-buffer 无 per-stream mixer 音量控件；`Compress Playback N Volume` 仅服务 offload | 改 Android 音量后读回 `Volume` 应不变 |
| I3 | 10–12 dB 的差值足以解释响度缺口，且为主导因素 | G11 + 其他增益级已排除 | A7 SPL 对照 |
| I4 | `audio_route_init` 在 HAL 启动时下发 `<!-- HIFI -->` 默认块，故 MoKee 主动把 `Volume` 置为 205 | tinyalsa `audio_route` 语义 + 实机值与 XML 一致 | 启动早期 tinymix 快照 |

### 10.3 未知

| ID | 未知 | 影响 |
| --- | --- | --- |
| N1 | MoKee HAL 的确切上游 commit | M3-0 的对照基线；不阻塞设计 |
| N2 | DIRECT PCM 在 MoKee HAL 中是否映射到 offload usecase 族 | **否决 M3.5**（前置 P3） |
| N3 | Android 10 上如何让播放器可靠拿到 DIRECT 44.1 输出 | 同上 |
| N4 | 44.1 kHz 下 LPASS slave 固定 3.072 MHz IBIT 参数的实际行为 | M3.5 首要观察项 |
| N5 | `hifi_volume` 记录值 30 vs 40（争议 D-1） | 目标差值 10.0 dB 还是 12.0 dB |
| N6 | 是否存在第二个较小的响度差异源（ACDB 缺失导致的 AFE 增益差 / Dirac 差异） | A7 的残差 |
| N7 | MIUI 中 `hifi_volume` 的 framework 调用者 | 仅影响"framework 零改动"结论的完备性 |

---

## 11. GO / NO-GO

### 11.1 编译前 GO（开始 M3-0 构建之前）

1. `docs/17` 已按第一轮 §9 + 本轮 §8 修订并冻结（证据门 E1–E10'、旁路三联断言、ACDB 三态）；
2. 争议 D-1（N5）已澄清，或明确记录为"两值均不得写入默认配置"；
3. agy 的 `702f7e8` 中 §12 列出的三处事实性错误已在其分支更正，或由项目主代理书面标注为"已知错误、不作为输入"；
4. Linux 构建主机就绪，同步 `hardware/qcom/audio` + `device/xiaomi/leo` 后可用空间仍 ≥ 6 GiB；
5. 已确认目标分支的 `device_table[]` / `acdb_device_table[]` 使用（或可改为）指定初始化器；
6. 本文 G1–G15 中至少 G1、G4、G5、G9、G10、G14 六条已由项目主代理独立复核。

**NO-GO**：任一不成立。特别是第 3 条——如果带着"删掉 48000 硬编码"的错误认知去写补丁，会先浪费一轮构建。

### 11.2 首次真机实验前 GO（M3-A 已在设备上、准备打开 M3-B 路由之前）

1. M3-0 的**无修改**构建产物已与 `701019bd…` 完成符号级对照，差异逐项可解释；
2. 设备端 `sha256sum` 已确认运行中的 HAL 即对照基线（采集请求 R5 完成，I1 升格为事实）；
3. M3-A（只读状态机，不改路由）在设备上运行，音频行为与原版 MoKee 逐项一致（至少 A1、A4、A9、A17）；
4. `leo_hifi_status` 可读出完整 evidence bitmap，且 **E5a/E5b/E5c 三联断言在原版 MoKee 正常耳机态下能正确报告"旁路存在"**
   （即：在标准 headphones 路径下，E5a 必须报告 `SLIMBUS_0_RX ← MM1 = On`）——这是断言逻辑本身的正向验证；
5. 音量写入代码已就位但**默认不启用**（`leo_hifi_volume` 缺省行为 = 不写 `Volume`），
   确保 M3-B 只引入路由这一个变量；
6. 回滚材料双份可读、recovery/fastboot 救援入口已实测（沿用 `docs/18` M2 前置门）；
7. 设备所有者当场明确授权。

**NO-GO**：符号对照有无法解释的差异；或 M3-A 出现任何与原版不一致的音频行为；
或第 4 条的正向验证失败（说明断言写错了，此时打开路由等于盲飞）；或回滚材料未闭合。

### 11.3 全局 NO-GO（沿用第一轮 §12.5，新增两条）

* 补丁中出现任何 snd_device 或 usecase 的裸数字；
* 为 `hifi-headphones` 借用其他设备的 ACDB ID。

---

## 12. agy 修正后仍存在的错误

按严重度排序。前三条会直接导致错误的工程决策。

| # | 位置 | 错误 | 正确表述 | 严重度 |
| ---: | --- | --- | --- | --- |
| **A1** | `AGY-CORRECTION-NOTES.md` §2；`AGY-MSM8994-HIFI-EVIDENCE.md` §5「分支 A」、§7、§8 评级表（标"已证明"）、§9.2；`agy-samplerate-evidence.tsv` SR-01 | 「`usecase->id != 3` 时函数**主动**写入 `0xbb80`(48000)/`16` 并更新缓存」 | `id != 3` 时 `bne` 跳向 `return 0`，**不写任何值**。48000/16 只用于通话/VoIP 分支与 `stream.out == NULL` 兜底 | **高**：由此推出的"删除硬编码"补丁是空操作 |
| **A2** | 全文以 `platform_check_hifi_backend_cfg` 为修复目标 | 该符号导出但**零调用者** | 活路径是 `platform_check_and_set_codec_backend_cfg`，由 `select_devices` 调用 | **高**：补丁打在死代码上 |
| **A3** | `AGY-MSM8994-HIFI-EVIDENCE.md` §3「根因」 | 「MoKee 的 `audio_policy_configuration.xml` 包含 `hifi-headphones`」 | `grep -in hifi` 对该文件**无匹配**；只有 `mixer_paths.xml` 含 hifi 路径 | **中**：会让人误以为 policy 层已就绪 |
| **A4** | `agy-hal-evidence.tsv` HAL-04；`agy-samplerate-evidence.tsv` SR-04 / SR-05 | 把未验证的 LineageOS commit `e20a6987…` 填进 `commit_or_sha256` 且 confidence=High，而正文自称"结构类比" | 字段应为 `N/A`，confidence 应为 `Inference`；且与项目 M2 记录的 `7f4cac74…` 冲突，二者均未闭合 | **中**：会把外部未验证 commit 固化为项目证据 |
| **A5** | `AGY-MSM8994-HIFI-EVIDENCE.md` §9.2 / 核心结论 6 | 「强制 Apple Music 等应用走 `USECASE_AUDIO_PLAYBACK_OFFLOAD`（即 Direct 模式）」 | compress-offload 与 direct PCM 是两回事；应用侧解码后的 PCM 流无法被强制进 compress-offload。且与其自身 SR-05「Direct PCM 映射未知」矛盾 | **中** |
| **A6** | `AGY-MSM8994-HIFI-EVIDENCE.md` §5「Compress Offload：这是确定的无损通道」 | 压缩流由 DSP 解码，**采样率**不被重采样，但"无损"与编码格式的有损性是两件事 | 应表述为"无 SRC 通道"，不是"无损通道" | 低（措辞） |
| **A7** | `agy-hal-evidence.tsv` HAL-05 `next_test`「increase 205 to 206 and measure」 | 单步 = 0.5 dB，远低于主观可辨阈；且该问题现已离线闭合 | 该行应改为 `Resolved: kernel snd_kcontrol_new + soc_mixer_control + TLV` | 低 |
| **A8** | 方法论 | 因 MiCode 仓库无 `es9018.c` 源码而把 `Volume` 语义整体判为"未知"，未尝试从项目**已持有**的 MoKee 内核映像中提取 | 该映像内含完整 kcontrol 元数据，min/max/invert/TLV 全部可离线读出（§4） | 中（不是错误，是漏掉的可行路径，代价是多一轮实机往返） |

**agy 修正正确、应予采纳的部分**：
`Volume = 205` 出自 `mixer_paths.xml`（更正了我第一轮的归因）；
把"绕过软件音量"降级为"待验证"（方向正确）；
把 64-bit 哈希改为 32-bit（与实机一致）；
明确区分 mixed/deep-buffer 与 offload 的前端重采样风险（与我第一轮 §5.1 一致）。

---

## 13. 仍需项目主代理执行的最小采集请求

全部为只读或一次性可逆写；均不需要写分区、不需要 recovery、不需要重启到 fastboot。

| # | 目标 | 动作 | 风险 | 预期证据 | 状态变化 |
| ---: | --- | --- | ---: | --- | --- |
| **R4** | 澄清争议 D-1 | 核对两次采集来源与时间戳，确定 `persist.audio.hifi.volume` 是 30 还是 40 | 无 | 单一可信值 | N5 → 事实；目标差值定为 10.0 或 12.0 dB |
| **R5** | 闭合 HAL 哈希最后一环 | 设备只读 `sha256sum /vendor/lib/hw/audio.primary.msm8994.so` | 无 | 与 `701019bd…` 比对 | I1 → 事实 |
| **R6** | 验证叠加关系 | 播放中改变 Android 音量若干刻度，每次 `tinymix` 读回 `Volume` | 无 | `Volume` 恒为 205 | I2 → 事实 |
| **R7** | 验证音量方向与量级 | 在已建立的临时 QUAT 路由下，把 `Volume` 从 205 依次写为 213 / 225，每步读回并记录主观响度（可选 SPL），完成后写回 205 | 低（起点即当前值，终点 −15 dB 仍低于 0 dB 22 dB） | 单调变响；225 与 MIUI 主观相当 | G11 → 实机确认；I3 → 事实 |
| **R8** | 采集 usecase 归属（为 M3.5 前置 P3 铺路） | 播放时 `dumpsys media.audio_flinger` + `/proc/asound/card0/pcm*p/sub0/hw_params`，分别记录 deep-buffer 与一次 DIRECT 尝试 | 无 | 输出线程类型与前端 hw_params | N2/N3 部分收敛 |
| **R9** | 记录启动早期 `Volume` | 冷启动后尽早 `tinymix` 读 `Volume` 与 `Automute Level` | 无 | 若为 205/120 即 XML 默认块已下发 | I4 → 事实 |

R7 的顺序很重要：**必须先做 R6**（确认 Android 音量不改 `Volume`），否则 R7 的主观对比会被两个变量污染。

---

## 14. 本轮验证记录

* 以只读方式审查 `702f7e8` 的全部四个文件（`git show`），未 cherry-pick、未修改 agy 工作树、未合并；
* 对 `platform_check_hifi_backend_cfg`（`0x17948`）、`platform_check_and_set_codec_backend_cfg`（`0x17ec4`）
  重新逐指令核对分支方向，并用 PLT 表与 BL 全量扫描确认调用关系；
* 从 `kernel-image.bin` 解出内核虚拟基址 `0xffffffc000080000`，枚举 ES9018 `snd_kcontrol_new` 数组 17 项，
  读出 `Volume` 的 `soc_mixer_control` 与 TLV，并用 `Automute Level`、`THD Compensation` 两项交叉校验结构解读；
* 核对 `mixer_paths.xml` 第 405–415 行的 `<!-- HIFI -->` 默认块，确认 MoKee 与 stock 逐字节相同；
* 核对 M2 归档 `tinymix-B-state.txt`、`13-ABA-test.txt`、`16-falsification.txt` 中与旁路断言相关的全部控件；
* 本轮未执行 `adb`/`fastboot`/`heimdall`，未连接设备，未写任何分区，未修改主工作树与 agy 工作树，
  未把任何专有二进制复制进 Git，未推送、未合并；
* 第一轮报告 `805989e` 保持原样，未 amend。

### 附：本轮新增复现命令

```bash
cd /Users/km/Desktop/Leo-Audio-OS
S=resources/private/stock-system-tree/lib/hw/audio.primary.msm8994.so

# G1 控制流
/usr/bin/objdump -d --start-address=0x179fc --stop-address=0x17a24 "$S"
# G2/G3 调用关系
/usr/bin/objdump -d "$S" | grep -E "(hifi|check_and_set_codec_backend_cfg).*@plt>:"
# G6/G7 XML
grep -in hifi   resources/private/phase5b-mokee/selected/system/vendor/etc/audio_policy_configuration.xml
sed -n '405,415p' resources/private/phase5b-mokee/selected/system/vendor/etc/mixer_paths.xml
# G14/G15 实机控件
grep -E "SLIMBUS_0_RX Audio Mixer MultiMedia|HPHL DAC Switch|SLIM RX[12] MUX" \
     resources/private/phase5b-mokee/m2-runtime-20260828/tinymix-B-state.txt
```

`Volume` 的内核元数据提取需要一段脚本：以 `BASE = 0xffffffc000080000` 建立 `VA = BASE + 文件偏移` 映射，
在映像中搜索 ES9018 控件名字符串的绝对指针，按 `snd_kcontrol_new`（arm64，80 字节，`name` 在 `+16`，
`tlv` 在 `+64`，`private_value` 在 `+72`）枚举数组，再解 `private_value` 指向的 32 字节
`soc_mixer_control`（`min, max, platform_max, reg, rreg, shift, rshift, invert`，全为 u32）
与 `tlv.p` 指向的 `{type, len, min_dB×100, step_dB×100}`。
