# M3 源码谱系裁定

日期：2026-08-29
裁定者：Claude Opus 5（独立首席架构审计者）
方法：GitHub REST API + 单文件 `raw.githubusercontent.com` 下载 + 与本地私有二进制的结构比对。
**未做完整克隆**；临时文件位于 Git 忽略的 `research-cache/`，不提交。
未连接设备、未运行 `adb`/`fastboot`、未修改镜像。

---

## 0. 裁定

| 候选 | 定级 | 结论 |
| --- | --- | --- |
| `MoKee/android_hardware_qcom_audio` **分支 `mkq-mr1-caf-msm8994`**，HEAD `7f4cac748b6f62897294cdaece9d1aec27e1e927`（2020-01-14） | **exact build provenance** | **成立。** 由 MoKee `mkq-mr1` manifest 显式 pin；其 snd_device 枚举、`device_table`、`use_case_table`、结构体偏移与设备二进制**逐项一致**；71 个 `platform_*` 导出符号中 70 个在该文件定义，剩下 1 个在同仓库另一文件 |
| `MoKee/android_hardware_qcom_audio` **分支 `mkq-mr1`**，HEAD `e20a6987ebc734a1e554836874da3b13383a2e4d`（2022-01-09） | **refuted** | **否证。** 这是同一仓库的**通用分支**，不是 msm8994 CAF 分支；其 OUT 枚举有 48 项（设备二进制为 37 项）且顺序不同；71 个二进制导出符号中 **33 个在该文件中根本不存在** |
| agy 在 `702f7e8` 中把 `e20a6987…` 标为 "LineageOS `android_hardware_qcom_audio`" | **归属错误 + 分支错误** | 该 commit 确实同时存在于 LineageOS 与 MoKee 两个仓库（MoKee 是 fork，共享历史），但它是 **MoKee `mkq-mr1` 分支的 HEAD**，与 leo 无关 |

**项目 `docs/reviews/2026-08-28-phase5b-m2-mokee-runtime-baseline.md` §8 记录的
`mkq-mr1-caf-msm8994 / 7f4cac74…` 是正确的**，本轮把它从"未验证的转述"升格为
**由 manifest 与二进制双向确认的事实**。

---

## 1. 精确坐标

```text
仓库   https://github.com/MoKee/android_hardware_qcom_audio
分支   mkq-mr1-caf-msm8994
HEAD   7f4cac748b6f62897294cdaece9d1aec27e1e927
日期   2020-01-14T02:34:53Z
标题   audio: free and assign NULL to global static device pointer
路径   （repo 内）hal/msm8974/platform.c, hal/msm8974/platform.h, hal/audio_hw.c, hal/audio_hw.h
```

manifest 侧固定：

```text
仓库   https://github.com/MoKee/android
分支   mkq-mr1（该仓库默认分支）
文件   snippets/mokee.xml : 114
内容   <project path="hardware/qcom-caf/msm8994/audio"
                 name="MoKee/android_hardware_qcom_audio"
                 groups="qcom,qcom_audio,pdk-qcom"
                 revision="mkq-mr1-caf-msm8994" />
```

设备侧固定：

```text
仓库   https://github.com/MoKee/android_device_xiaomi_leo
分支   mkq-mr1（与 mkq 同指 b994edccae75e50ddfdbd3c74b71f9f1aae31b3e）
BoardConfig.mk:6   TARGET_BOARD_PLATFORM := msm8994
```

**时间线自洽性**：ROM 为 `MK100.0-leo-221019-RELEASE`（2022-10）。
`mkq-mr1-caf-msm8994` 的 HEAD 停在 2020-01-14，即该分支在 ROM 构建前 2 年 9 个月已冻结；
因此该 ROM 构建时使用的就是 HEAD `7f4cac74…`，不存在"HEAD 已前移"的歧义。
（对照：`mkq-mr1` 通用分支 HEAD 为 2022-01-09，仍在演进，说明二者是不同用途的分支。）

---

## 2. 与设备二进制的逐项比对

被比对二进制：
`resources/private/phase5b-mokee/selected/system/vendor/lib/hw/audio.primary.msm8994.so`
SHA-256 `701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47`（ELF32 ARM，`.note.android.ident` API 29）

| 比对项 | 源码 A（`7f4cac74`） | 设备二进制 | 结果 |
| --- | --- | --- | --- |
| **snd_device OUT 枚举项数** | 37（`SND_DEVICE_OUT_HANDSET` … `SND_DEVICE_OUT_VOICE_SPEAKER_PROTECTED`） | 37（`device_table` 索引 1–35 + `NONE`） | **一致** |
| **snd_device OUT 顺序** | `…SPEAKER_REVERSE(5), LINE(6), HEADPHONES(7), SPEAKER_AND_HEADPHONES(8), SPEAKER_AND_LINE(9)…` | `…speaker-reverse(5), line(6), headphones(7), speaker-and-headphones(8), speaker-and-line(9)…` | **逐项一致（37/37）** |
| **OUT/IN 边界** | `SND_DEVICE_OUT_END` 之后 `SND_DEVICE_IN_BEGIN = SND_DEVICE_OUT_END`，首项 `IN_HANDSET_MIC` | 索引 36 = `handset-mic` | **一致** |
| **`device_table` 初始化风格** | 指定初始化器（`[SND_DEVICE_OUT_X] = "..."`） | — | 便于安全追加（见 `docs/19` §10.1） |
| **`acdb_device_table` 无条目约定** | `[SND_DEVICE_NONE] = -1` | — | 采用 `-1` 作为 `hifi-headphones` 的取值 |
| **usecase 枚举** | `DEEP_BUFFER=0, LOW_LATENCY=1, MULTI_CH=2, OFFLOAD=3, OFFLOAD2..9=4..11` | `use_case_table[3] = "compress-offload-playback"`，索引 5–11 为可重定位指针（`MULTIPLE_OFFLOAD_ENABLED` 已定义），索引 12 = `audio-ull-playback` | **一致** |
| **`usecase_type_t`** | `PCM_PLAYBACK=0, PCM_CAPTURE=1, VOICE_CALL=2, VOIP_CALL=3, PCM_HFP_CALL=4` | 二进制中 `usecase->type == 0` 判据用于 PCM_PLAYBACK | **一致** |
| **`struct audio_usecase` 偏移** | `listnode list`(0,4) → `id`(+8) → `type`(+0xc) → `devices`(+0x10) → `out_snd_device`(+0x14) → `in_snd_device`(+0x18) → `stream`(+0x1c) | 反汇编读到 `[r,#0x8]`=id、`[r,#0xc]`=type、`[r,#0x1c]`=stream | **一致** |
| **`platform_get_output_snd_device` 有线耳机分支** | `if (WIRED_HEADSET && anc_enabled) → ANC…; else snd_device = SND_DEVICE_OUT_HEADPHONES;` | `0x17f20: mov r0,#7 ; tst r4,#12 ; bne <ret>`（无 ANC 调用） | **形状一致**（MoKee 二进制无 ANC 符号，与该分支的 `audio_extn` 编译开关一致） |
| **`platform_check_and_set_codec_backend_cfg`** | 只处理 SLIM codec backend，**无任何 HiFi 分支**，函数体 ~20 行 | 导出符号大小 `0xb0`（stock MIUI 同名函数为 `0x218`） | **一致（无 HiFi 逻辑）** |
| **`is_offload_usecase()`** | `audio_hw.h:374` 声明、`audio_hw.c:1333` 定义 | 存在 | **可用**（`docs/19` §10.1 第 5 条） |
| **`platform_*` 导出符号覆盖** | `platform.c` 定义 72 个 | 二进制导出 71 个 | **70/71 在 `platform.c`；剩余 1 个 `platform_info_init` 属同仓库另一编译单元** |

### 2.1 候选 B 的否证

| 比对项 | 源码 B（`e20a6987`，`mkq-mr1`） | 设备二进制 | 结果 |
| --- | --- | --- | --- |
| snd_device OUT 项数 | **48** | 37 | 不符 |
| OUT 顺序 | `SPEAKER(2), SPEAKER_REVERSE(3), SPEAKER_SAFE(4), HEADPHONES(5), LINE(6)…`（无 `SPEAKER_EXTERNAL_*`，新增 `SPEAKER_SAFE`） | `speaker(2), speaker-ext-1(3), speaker-ext-2(4), speaker-reverse(5), line(6), headphones(7)` | 不符 |
| `platform_*` 定义覆盖 | 79 个定义 | 71 个导出 | **33 个二进制导出在 B 中不存在**（含 `platform_check_and_set_codec_backend_cfg`、`platform_get_parameters`、`platform_get_compress_offload_buffer_size` 等） |
| 文件规模 | `platform.c` 5129 行、`audio_hw.c` 6646 行 | — | A 为 3979 / 4128 行，代际明显不同 |

**结论：B 被艺术级地否证**，不是"结构类比"而是"不同代际的不同分支"。

---

## 3. 设备树侧的额外确认（byte-exact）

从 `MoKee/android_device_xiaomi_leo` @ `mkq-mr1` 直接下载并哈希：

| 文件 | 设备树 SHA-256 | 设备镜像 SHA-256 | 结果 |
| --- | --- | --- | --- |
| `audio/mixer_paths.xml` | `13db0e6e5bd04e02c36a6b84e815f492d730e107866b91e605ee653364084bb4` | `13db0e6e…4bb4` | **逐字节相同** |
| `audio/audio_platform_info.xml` | `8fa544779068490bcc81bd264380d508fe831b06e2023ad9381be79dedffe523` | `8fa54477…e523` | **逐字节相同** |

这有两层意义：

1. 设备树分支 `mkq-mr1`（commit `b994edcc`）即为 ROM 中音频配置的确切来源；
2. 那段 `<!-- HIFI -->` 顶层默认块（含 `<ctl name="Volume" value="205" />`、
   `Automute Level 120`、`THD2 Compensation 255` 等 10 项 ES9018 控件）**由 MoKee 设备树携带**，
   与 MIUI 的 `mixer_paths.xml` 逐字节相同——即 MoKee 从 MIUI 继承了这段配置，
   但**没有继承会覆盖 `Volume` 的 HAL 代码**。这正是 205 停留不动的完整因果链。

依赖链（`mokee.dependencies`）：
`device/xiaomi/leo` → `device/xiaomi/msm8994-common` + `vendor/xiaomi/leo`。

---

## 4. 定级

| 级别 | 判定 | 说明 |
| --- | --- | --- |
| **exact build provenance** | ✅ `mkq-mr1-caf-msm8994 @ 7f4cac74…` + `device_xiaomi_leo @ mkq-mr1` | manifest pin + 分支冻结时间早于构建 + 枚举/表/结构体/符号集四重一致 + 设备树配置 byte-exact |
| closest structural match | —（不需要退到这一级） | |
| analogy only | ❌ agy 的 `e20a6987…` | 同仓库不同分支，代际不同，符号集缺 33 个 |

### 4.1 仍未闭合的最后一环（N-8）

| 项 | 说明 | 闭合方式 |
| --- | --- | --- |
| 本地补丁 | 无法排除 MoKee 构建服务器在 `hardware/qcom-caf/msm8994/audio` 上应用了未推送的本地补丁 | **M3-0 的无修改构建 + 与 `701019bd…` 的符号级/节区级对照** |
| 工具链 | MoKee HAL 已 strip `.comment`，无编译器指纹（stock MIUI 保留了 `GCC 4.9 / Android clang 3.8.256229`） | 只能靠 M3-0 的产物比对推定 |
| `vendor/xiaomi/leo` | 私有 vendor 仓库，未审阅 | 与 HAL 源码无关，但影响 `libacdbloader` 等 blob 的来源 |
| `mixer_paths_i2s.xml` / `audio_platform_info_i2s.xml` | 未在 leo 设备树中找到；推测来自 `msm8994-common`（本轮该仓库树列举失败） | 低优先级，不影响 M3 |

**这不构成阻断**：M3 的补丁面全部落在已确认一致的枚举与函数上，
且 `docs/19` §10.1 的编译期断言与运行期自检会在表结构不符时直接禁用 HiFi 而非误动作。

---

## 5. 复现命令

```bash
# 分支 HEAD
curl -s "https://api.github.com/repos/MoKee/android_hardware_qcom_audio/branches?per_page=100&page=1" \
  | python3 -c "import json,sys;[print(b['name'],b['commit']['sha']) for b in json.load(sys.stdin) if 'mkq' in b['name']]"

# manifest pin
curl -s https://raw.githubusercontent.com/MoKee/android/mkq-mr1/snippets/mokee.xml | grep msm8994/audio

# 源码单文件
B=https://raw.githubusercontent.com/MoKee/android_hardware_qcom_audio/7f4cac748b6f62897294cdaece9d1aec27e1e927
curl -s $B/hal/msm8974/platform.h -o platform.h
curl -s $B/hal/msm8974/platform.c -o platform.c

# 设备树音频配置（byte-exact 验证）
curl -s https://raw.githubusercontent.com/MoKee/android_device_xiaomi_leo/mkq-mr1/audio/mixer_paths.xml | shasum -a 256

# 与二进制比对（见 scripts/verify-m3-source-layout.sh）
```

---

## 6. 对 agy `702f7e8` 的具体更正建议

| 文件 | 行 | 现状 | 应改为 |
| --- | --- | --- | --- |
| `agy-hal-evidence.tsv` | HAL-04 | `source = LineageOS android_hardware_qcom_audio`，`commit = e20a6987…`，confidence `High` | `source = MoKee/android_hardware_qcom_audio`，`commit = 7f4cac748b6f62897294cdaece9d1aec27e1e927`（分支 `mkq-mr1-caf-msm8994`），confidence `High`（现已可验证） |
| `agy-samplerate-evidence.tsv` | SR-04 / SR-05 | 同上 | 同上 |
| `AGY-MSM8994-HIFI-EVIDENCE.md` | §2 | 「高度匹配 LineageOS…属于结构类比」 | 改为 exact provenance，并指明 `e20a6987…` 实为 MoKee `mkq-mr1` 通用分支 HEAD，与 leo 无关 |
| `AGY-CORRECTION-NOTES.md` | §2「修正（源码谱系）」 | 「确认为基于 LineageOS 的结构类比」 | 该"修正"方向错误，应撤回 |
