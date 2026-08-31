# 19：Phase 5B M3 Leo HiFi Controller 工程合同

> 状态：**工程合同（冻结草案）**。本文把 `94d0370` 的第二轮裁决转化为可执行契约。
> 本文**不授权**向设备写入任何分区、不授权连接设备、不授权修改 mixer。
> 当前设备状态：`system` 已写入 MoKee M2 候选；`boot` 仅以 `fastboot boot` 临时启动，
> **未持久写入**；HiFi 仅由一次性运行时 mixer 写入建立，重启即消失。
>
> **[2026-08-29 状态更新 · 上一行已过期]**
> `boot` **已持久写入 boot 分区**。分区前 `23928832` 字节回读 SHA-256 为
> `9470dd6a01120480289c17d0da161e73b2eb6361ece3ea72041b07da088934af`，与候选完全一致。
> `misc` 中残留的 BCB 曾导致 recovery 循环，已按既有文档清除并恢复正常启动。
> 因此 §14 中「不能依赖重启恢复」的理由消失：**重启现在是可用的恢复手段**，
> 但仍不是首选（它丢弃现场证据）。§13.2 的写入前 GO 第 2 条随之关闭。

日期：2026-08-29
上游裁决：[`docs/research/CLAUDE-OPUS5-HIFI-CONTROLLER-ARCHITECTURE.md`](research/CLAUDE-OPUS5-HIFI-CONTROLLER-ARCHITECTURE.md)（`805989e`）、
[`docs/research/M3-HIFI-ARCHITECTURE-RULING-DRAFT.md`](research/M3-HIFI-ARCHITECTURE-RULING-DRAFT.md)（`94d0370`）
源码谱系：[`docs/research/M3-SOURCE-PROVENANCE.md`](research/M3-SOURCE-PROVENANCE.md)

---

## 1. 目的、范围与非目标

### 1.1 目的

让 MoKee Android 10 在有线耳机播放时**自动、可读回、可回退地**进入
`QUAT_MI2S → ES9018K2M → OPA1612` 通路，并提供与普通耳机相互独立的 HiFi 音量状态；
所有状态只有一个写入者，界面只读。

### 1.2 M3 范围（十条，全部必须实现）

| # | 条目 |
| ---: | --- |
| M3-1 | MoKee 自动选择 `hifi-headphones` / ESS 路由 |
| M3-2 | Leo HiFi Controller 是**唯一**状态写入者 |
| M3-3 | 独立 HiFi 音量模型（ES9018 `Volume` kcontrol） |
| M3-4 | **每次进入和退出 HiFi 都确定性设置并读回** `QUAT_MI2S SampleRate = KHZ_48`、`QUAT_MI2S BitWidth = S24_LE` |
| M3-5 | 检测 `MultiMedia<N> → SLIMBUS_0_RX` 等 WCD 旁路 |
| M3-6 | `hifi-headphones` 无 ACDB ID 是原厂已知状态；**不借用**其他设备的 ACDB ID |
| M3-7 | 暂停、切歌、拔线、HAL 重启与各类失败下的安全回退 |
| M3-8 | UI / 维护页只读，不得直接写 mixer |
| M3-9 | 所有跨版本设备枚举按**符号与表结构**重建，禁止复制 MIUI 数值 `34` |
| M3-10 | 在 R6/R7 完成之前，**不把 213 / 225 / 229 中任一值设为产品默认** |

### 1.3 M3 非目标（明确不做）

* 44.1 kHz bit-perfect（归 M3.5）；
* 强制 DIRECT / offload 通路；
* framework 大规模修改；
* kernel / DTB 修改；
* GApps、播放器、界面扩展；
* 系统精简（归 M4）。

### 1.4 M3.5 边界

M3.5 单独处理 SRC。**在 N2（DIRECT PCM 是否映射到 offload usecase 族）闭合之前，
不得对 Apple Music 或任何第三方播放器声称存在用户可达的 44.1 kHz 无 SRC 通路。**
M3.5 的完整前置条件见 `M3-HIFI-ARCHITECTURE-RULING-DRAFT.md` §7.2（P1–P7），其中 P3 为否决性。

### 1.5 F-19（error -5）对 M3 的强制约束

实机已证明：**播放开始之后再改 mixer 是不可行的**——HAL 会在约 10.5–11.6 s 内
把路由改回 SLIMBUS/WCD，同时把手工写下的 QUAT 留在 On 上。因此：

1. **路由必须在流第一次 `start_output_stream()` 时就确定。**
   `select_devices()`（`audio_hw.c:1766`）在 `pcm_open()`（`:1778`）之前执行，
   而设备选择发生在 `select_devices()` 内最早的 `platform_get_output_snd_device()`。
   M3 的判定点必须且只能在那里。
2. **必须应用完整的 `deep-buffer-playback hifi-headphones` 路径**，而不是单点翻转
   `QUAT_MI2S_RX Audio Mixer MultiMedia1`。路径由
   `use_case_table[id]` + `" "` + `backend_tag_table[snd_device]` 组成，
   因此 `backend_tag_table[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES] = "hifi-headphones"` 是必需项。
3. **`docs/19` §15 中「init.rc 或常驻 `tinymix` 脚本」一条现在有实机反证**，
   不再只是"违反单写入者原则"的原则性禁令。

---

## 2. 事实、推断与未知

### 2.1 已证明事实（本项目可离线复现）

| ID | 事实 | 证据位置 |
| --- | --- | --- |
| F-1 | MoKee 32-bit HAL `701019bd…` 完全不含 HiFi 逻辑（无符号、无字符串、无 QUAT 控件名） | `objdump -T` / `grep -rail hifi` |
| F-2 | MIUI 的设备选择是单一布尔量 `my_data->hifi`，`true → 34 (hifi-headphones)`，`false → 6 (headphones)` | stock HAL `0x145dc–0x14614` |
| F-3 | MIUI 独立音量 = `set_hifi_volume()` 向 ALSA kcontrol `"Volume"` 写 2 元素数组，值 `= ⌊v×0.4⌋ + 213`，`v∈[0,100]` | stock HAL `0x12de8` |
| F-4 | `Volume` 属 ES9018 codec：`min=0 max=255 reg=15 rreg=16 shift=0 rshift=0 invert=1` | MoKee 内核映像 `soc_mixer_control @0xffffffc001d45ff8` |
| F-5 | `Volume` 的 TLV = `DB_SCALE(min = −127.50 dB, step = 0.50 dB)`；`access = 0x13`（含 TLV_READ） | 内核映像 `tlv @0xffffffc0011452e8` |
| F-6 | 由 F-4 + F-5：`dB = −127.50 + 0.50 × 控件值`，**控件值越大越响**；205 = −25.0 dB，213 = −21.0 dB，225 = −15.0 dB，229 = −13.0 dB，253 = −1.0 dB | 计算 |
| F-7 | `mixer_paths.xml:410` 的 `<!-- HIFI -->` **顶层默认块**把 `Volume` 初始化为 205；MoKee 与 stock 该文件逐字节相同（`13db0e6e…`） | 直接读文件 |
| F-8 | `platform_check_hifi_backend_cfg` 在 `usecase->id != 3` 时**直接返回 0，不写任何值**；且该符号**零调用者** | stock HAL `0x179fc–0x17a08`；无 PLT 桩 |
| F-9 | HiFi 后端的活路径是 `platform_check_and_set_codec_backend_cfg`，判据 `id == 3` **严格相等**（`offload2..9` 不覆盖） | stock HAL `0x1807c` |
| F-10 | `QUAT_MI2S SampleRate` 全 `.so` 只有一个写入点，**无 teardown 复位** → 存在陈旧速率风险 | BL 全量扫描 |
| F-11 | MoKee snd_device 枚举与 MIUI **不同**：MoKee `line=6, headphones=7`，OUT 段止于 35；`34 = speaker-protected` | 两份 `device_table` |
| F-12 | MoKee `audio_policy_configuration.xml` **不含** `hifi`；只有 `mixer_paths.xml` 含五条 hifi 路径 | `grep -in hifi` |
| F-13 | `hifi-headphones` 在 stock 与 MoKee 的 `audio_platform_info*.xml` 中**均无 `acdb_id`** | 直接读文件 |
| F-14 | 实机存在 `SLIMBUS_0_RX Audio Mixer MultiMedia1..16`（控件 641–656）、`HPHL DAC Switch`（806，声卡内唯一同名控件）、`SLIM RX1/RX2 MUX`（814/813） | M2 `tinymix-B-state.txt` |
| F-15 | 反证态下 `SLIMBUS_0_RX Audio Mixer MultiMedia5 = On` 可与 QUAT 并存 → 旁路真实存在 | M2 `16-falsification.txt` |
| **F-16** | **MoKee 的 msm8994 音频 HAL 源码基线 = `MoKee/android_hardware_qcom_audio` 分支 `mkq-mr1-caf-msm8994`，HEAD `7f4cac748b6f62897294cdaece9d1aec27e1e927`（2020-01-14）**，由 `MoKee/android` @ `mkq-mr1` 的 `snippets/mokee.xml` 显式 pin，且其 `device_table` / snd_device 枚举与二进制**逐项完全一致** | 见 `M3-SOURCE-PROVENANCE.md` |
| **F-19** | **包外手工改 mixer 会被 HAL 自动撤销。** 在 AudioFlinger deep-buffer 流播放期间手动打开 QUAT、切断 WCD 后，HAL 每约 10.5–11.6 s 出现 `out_write: error -5 - cannot write stream data: I/O error`，随后 `out_standby` → `disable deep-buffer-playback/headphones` → `start_output_stream` → `select_devices(out_snd_device 7: headphones)` → `enable_audio_route(deep-buffer-playback)`，即恢复 SLIMBUS/WCD，而手工写下的 QUAT 仍可能保持 On，形成潜在双通路 | 2026-08-29 实机；源码机制见下 |
| **F-20** | 该现象的源码路径：`out_write` 的 `pcm_write` 失败 → `audio_hw.c:2488` 打印 → `:2495 out_standby()` → `:2496 usleep(一个 buffer 周期)`；下一次写入触发 `start_output_stream()`，其中 `select_devices()` 在 `:1766`、`pcm_open()` 在 `:1778` | `7f4cac74` 源码 |
| **F-21** | 整棵 `hardware/qcom-caf/msm8994/audio` @ `7f4cac74` 中**没有任何代码写 `QUAT_MI2S` 控件**（`grep -rn QUAT_MI2S` 零命中），也没有 teardown 复位 | 本轮 grep |
| **F-22** | `select_devices()` 在 `usecase->out_snd_device = out_snd_device`（`:1099`）**之前**就调用了 `check_and_route_playback_usecases()`（`:1079`）→ `platform_check_and_set_codec_backend_cfg()`（`:744`）。在那里读 `usecase->out_snd_device` 得到的是**上一个**设备 | `7f4cac74` 源码 |
| **F-23** | `platform_check_backends_match()` 用 `hw_interface_table` 的互相 `strstr` 比较。`"QUAT_MI2S_RX"` 与 `"SLIMBUS_0_RX"` 互不含子串 → 判为不同后端 → `check_and_route_playback_usecases()` **不会**把 SLIMBUS usecase 迁到 ESS，它们保持 `headphones` 路径，`HPHL DAC Switch` 保持为 1 | `platform.c` 源码 |

### 2.2 高可信推断

| ID | 推断 | 证伪方式 |
| --- | --- | --- |
| I-1 | 设备上运行的 32-bit HAL 即 `701019bd…` | 设备只读 `sha256sum`（R5） |
| I-2 | ES9018 `Volume` 与 Android 软件音量**串联叠加**（deep-buffer 无 per-stream mixer 音量控件） | R6 |
| I-3 | `Volume=205` 造成的 10.0–12.0 dB 缺口足以解释响度差，且为主导因素 | R7 + A7 |
| I-4 | `audio_route_init` 在 HAL 启动时下发 `<!-- HIFI -->` 默认块 | R9 |

> **[2026-08-29 升格 · R6 与 R7-A 已在实机通过]**
>
> * **I-2 → 事实（F-17）**：R6 通过。Android `STREAM_MUSIC` 依次取 2 / 6 / 10 / 14 / 18
>   （范围 0..25）时，ES9018 `Volume` 恒为 `205 205`，QUAT 路由与 PCM 稳定，
>   用户确认响度单调变化。**Android 软件音量与 ESS `Volume` 是相互独立的串联增益。**
> * **I-3 → 部分事实（F-18）**：R7-A 通过。为避免 HAL 抢路由，停止 Phonograph 后改用
>   同机原厂 64-bit `tinyplay` 直接打开 PCM0/MultiMedia1（48 kHz、S16_LE 前端，
>   QUAT backend `S24_LE`/`KHZ_48`，`HPHL DAC Off`、`SLIM RX1/RX2 ZERO`、`QUAT MM1 On`）。
>   `205 → 213` 精确读回并稳定 10 秒，用户确认**明确变响**且无爆音、失真、单边或断续；
>   随后已恢复 `205`。
>   → 控件方向与量级与内核 TLV 推导一致（`dB = -127.50 + 0.50 × v`，205 = −25.0 dB，
>   213 = −21.0 dB，差 +4.0 dB）。
> * **R7-B（`225`，−15.0 dB）尚未执行，不得记为通过。** I-3 的"10.0 dB 缺口足以解释响度差"
>   这一半仍是推断。
>
> **[2026-08-29 22:04 R7-B 第一次尝试：停在前置门，未写入]**
> 只读核验：设备唯一（`68f5f468`）、root 可用、`Volume: 205 205 (dsrange 0->255)`、
> Android `STREAM_MUSIC` headphone 档 = 2/25、耳机确已插入（阻抗 34282/34804，HPH Type 2）、
> 无遗留测试进程、无双通路。
> 但 `QUAT_MI2S_RX Audio Mixer MultiMedia1 = **Off**` 且**所有 PCM 均为 closed**——
> 路由未建立、无流在播。此时写 `225` 不会产生任何可听变化，只会得到假阴性。
> 另有一处约束冲突需用户裁决：本轮规定只允许改 `Volume`，
> 而建立 HiFi 路由必须写 `QUAT_MI2S_RX Audio Mixer MultiMedia1`。
> **全程只读，未写任何控件，设备状态未改变。** 详见
> `M3-R6-R7-RUNTIME-TEST-RUNBOOK.md` §7。
>
> **[2026-08-29 裁决 · 设备所有者]** R7-B **推迟到 M3-B 之后**执行：届时补丁后的 HAL
> 自行建立 HiFi 路由，执行者只写 `Volume`，与安全约束相容，也避开 F-19。
> 因此在 M3-B 之前：`LEO_HIFI_CTL_CEIL = 237` 保持暂定；M3-10 继续有效；
> M3-B 的验收矩阵新增一项"在 HAL 已建立路由的前提下完成 R7-B"。
>
> `audio_route_init` 的实际位置本轮已由源码确认：`platform.c:1212/1216`，即在
> `platform_init()` **内部**、`leo_hifi_init()`（`platform.c:1435`）之前。I-4 成立。

### 2.3 未知

| ID | 未知 | 阻断对象 |
| --- | --- | --- |
| N-2 | DIRECT PCM 在 MoKee HAL 中是否映射到 offload usecase 族 | **否决 M3.5** |
| N-3 | Android 10 上如何让播放器可靠拿到 DIRECT 44.1 输出 | M3.5 |
| N-4 | 44.1 kHz 下 LPASS slave 固定 3.072 MHz IBIT 参数的行为 | M3.5 |
| N-5 | `persist.audio.hifi.volume` 记录值 30 还是 40（争议 D-1） | 目标差值 10.0 或 12.0 dB |
| N-6 | 是否存在第二个较小的响度差异源 | A7 残差 |
| N-7 | MIUI 中 `hifi_volume` 的 framework 调用者 | 仅影响"framework 零改动"论证的完备性 |
| N-8 | 设备树 / vendor 是否对 HAL 打过本地补丁（F-16 的最后 1%） | M3-0 构建对照 |

---

## 3. 分层所有权

| 关注点 | 唯一写入者 | 只读观察者 | 禁止 |
| --- | --- | --- | --- |
| `requested_hifi_mode` | Leo Audio Policy Service → HAL `set_parameters` | Leo Home、维护页 | 普通 App、init 脚本 |
| 输出设备选择 | HAL `platform_get_output_snd_device()` | `get_parameters` | AudioPolicyManager 不参与 |
| ESS 供电/时钟/mute/OPA/模拟 switch | **kernel**（`es9018.c` + `msm8994.c`，随 QUAT MI2S DAI startup/shutdown） | HAL 读 sysfs | HAL 与用户态不得直接操作 |
| `QUAT_MI2S BitWidth` / `SampleRate` | HAL `leo_set_hifi_backend()` | 维护页读回 | App、init.rc、常驻 `tinymix` |
| ES9018 `Volume` | HAL `leo_set_hifi_volume()` | 维护页读回 | 普通 UI 不得暴露原始寄存器值 |
| HiFi 音量持久化 | HAL 写 `vendor.leo.audio.hifi.volume` | — | 不复用 `persist.audio.hifi.volume` |
| `effective_mode` / generation / fail_code | HAL，仅在读回成功后推进 | Status Service → UI | UI 不得从 `requested` 推断 `effective` |

**framework 不需要修改。** `platform_set_parameters()` / `platform_get_parameters()` 已是
`android.hardware.audio@2.0` 的标准通道，特权组件可直接调用。

---

## 4. 状态机、generation 与失败码

### 4.1 状态

| 状态 | 语义 | 普通界面 |
| --- | --- | --- |
| `IDLE` | 无活动输出流 | 就绪 |
| `SPEAKER` | 外放 | 外放 |
| `WIRED_STANDARD` | 有线耳机走 WCD9330 | 耳机 · 标准 |
| `HIFI_ARMING` | 正在建立 HiFi | HiFi · 正在连接 |
| `HIFI_ACTIVE` | 全部致命证据同 generation 闭合 | HiFi · 已激活 |
| `HIFI_DEGRADED` | 有声但非致命证据缺失 | 耳机 · 受限 |
| `ERROR_FALLBACK` | 已回退到 `headphones` | 耳机 · 安全回退 |

`generation` 单调递增，每次状态转换 +1。**同一 generation 内采集的证据才可用于判定。**
`requested_mode` 与 `effective_mode` 严格分离。

### 4.2 证据门

| # | 证据 | 等级 |
| ---: | --- | --- |
| E1 | AudioPolicy 输出设备 ∈ {WIRED_HEADSET, WIRED_HEADPHONE} | 致命 |
| E2 | `platform_get_output_snd_device()` 返回 `SND_DEVICE_OUT_LEO_HIFI_HEADPHONES` | 致命 |
| E3 | `/sys/bus/i2c/devices/6-0048/driver` → `es9018` | 致命 |
| E4 | `QUAT_MI2S_RX Audio Mixer MultiMedia<N>` 读回 = On（N = 本 usecase 的前端） | 致命 |
| E5 | **旁路三联断言**（§7） | 致命 |
| E6 | `QUAT_MI2S BitWidth` = `S24_LE` 且 `SampleRate` = `KHZ_48`，均为**读回值** | 致命 |
| E7 | `Volume` 读回 = 期望值且 ∈ [205, `LEO_HIFI_CTL_CEIL`] | 非致命 → DEGRADED |
| E8 | 活动 PCM_PLAYBACK 流 ≥ 1 且 `pcm_state` = RUNNING | 致命 |
| E9 | 本 generation 内无 mixer 写失败、无 linker / dlopen 错误 | 致命 |
| E10' | ACDB 查询结果 ∈ {`OK`, `ABSENT_EXPECTED`} | 非致命 |

> **[2026-08-29 修订 · 依据：M2 `16-falsification.txt` 与 F-23]**
>
> **E4 的判据具体化**：至少一个 `QUAT_MI2S_RX Audio Mixer MultiMedia1..16` 读回为 On。
> 理由：`mixer_paths.xml` 只为 deep-buffer / low-latency / audio-ull / compress-offload
> 四个 usecase 提供了 `<usecase> hifi-headphones` 路径。其他 usecase 会应用不到任何路径，
> 于是**静默出不了声**；E4 是唯一能捕获这种情况的证据位。
>
> **E5 从"三联全致命"改为"只有模拟出口致命"**。观测模型覆盖完整 WCD 链：
>
> ```text
> MultiMediaN -> SLIMBUS_0_RX -> SLIM RX1/RX2 MUX -> RX1/RX2 MIX1 INP1
>              -> CLASS_H_DSM MUX -> HPHL DAC Switch -> 耳机插孔
> ```
>
> | 观测位 | 控件 | 致命性 |
> | --- | --- | --- |
> | `LEO_BP_SLIM_FE` | `SLIMBUS_0_RX Audio Mixer MultiMedia1..16` | 记录 |
> | `LEO_BP_MUX_LIVE` | `SLIM RX1 MUX`、`SLIM RX2 MUX` | 记录 |
> | `LEO_BP_MIX_LIVE` | `RX1 MIX1 INP1`、`RX2 MIX1 INP1` | 记录 |
> | `LEO_BP_CLASSH` | `CLASS_H_DSM MUX`（**右声道 DAC 的实际闸门**） | 记录 |
> | `LEO_BP_OUTLET` | `HPHL DAC Switch` | **致命** |
>
> 依据：M2 反证态中 `SLIMBUS_0_RX ← MultiMedia5 = On` 而 `HPHL DAC Switch = Off`、
> `SLIM RX1/2 MUX = ZERO` 时**无声**。断开模拟出口即足以使 WCD 路径不可闻，
> 因此把"有前端在 SLIMBUS 上"本身判为致命是**过严**的。
>
> 本声卡只有一个 `HPHL DAC Switch`，**没有 `HPHR DAC Switch`**（M2 全量控件表已确认）；
> 右声道由 RX2 链与 `CLASS_H_DSM MUX` 门控，故两者纳入观测以覆盖左右声道。
>
> **正向验证要求（M3-A 的 GO 条件之一）**：在**原版标准耳机播放态**下，
> WCD 链全部活跃是正常的，状态机必须落到 `WIRED_STANDARD` 且不产生 `WCD_BYPASS`
> 失败码；控制器在 `to_hifi_device == false` 时根本不调用旁路检查。

耳机阻抗**不作为证据门**（M2 §7.1：QUAT 后端启动前无效）。

### 4.3 失败码

| code | 含义 | 目标状态 |
| ---: | --- | --- |
| 0 | 无 | — |
| 1 | `mixer_get_ctl_by_name` 失败（控件不存在） | `ERROR_FALLBACK` |
| 2 | mixer 写入返回错误 | `ERROR_FALLBACK` |
| 3 | 致命项写入成功但读回不一致 | `ERROR_FALLBACK` |
| 4 | 非致命项读回不一致（E7） | `HIFI_DEGRADED` |
| 5 | ES9018 未绑定 / sysfs 缺失 | `ERROR_FALLBACK`，本次 boot 永久禁用 HiFi |
| 6 | 检测到 WCD 旁路（E5 任一失败） | `ERROR_FALLBACK` |
| 7 | 后端速率协商失败 | `HIFI_DEGRADED` |
| 8 | 超时 | `ERROR_FALLBACK` |
| 9 | 音量请求越界 | 保持原状态，不降级 |
| 10 | 后端读回与目标不符（E6） | `ERROR_FALLBACK` |
| 11 | 活动 offload usecase 不在认可集合内 | `HIFI_DEGRADED` |
| 12 | `device_table` 自检失败（§9.2） | 本次 boot 永久禁用 HiFi |

---

## 5. 路由建立与撤销的精确顺序

### 5.1 建立（`WIRED_STANDARD` → `HIFI_ARMING` → `HIFI_ACTIVE`）

```text
前置：E3 成立；requested = HIFI；leo_hifi_supported == true
 1. generation += 1，effective = HIFI_ARMING，清空 evidence bitmap
 2. 写 ES9018 "Volume" = clamp(leo_hifi_volume)      ← 必须在路由之前
    立即读回；不一致 → code 4，置 E7 失败位（不中止）
 3. 写 QUAT_MI2S BitWidth = "S24_LE"；读回          ← M3-4，确定性
    写 QUAT_MI2S SampleRate = "KHZ_48"；读回
    任一读回不一致 → code 10 → 回退（§5.3）    ★ 该写入的挂载点是 enable_snd_device()，不是
      platform_check_and_set_codec_backend_cfg()。见下方修订。
 4. select_devices() → enable_audio_route()
       → audio_route_apply_and_update_path("<usecase> hifi-headphones")
 5. 读回 E4（QUAT_MI2S_RX Audio Mixer MultiMedia<N> == On）
 6. 执行旁路三联断言 E5a/E5b/E5c（§7）
 7. 读回 E6、E8；查询 ACDB → E10'
 8. 全部致命位成立 → effective = HIFI_ACTIVE
    否则按 §4.3 落到 DEGRADED 或 ERROR_FALLBACK
超时：整段 300 ms（覆盖 es9018 soft-start 150 ms 的裕量）
```

**顺序不可交换的三处**：
`Volume` 必须早于路由（此时 ESS 仍静音/未 soft-start，避免突发响度）；
后端 cfg 必须早于路由（速率变更只允许在 QUAT 引用计数为 0 时发生）；
旁路断言必须晚于路由（旁路是路由建立的副作用）。

> **[2026-08-29 修订 · 依据 F-22]** 进入侧后端写入的挂载点必须是
> `enable_snd_device()`（`audio_hw.c:637`），**不能**是
> `platform_check_and_set_codec_backend_cfg()`。
>
> `select_devices()` 的真实顺序是：
>
> ```text
> disable_audio_route(旧)                    :1058   ← 退出钩子在这里（usecase 仍持旧设备）
> disable_snd_device(旧)                     :1059
> check_and_route_playback_usecases(新)      :1079
>      └─ platform_check_and_set_codec_backend_cfg(uc_info)  :744
>         ★ uc_info->out_snd_device 此刻仍是【旧】设备
> enable_snd_device(新)                      :1080   ← 进入钩子在这里（第一次看到新设备）
> usecase->out_snd_device = 新               :1099
> enable_audio_route(新)                     :1113   ← QUAT DAI 在此启动
> ```
>
> 原草案在 `platform_check_and_set_codec_backend_cfg()` 里守卫
> `usecase->out_snd_device == SND_DEVICE_OUT_LEO_HIFI_HEADPHONES`，
> 读到的是上一个设备：**标准→HiFi 时永不触发，HiFi→标准时反而触发**。
> M3-4「进入侧确定性」会整条失效。已在补丁 0004 修正。
>
> 写入时机的正确性另有两条源码依据：
> `QUAT_MI2S BitWidth` / `SampleRate` 是声卡注册时就存在的静态 kcontrol（M2 实机在
> QUAT 全 Off 时仍可读到）；内核 machine driver 在 `hw_params` 时采样它们，
> 而 `hw_params` 由 `enable_audio_route()` 应用的 mixer path 触发。
> 所以必须在 `enable_audio_route()` **之前**写，且不需要后端先启动。

### 5.2 撤销（正常退出）

```text
 1. generation += 1
 2. disable_audio_route() → 撤销 hifi-headphones 路径
 3. 写 QUAT_MI2S SampleRate = "KHZ_48"；读回        ← M3-4，退出侧确定性恢复
    写 QUAT_MI2S BitWidth  = "S24_LE"；读回
    读回不一致 → 记录 code 10，但**不阻断**退出
 4. "Volume" 保持不变（只作用于 ESS 支路；下次进入必重设）
 5. effective = WIRED_STANDARD / SPEAKER / IDLE
```

第 3 步是 F-10 的直接对策：`QUAT_MI2S SampleRate` 没有任何上游 teardown 复位，
若不显式写回，一次非 48 kHz 会话会把控件永久留在错误值上。

### 5.3 失败回退（统一动作）

```text
 1. 停止后续所有 mixer 写入（不重试到超时）
 2. 逆序撤销本 generation 已写控件：
       后端 cfg → 路由 → "Volume" 写回 205 并读回
 3. select_devices() 切回 SND_DEVICE_OUT_HEADPHONES
 4. generation += 1；effective = ERROR_FALLBACK；记录 code 与首个失败的证据位
 5. 不自动重试；下一次 select_devices() 才允许重新 ARMING
```

**禁止**从 `ERROR_FALLBACK` 或 `HIFI_DEGRADED` 直接跳到 `HIFI_ACTIVE`；必须新起 generation 并重走 §5.1 全部读回。

### 5.4 各事件路径

| 事件 | 动作 | 终态 |
| --- | --- | --- |
| 插耳机、未播放 | **不做任何硬件动作**（`docs/04` §6：插入不启动 DAC） | `WIRED_STANDARD` |
| 首次播放 | §5.1 | `HIFI_ACTIVE` / DEGRADED / FALLBACK |
| 暂停 3 s | 不主动写；等 usecase 归零（AudioFlinger standby delay = 3 s） | `IDLE`（ESS 由内核有序下电） |
| 快速切歌（同参数） | **不做任何写入**，generation 不变 | `HIFI_ACTIVE` 保持 |
| 拔耳机 | 立即 `select_devices()`；**不写 `Volume`**；执行 §5.2 第 3 步 | `SPEAKER` / `IDLE` |
| 息屏 | 每 30 s 轻量巡检 E4 + E5 | 不变或降级 |
| 多流 | 不切换时钟家族；速率标注"混音 48 kHz" | `HIFI_ACTIVE` |
| HAL 崩溃重启 | `platform_init` 冷路径重建；generation 从 0 起 | 由自检决定 |
| audioserver 重启 | 同上 | 同上 |
| ESS 未 probe | 不发起任何 HiFi 尝试 | `WIRED_STANDARD`，code 5 |
| 重启后恢复 | `platform_init` 读 property → clamp → 写 `Volume` → 读回；**不主动建路由** | `IDLE` |

---

## 6. `Volume` 写入与读回规则

### 6.1 映射

```c
#define LEO_HIFI_CTL_NAME     "Volume"
#define LEO_HIFI_CTL_FLOOR    205   /* = mixer_paths.xml 默认，-25.0 dB，绝对下限 */
#define LEO_HIFI_CTL_BASE     213   /* v=0 → -21.0 dB（MIUI 曲线起点）           */
#define LEO_HIFI_CTL_CEIL     237   /* 第一版硬上限，-9.0 dB                      */
#define LEO_HIFI_VOL_MAX       60   /* 用户刻度上限                              */
/* ctl = LEO_HIFI_CTL_BASE + (v * 2) / 5      ⇒ dB = -21.0 + 0.2 * v */
```

### 6.2 规则

1. **R6/R7 完成前不自动提升**：第一版 `LEO_HIFI_APPLY_DEFAULT = 0`，即
   `platform_init` **不写** `Volume`，控件保持 `mixer_paths.xml` 的 205。
   213 / 225 / 229 中任何一个都**不得**成为产品默认（M3-10）。
2. 只有在收到显式 `leo_hifi_volume=<v>` 参数时才写入；写入前 clamp 到 `[0, LEO_HIFI_VOL_MAX]`，
   越界请求返回 code 9 并保持原值。
3. 计算出的控件值再次 clamp 到 `[LEO_HIFI_CTL_FLOOR, LEO_HIFI_CTL_CEIL]`。
4. **写后必读回**；不一致 → 写回 205 → code 4 → `HIFI_DEGRADED`。
5. 单次调整步长上限 5 个用户单位（1.0 dB）；更大跨度分帧应用，每帧 20 ms。
   （ES9018 自带 `Volume Ramp Rate = 2`，此为叠加保护。）
6. **写入失败不得阻断系统启动**：`platform_init` 中任何 `Volume` 相关失败只记录并继续。
7. 持久化写 `vendor.leo.audio.hifi.volume`，**不写** `persist.audio.hifi.volume`。

---

## 7. WCD 旁路检测（M3-5）

M2 已实测：主路由被切断后 AudioFlinger 会另开 `SLIMBUS_0_RX ← MultiMedia5` 并**真实出声**。
只检查"QUAT 已开"无法发现它。

**三联断言，全部致命，任一失败 → `ERROR_FALLBACK` code 6：**

```text
E5a  数字侧：对 N ∈ [1..16]，"SLIMBUS_0_RX Audio Mixer MultiMedia<N>" 读回必须全为 Off
E5b  模拟侧："HPHL DAC Switch" 读回必须为 Off
E5c  通路侧："SLIM RX1 MUX" 与 "SLIM RX2 MUX" 读回必须为 ZERO
```

**采样时机（三处，且必须同 generation）**：
① `HIFI_ARMING` 结束前；② 每次 `select_devices()` 之后；③ 息屏/后台每 30 s 巡检。

**为何是致命而非降级**：旁路会让用户听到 WCD 耳放的声音，而界面仍在谈论 HiFi。
正确行为是主动回退到 `headphones`，使声音来源与界面陈述一致。

---

## 8. ACDB 无条目的处理（M3-6）

事实 F-13：`hifi-headphones` 在 stock 与 MoKee 的 `audio_platform_info*.xml` 中均无 `acdb_id`；
MIUI 原厂即以"device 34 缺少 ACDB ID"告警运行。

1. **建模为常量**：`acdb_device_table[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES] = -1`
   （`-1` 是本分支既有的"无条目"约定，见 `[SND_DEVICE_NONE] = -1`），并加注释说明这是原厂行为。
2. **状态三态**：E10' 取 `OK` / `ABSENT_EXPECTED` / `ERROR`。`ABSENT_EXPECTED` **不降级**；
   `ERROR`（loader 报错、linker/SELinux denial）→ `HIFI_DEGRADED`。
3. **维护页显式呈现**：「ACDB：无该设备条目（与原厂一致）」。普通界面不呈现。
4. **写入禁令**：**禁止**为 `hifi-headphones` 借用 `headphones` 或任何其他设备的 ACDB ID。
   借用会把为 WCD 模拟链标定的 EQ/增益/限幅套到 ESS 数字链上。

---

## 9. property、set_parameters 与状态接口

### 9.1 property

| 名称 | 类型 | 写入者 | 默认 |
| --- | --- | --- | --- |
| `vendor.leo.audio.hifi.enable` | bool 字符串 | HAL | `false` |
| `vendor.leo.audio.hifi.volume` | int 0–60 | HAL | 不存在时视为"不写 `Volume`" |
| `vendor.leo.audio.hifi.supported` | bool（只读发布） | HAL 自检后 | — |

**不使用** `persist.audio.hifi` / `persist.audio.hifi.volume`（MIUI 语义未完全证明，且 MoKee 无对应 `property_contexts` 条目）。

### 9.2 set_parameters（唯一控制入口）

| 键 | 值 | 行为 |
| --- | --- | --- |
| `leo_hifi_mode` | `true` / `false` | 改 `my_data->leo_hifi`；变化时遍历 `usecase_list`，对每个 `type == PCM_PLAYBACK` 调 `select_devices()`；写 `vendor.leo.audio.hifi.enable` |
| `leo_hifi_volume` | `0`–`60` | clamp → `leo_set_hifi_volume()` → 读回 → 写 `vendor.leo.audio.hifi.volume` |

### 9.3 get_parameters（只读状态）

键 `leo_hifi_status`，返回单行 `k=v;` 结构化快照：

```text
supported=1;requested=hifi;effective=hifi_active;gen=17;fail=0;
snd_device=hifi-headphones;quat_mm=1;quat_bw=S24_LE;quat_sr=KHZ_48;
vol_ctl=205;vol_user=0;ess_bound=1;streams=1;acdb=absent_expected;
ev=E1,E2,E3,E4,E5a,E5b,E5c,E6,E8,E9
```

未知字段一律 fail-closed 为"未确认"，**不填猜测值**。

### 9.4 SELinux / property_contexts 需求

```text
# device/xiaomi/leo/vendor_prop.te（或等价文件）
vendor_internal_prop(vendor_leo_audio_prop)

# property_contexts
vendor.leo.audio.       u:object_r:vendor_leo_audio_prop:s0

# hal_audio_default.te
set_prop(hal_audio_default, vendor_leo_audio_prop)
# Status Service 只需 get_prop
get_prop(leo_status_service, vendor_leo_audio_prop)
```

M5（`user` + Enforcing）之前这些规则不阻断功能，但必须在 M3-D 就位，避免 M5 才发现缺口。
**HAL 是唯一被授予 `set_prop` 的域。**

---

## 10. 最小补丁文件与函数清单

源码基线：`MoKee/android_hardware_qcom_audio` @ `7f4cac748b6f62897294cdaece9d1aec27e1e927`
（manifest 路径 `hardware/qcom-caf/msm8994/audio`），构建产物必须是 **32-bit**。

| # | 文件 | 函数 / 位置（基线行号） | 改动 |
| ---: | --- | --- | --- |
| P1 | `hal/msm8974/platform.h` | snd_device enum，`SND_DEVICE_OUT_VOICE_SPEAKER_PROTECTED` 之后（L104–106） | 追加 `SND_DEVICE_OUT_LEO_HIFI_HEADPHONES`；`SND_DEVICE_OUT_END` 自动顺延 |
| P2 | `hal/msm8974/platform.c` | `device_table[]`（L287–324） | `[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES] = "hifi-headphones"` |
| P3 | `hal/msm8974/platform.c` | `acdb_device_table[]`（L395–） | `= -1` + 注释 |
| P4 | `hal/msm8974/platform.c` | `struct platform_data`（L~250） | 新增 `leo_hifi`、`leo_hifi_volume`、`leo_hifi_supported`、`leo_ctl_cache` |
| P5 | `hal/msm8974/platform.c` | `platform_init()`（L1102） | 控件预解析 + `device_table` 自检 + property 读入（**不写 `Volume`**） |
| P6 | `hal/msm8974/platform.c` | **新增** `leo_set_hifi_volume()` | 写 + 读回 + clamp + 步长限制 |
| P7 | `hal/msm8974/platform.c` | **新增** `leo_set_hifi_backend()` | 写 `QUAT_MI2S BitWidth` / `SampleRate` + 读回 |
| P8 | `hal/msm8974/platform.c` | **新增** `leo_hifi_check_bypass()` | E5a/E5b/E5c |
| P9 | `hal/msm8974/platform.c` | `platform_get_output_snd_device()`（L2085–2094） | 有线耳机分支加 `leo_hifi` 判定 |
| P10 | `hal/msm8974/platform.c` | `platform_check_and_set_codec_backend_cfg()`（L3393） | 挂入 `leo_set_hifi_backend()`；用 `is_offload_usecase()` |

> **[2026-08-29 修订]** P10 作废。进入侧钩子改为
> **`hal/audio_hw.c` `enable_snd_device()`（L637）→ `platform_leo_hifi_snd_device_enabled()`**，
> 后者定义在 `platform.c`。M3 按**设备**而非按 usecase 钉后端，
> 因此不再需要 `is_offload_usecase()` 判定；该判定留给 M3.5，
> 届时仍禁止写 `usecase->id == 3` 字面量。
| P11 | `hal/msm8974/platform.c` | `platform_set_parameters()`（L2772） | 新键 `leo_hifi_mode` / `leo_hifi_volume` |
| P12 | `hal/msm8974/platform.c` | `platform_get_parameters()`（L3062） | 新键 `leo_hifi_status` |
| P13 | `hal/audio_hw.c` | `enable_audio_route()`（L527）/ `disable_audio_route()`（L560）/ `select_devices()`（L937） | 状态机钩子 |
| P14 | `device/xiaomi/leo/` | `property_contexts` + `*.te` | §9.4 |

**不触碰**：kernel、DTB、任何 XML、`audioserver`、AudioFlinger、AudioPolicyManager、ACDB 库、Dirac、
以及**零调用者的 `platform_check_hifi_backend_cfg`**（该符号在 MoKee 源码中根本不存在，若日后被引入亦不得使用）。

### 10.1 禁止复制 MIUI 数值 34（M3-9）

1. 补丁中**零裸数字**：所有 snd_device 用符号名；新增枚举数值由编译器决定，
   文档、日志、断言、TSV 一律只记名字。
2. `device_table` / `acdb_device_table` 已使用**指定初始化器**（基线确认），追加项必须沿用。
3. 编译期断言：

   ```c
   _Static_assert(SND_DEVICE_OUT_LEO_HIFI_HEADPHONES < SND_DEVICE_OUT_END, "...");
   _Static_assert(SND_DEVICE_OUT_END == SND_DEVICE_IN_BEGIN, "...");
   ```
4. 运行期自检（`platform_init`，早于任何路由）：
   `strcmp(device_table[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES], "hifi-headphones") != 0`
   → `leo_hifi_supported = false`，code 12，**本次 boot 彻底禁用 HiFi**（不是降级）。
5. usecase 判据一律 `is_offload_usecase(uc->id)`，禁止 `uc->id == 3`。

---

## 11. 阶段拆分

| 阶段 | 内容 | 完成判据 | 不做 |
| --- | --- | --- | --- |
| **M3-0** | 建 Linux 构建主机；同步基线；**无修改**构建 32-bit HAL；与 `701019bd…` 符号级对照 | 双次构建自身一致；差异逐项可解释 | 不刷机 |
| **M3-A** | P1–P5、P8、P12、P13 的**只读部分**：加枚举、加状态机、加旁路断言、加 `leo_hifi_status`；`leo_hifi` 恒为 false | 设备行为与原版 MoKee 逐项一致；旁路断言在**标准耳机态**下能正确报告"旁路存在"（正向验证） | 不改路由 |
| **M3-B** | 打开 P9：`leo_hifi_mode=true` 时选 `LEO_HIFI_HEADPHONES`；启用 P7 的进入/退出确定性写入 | A2、A3 通过；E5、E6 全绿 | 不动音量 |
| **M3-C** | 启用 P6、P11 的音量路径 | R6/R7 完成；A7/A8 通过 | 不动速率策略 |
| **M3-D** | Status Service（只读 binder，signature 权限）+ P14 SELinux | 维护页可读全部证据；普通 UI 只读摘要 | UI 无写能力 |
| **M3.5** | 仅 S1 场景的 44.1 DIRECT 直通实验 | 前置 P1–P7 全满足 | 不为第三方 App 做 hack |

**M3-B 与 M3-C 不得合并**：音量变化会掩盖路由问题，反之亦然。

---

## 12. 三层验收

### 12.1 host / offline（无需设备）

| ID | 检查 | 工具 |
| --- | --- | --- |
| H1 | `device_table` / `acdb_device_table` / snd_device 枚举三者条目数与索引一致 | `scripts/verify-m3-source-layout.sh` |
| H2 | 源码 snd_device 顺序与设备二进制 `device_table` 逐项一致 | 同上 |
| H3 | patch 不含跨版本裸数字 `34`；不改 `platform_check_hifi_backend_cfg` | `scripts/verify-m3-patch-contract.sh` |
| H4 | patch 含进入与退出两侧的 `KHZ_48` / `S24_LE` 写入 | 同上 |
| H5 | patch 含 `Volume` clamp、读回、失败回退 | 同上 |
| H6 | patch 不引入 adb / Magisk / root daemon / App 直写 mixer | 同上 |
| H7 | patch 使用 `is_offload_usecase()` 而非 `id == 3` | 同上 |
| H8 | **feature flag 关闭时与上游逐 token 相同**（`platform.h` / `platform.c` / `audio_hw.c`） | `scripts/verify-m3-flag-off-equivalence.sh` |
| H9 | 进入钩子在 `enable_snd_device()`，且不存在对 `usecase->out_snd_device` 的守卫 | `verify-m3-patch-contract.sh` |
| H10 | dB 日志走符号安全的 `leo_hifi_ctl_to_db()`，无 `abs()` 版本 | 同上 |
| H11 | 旁路观测覆盖 `RX1/RX2 MIX1 INP1`、`CLASS_H_DSM MUX`、`QUAT_MI2S_RX Audio Mixer MultiMedia` | 同上 |
| H12 | 故障注入（22 组场景）在 host mock 下全部符合预期 | `tests/host-mock-leo-hifi/run.sh` |

> **H12 的边界**：host mock 编译并运行的是 `leo_hifi.c` **对 mock 头文件**的版本，
> 用于验证决策逻辑。它**不是** Android 构建，**不是** M3-0，**不构成设备证据**。

### 12.2 build / static（构建主机）

| ID | 检查 |
| --- | --- |
| B1 | 无修改构建产物与 `701019bd…` 符号集合差异可解释 |
| B2 | 打 patch 后仍为 32-bit ARM ELF，`DT_NEEDED` 未新增 |
| B3 | 默认关闭 feature flag 时，`objdump -T` 与无修改构建一致（除新增静态函数外） |
| B4 | 双次构建产物自身一致 |

### 12.3 真机（需授权）

沿用 `M3-HIFI-ARCHITECTURE-RULING-DRAFT.md` §8 与第一轮 §8 的 A1–A18，重点：
A1 插耳机不播放、A2 首次播放、A3 A/B/A 因果、A4 暂停 3 s、A5 同参数切歌 ×20、
A7 SPL 对照、A8 音量扫描、A9 拔耳机、A10 息屏 2 h、A11/A12 服务重启、
A13/A14 故障注入、A15 重启恢复、A16 多流、A17 外放。

---

## 13. GO / NO-GO

### 13.1 编译前 GO

1. 本文与 `docs/17` 已冻结且相互一致；
2. 争议 N-5 已澄清或明确记录为"两值均不得写入默认配置"；
3. 源码谱系已按 `M3-SOURCE-PROVENANCE.md` 定级为 **exact build provenance**，
   且 N-8（设备树本地补丁）已被列为 M3-0 的对照项；
4. Linux 构建主机就绪，同步后可用空间 ≥ 6 GiB；
5. `scripts/verify-m3-source-layout.sh` 与 `scripts/verify-m3-patch-contract.sh` 全绿；
6. F-1…F-16 中至少 F-2、F-3、F-4、F-5、F-8、F-9、F-16 七条已由项目主代理独立复核。

### 13.2 写入前 GO（首次向设备写 boot/system 之前）

1. M3-0 的无修改构建产物与 `701019bd…` 符号级对照完成；
2. **`boot` 的持久化策略已决定**——当前 `boot` 仅 `fastboot boot` 临时启动，
   任何需要重启才能生效的验证都必须先解决这一点，否则"重启恢复"类用例无法执行；
   > **[2026-08-29 已关闭]** `boot` 已持久写入，回读 SHA-256
   > `9470dd6a…8934af` 与候选一致；`misc` 残留 BCB 造成的 recovery 循环已清除。
   > A15（重启后恢复）现在可执行。
3. R5 完成，I-1 升格为事实；
4. 回滚材料双份可读、recovery/fastboot 救援入口已实测（`docs/18` M2 前置门）；
5. 设备所有者当场明确授权。

### 13.3 宣布成功前 GO

1. A1–A18 全部通过，且每项都有 `leo_hifi_status` 快照 + `tinymix` 读回 + `dmesg` 三重记录；
2. R6 与 R7 完成，I-2、I-3 升格为事实；
3. A7 的 SPL 残差已解释（N-6 收敛）；
4. 任何"状态显示 HiFi 但证据不一致"的记录数为 0；
5. 文档、manifest、验收报告齐全。

**NO-GO（全局，任一成立即停止）**：
需要改 AudioFlinger / AudioPolicyManager / audioserver；
需要把 Android 7 二进制放进 Android 10；
需要关闭 SELinux 或依赖常驻 root；
`HIFI_ACTIVE` 被简化为"耳机有声"或"property 为 true"；
界面在证据不完整时显示"已激活"；
为 `hifi-headphones` 借用其他设备 ACDB ID；
补丁出现 snd_device 或 usecase 的裸数字。

---

## 14. 回滚条件

| 触发 | 回滚动作 |
| --- | --- |
| M3-A 出现与原版 MoKee 不一致的音频行为 | 撤回 patch，回到无修改构建 |
| M3-B 出现 A3 假阳性（旁路未被拦截） | 关闭 feature flag（`leo_hifi_mode=false`），设备行为立即回到原版 |
| M3-C 出现削波 / 突发响度 / 单边 | `Volume` 立即写回 205；关闭音量路径 |
| 连续两次冷启动失败 | 按 `docs/18` 回滚 `system`；**注意 `boot` 当前为临时启动，不能依赖"重启恢复"** |
| 任何写入后设备无法进入 recovery/fastboot | 立即停止，按 Phase 4 rollback set 处理 |

**关键约束**：feature flag 默认关闭 ⇒ 任何阶段的第一层回滚都是**改 property，不是刷机**。

---

## 15. 不得使用的危险捷径

| 捷径 | 为什么禁止 |
| --- | --- |
| 二进制 patch MIUI HAL 或把 MIUI HAL 放进 MoKee | ABI、linker namespace、SELinux 域、ACDB 代际全部不匹配；`docs/16` §9 已明令禁止 |
| `LD_PRELOAD` / 包装 so 拦截 `platform_get_output_snd_device` | 该函数为 `.so` 内部调用，无法从外部拦截；Android 10 linker namespace 也禁止 |
| init.rc 或常驻 `tinymix` 脚本写 mixer | 无法感知流生命周期，与 `select_devices()` 竞态（M2 已实测），违反单写入者原则 |
| （同上，2026-08-29 加强） | **F-19 实机反证**：播放中改 mixer 会让 `out_write` 每约 10.5–11.6 s 返回 `-5`，HAL 随即 standby 并把路由改回 SLIMBUS/WCD，而手工写下的 QUAT 仍留在 On，形成双通路。这不是"可能有竞态"，是**必然被撤销**。 |
| 给 `hifi-headphones` 借用 ACDB ID | 把 WCD 模拟链的标定套到 ESS 数字链 |
| 只改 `QUAT_MI2S SampleRate` 追求 44.1 | 前端仍 48 kHz，SRC 只是搬到 ADSP，且触发未验证的 slave 时钟路径 |
| 用"耳机有声"判定 HiFi 成立 | M2 已实测 MultiMedia5 旁路会真实出声 |
| 为让状态变绿而放宽证据门 | 证据门存在的唯一理由就是不放宽 |
| 依赖重启来恢复现场 | 当前 `boot` 仅临时启动，重启会丢失当前运行环境 |
| 无人值守的自动音量扫描 | 突发响度可能损伤听力与耳机 |


---

## 16. 已知产品行为后果（2026-08-29 新增）

### 16.1 HiFi 期间的第二条播放流会触发回退

依据 F-23：`hw_interface_table` 把 ESS 放在自己的后端上，
`platform_check_backends_match()` 判定 `QUAT_MI2S_RX` 与 `SLIMBUS_0_RX` 不匹配，
于是 `check_and_route_playback_usecases()` **有意不把**其他 SLIMBUS usecase 迁到 ESS。
它们保持 `headphones` 路径，`HPHL DAC Switch` 因此保持为 1。

在修订后的 E5 语义下，模拟出口开放是致命条件 → 控制器回退到标准路由。

**净效果：HiFi 播放期间来一条通知音，HiFi 会掉回普通耳机路径。**

这是 v1 的**有意选择**：宁可回退，也不在一个无法离线证明其行为的双通路上继续对用户
宣称 HiFi。两条替代方案都不属于 M3：

1. 把全部 playback usecase 一并迁到 ESS（要动 `check_and_route_playback_usecases()`，
   影响面远超 M3 的补丁边界）；
2. 在 HiFi 态下抑制系统提示音（产品决策，属 M4 的 Leo Home 范畴）。

**验收要求**：A16 必须实测这一行为并记录其可接受性。在 A16 有结论之前，
不得对外描述 HiFi 为"始终生效"。

### 16.2 探测失败的可恢复性

`leo_hifi_init()` 的失败不再永久：控件缺失或 ESS 未绑定这类**瞬态**失败，
在后续路由决策时最多再做 2 次**只读**重探测（`stat()` + `mixer_get_ctl_by_name()`，
不写任何控件，因此不会爆音、不会触发重路由、不耗电）。
只有 `device_table` 名字不符这一**结构性**失败永久禁用且不重试。

无论哪种失败，都不阻断 Android 启动，也不阻断普通耳机播放。


---

## 17. 构建门（2026-08-29 新增）

构建门的六级证据阶梯、`platform_api.h` 约定问题、`DT_NEEDED` 与导出符号硬判据、
feature-OFF 三层等价性、以及"如何证明产物来自最新补丁"的 P1–P8，
统一记录在 [`docs/research/M3-BUILD-GATE-ACCEPTANCE.md`](research/M3-BUILD-GATE-ACCEPTANCE.md)。

其中一条会影响补丁本身、但**本轮刻意不改**（避免在 agy 构建期间移动基线）：

> 四个 `platform_leo_hifi_*` 定义在 `platform.c`，却声明在平台私有的 `leo_hifi.h`，
> 导致平台无关的 `audio_hw.c` 需要包含平台私有头。当前能编译（`LOCAL_C_INCLUDES`
> 含 `$(LOCAL_PATH)/$(AUDIO_PLATFORM)`，且 `LEO_HIFI_ENABLED` 只在
> `AUDIO_PLATFORM = msm8974` 时定义），但违反本树"platform 层导出走 `platform_api.h`"
> 的约定。**须在 L3 完成前以补丁 0006 修正。**
