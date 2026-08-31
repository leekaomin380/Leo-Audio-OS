# Gate 2：真实 Android HAL 模块链接 — 完成

日期：2026-08-31（Asia/Shanghai）。轮值架构师：Claude（`LEO-HO-20260830-223623-CODEX-TO-CLAUDE`）。

本文件是构建证据，**不是刷写、安装或 ROM 集成授权**。产物未安装、未加载、未在设备上运行。

## 1. 结论

以 `7f4cac74` 干净源码 + 5 个 M3 补丁为输入，成功链接出真实 ARM32 ELF 共享对象
`audio.primary.msm8994.so`，`SONAME` 正确、导出 `HMI`、`DT_NEEDED` 与出厂模块一致，
**122 个未解析符号可 100% 由设备自身的 12 个运行库满足，缺失 0**。

M3 裁决书 §8 中 `Android HAL 模块编译 = BLOCKED/PENDING`、
`audio.primary.msm8994.so 真实链接 = NO-GO` 两行，据本文件可更新为 **GO**。
`ROM 集成`、`M3 上机` 两行**维持 NO-GO 不变**。

## 2. 此前为何被判定不可行，以及那个判断错在哪

阻断被记为「本机无 ELF 链接器」。实测该阻断的全部成本是：

| 缺失项 | 实际代价 | 获取方式 |
|---|---|---|
| ELF 链接器 | **6.0 MB** | `brew install lld` |
| 12 个链接库 | **1.7 MB** | 从设备 `adb pull`（只读） |

合计约 7.7 MB。此前无人实测缺什么，包括本班在 2026-08-31 08:16 之前——
我当时对链接器体积的估计（「几十到上百 MB」）偏离实际 10–20 倍，
若用户据此拒绝，就会以一个错数字堵死关键路径。**先测再判，不要先判再问。**

## 3. 输入身份

| 输入 | 身份 |
|---|---|
| HAL 源码 | `mokee_audio_clean` @ `7f4cac748b6f62897294cdaece9d1aec27e1e927`，clone 后 `git status` 干净 |
| M3 补丁 | `Leo-Audio-OS-claude-opus5/patches/phase5b-m3/0001..0005`，5 个全部 `apply --check` 通过，`diff --check` CLEAN |
| AOSP 头文件 | `agy-gemini31pro/research-cache/headers`（225 MB）。抽样核验为**真实 AOSP 原文**（bionic `stdio.h` 为 OpenBSD 血统原件；`cutils/properties.h` 为 AOSP 原件），非 mock |
| 内核 uapi 头文件 | **本轮改用真内核源码**：`xiaomi-classic-leo-kernel/include/{uapi/sound,sound}` 的 `compress_params.h`、`msmcal-hwdep.h`、`voice_params.h` |
| 链接库 | 设备 `68f5f468` 的 `/system/lib` ×10 + `/vendor/lib` ×2，只读 pull |
| 参照模块 | 设备 `/vendor/lib/hw/audio.primary.msm8994.so`，SHA256 `701019bd…9af47` |

### 3.1 surrogate 头文件已被消除

此前的对象门使用 3 个 surrogate 内核头，脚本自带警告
`Header cache includes surrogate kernel headers: NEVER install these objects.`

本轮首次编译即在 `audio_extn.c:747` 失败：

```
error: no member named 'min_blk_size' in 'struct snd_codec_options::(unnamed ...)'
```

根因是 surrogate `compress_params.h` 缺 QTI FLAC 解码字段。改用设备实际内核源码的
真头文件后 11/11 编译通过。内核来源已核验：

```
设备:     Linux version 3.10.108-gc93c59ddbb9
本地源码: VERSION=3 PATCHLEVEL=10 SUBLEVEL=108
```

**本轮产物不再依赖任何 surrogate 头文件。**

## 4. 编译配置的推导依据

`AUDIO_PLATFORM = msm8974`、`-DPLATFORM_MSM8994` 取自 `hal/Android.mk` 的平台映射。
特性宏与条件源文件取自设备树 `xiaomi-classic-msm8994-common-device/BoardConfigCommon.mk`
的实际开关，**逐条对应，非猜测**：

源文件 11 个：`audio_hw.c` `voice.c` `platform_info.c` `msm8974/platform.c`
`audio_extn/audio_extn.c` `audio_extn/utils.c` `msm8974/leo_hifi.c` `edid.c`
`audio_extn/hfp.c` `voice_extn/voice_extn.c` `voice_extn/compress_voip.c`

宏 16 个：`PLATFORM_MSM8994` `USE_VENDOR_EXTN` `LEO_HIFI_ENABLED` `PCM_OFFLOAD_ENABLED`
`PCM_OFFLOAD_ENABLED_24` `FLUENCE_ENABLED` `AFE_PROXY_ENABLED` `KPI_OPTIMIZE_ENABLED`
`HFP_ENABLED` `MULTI_VOICE_SESSION_ENABLED` `COMPRESS_VOIP_ENABLED`
`AUDIO_EXTN_FORMATS_ENABLED` `ENABLE_EXTENDED_COMPRESS_FORMAT` `FLAC_OFFLOAD_ENABLED`
`COMPRESS_METADATA_NEEDED` `DOLBY_ACDB_LICENSE`

M3 补丁在 `Android.mk` 中新增的 `AUDIO_FEATURE_ENABLED_LEO_HIFI` 是干净的 per-device
opt-in，并带 `AUDIO_PLATFORM=msm8974` 内层守卫；未设该开关时其它板子逐字节不受影响。

## 5. `use_case_table` 悬案：首次有真链接证据

`hal/audio_hw.h:145` 的 `const char * const use_case_table[AUDIO_USECASE_MAX];`
是 tentative definition。以 `-fno-common`（现代 clang 默认）链接：

```
ld.lld: error: duplicate symbol: use_case_table   ×9
```

**实测 10 个编译单元各定义一次，产生 9 个重复定义**：`audio_hw.c` `voice.c`
`platform_info.c` `platform.c` `audio_extn.c` `utils.c` `edid.c` `hfp.c`
`voice_extn.c` `compress_voip.c`（`leo_hifi.c` 不含）。

项目此前记录的「×11」与 agy J102 报告的「12 个编译单元」**均不准确**。这两个数字
此前都是推算，本轮是链接器实测。

加 `-fcommon`（零源码改动）后链接成功。旁证：
`-fcommon` 下该符号为 `C`（common，可合并），`-fno-common` 下为 `R`（`.rodata` 强定义）。

**裁决**：出厂构建必然具备 `-fcommon` 语义，否则出厂模块不可能存在。方案 (a)
「构建时加 `-fcommon`」是零源码改动的忠实复现，**本轮采用**。方案 (b)（头文件加
`extern`）作为可选清理保留，但不应作为「让它能编译」的必要条件提出。

agy J102 推荐 (b) 并给了补丁，但该补丁**有实质缺陷**：它在 `audio_hw.c` 末尾追加了一份
`use_case_table` 定义，而 `audio_hw.c:168` 早已存在带初值的完整定义。其报告写
「补 1 行定义」，说明未看到既有定义。正确的最小 (b) 补丁只需头文件加一个 `extern`。

## 6. 产物与参照模块的逐项差分

产物：`out/audio.primary.msm8994.so`，205412 字节，
SHA256 `cac5689fddf10ef1e2c2c2a220a6708adf97bf99e0cc99382850477313b2ee44`
`ELF 32-bit LSB shared object, ARM, EABI5 version 1 (SYSV), dynamically linked`

| 检查 | 本次构建 | 参照模块 | 判定 |
|---|---|---|---|
| SONAME | `audio.primary.msm8994.so` | 同 | PASS |
| `DT_NEEDED` | 11 项 | 12 项 | 见下 |
| 导出 `HMI` | 是 | 是 | PASS |
| 导出符号总数 | 199 | 205 | 交集 **180** |
| 未解析符号 | 122 | 120 | 见 §7 |
| `.fini_array` | **无** | 有 | 见 §8 |

`DT_NEEDED` 差异：参照多 `libc++.so`（Android 构建系统对共享库的默认追加）。
首次链接时我多加了 `-lacdbloader`，实测去掉后仍链接成功，最终产物已对齐——
参照模块同样不静态依赖 `libacdbloader`，ACDB 走 `dlopen`。

导出符号差异：参照独有的 25 个几乎全是编译器内建
（`__aeabi_*` `__divdi3` `__udivmoddi4` 等），来自出厂构建静态链接的 builtins 库。
**本次独有的是 `leo_hifi_*` 共 8 个**：`leo_hifi_init` `leo_hifi_on_route`
`leo_hifi_on_route_off` `leo_hifi_route_wanted` `leo_hifi_apply_volume`
`leo_hifi_read_volume` `leo_hifi_restore_volume_floor` `leo_hifi_check_bypass`
`leo_hifi_ctl_to_db`。

**这是 M3 控制器首次以机器可核验的形式进入一个真实的 Android 共享对象。**
此前的证据只到 relocatable object 层级。

## 7. 符号闭合：122/122，缺失 0

对设备的 12 个库逐一解析 `dynsym`（合计提供 2868 个已定义符号），
本次模块的 122 个未解析符号**全部有确定归属，缺失 0**：

| 提供方 | 数量 |
|---|---:|
| libc.so | 44 |
| libtinyalsa.so | 23 |
| libtinycompress.so | 18 |
| libcutils.so | 17 |
| libaudioroute.so | 8 |
| libexpat.so | 5 |
| libdl.so | 3 |
| libhardware.so / libm.so / libprocessgroup.so / liblog.so | 各 1 |

含 `__aeabi_idiv` `__aeabi_uidiv` `__aeabi_ldivmod` ← `libc.so`；
`__aeabi_memclr` `__aeabi_memcpy` ← `libaudioroute.so`。
即**编译器内建库的缺失在本设备上不构成运行期阻断**——bionic 与 libaudioroute 已导出它们。

（`libaudioroute.so` 再导出内建符号是这台设备的既成事实，不是好设计；
记录在案，不据此推广到其它设备。）

## 8. 仍未闭合的项（不得由本文件推导为已解决）

1. **`.fini_array` 缺失**。参照模块有，本次产物无——出厂构建链接了
   `crtbegin_so.o` / `crtend_so.o`，本轮没有。对纯 C、无静态析构的 HAL 模块很可能无害，
   **但这是产物与出厂模块之间一处确凿的结构差异，不能因为「大概没事」就略过。**
   要消除必须取得 Android 的 crt 目标文件。
2. **未加 `-D_FORTIFY_SOURCE=2`**。参照模块使用 `__memcpy_chk` `__strlcpy_chk`
   `__vsnprintf_chk` 等 FORTIFY 变体，本次产物使用未加固版本。属编译选项差异，
   与出厂不完全一致。
3. **未加载验证**。产物从未被 `dlopen`、从未由 audioserver 加载、从未在设备上运行。
   **链接成功 ≠ 可加载 ≠ 可播放。**
4. **feature-OFF 等价性未在本产物上重验**。本轮只构建了 `LEO_HIFI_ENABLED` 变体。
5. **未做 ROM 集成、未做离线镜像审计、未准备回退材料**。Gate 3 全部未开始。

## 9. 证据门更新建议

| 层级 | 原状态 | 建议 | 依据 |
|---|---|---|---|
| Android HAL 模块编译 | BLOCKED/PENDING | **GO** | 11/11 真实头文件编译通过 |
| `audio.primary.msm8994.so` 真实链接 | NO-GO | **GO** | §6 §7 |
| ROM 集成与离线镜像审计 | NO-GO | **维持 NO-GO** | 未开始 |
| M3 上机 | NO-GO | **维持 NO-GO** | §8 全部未闭合；且需单独授权 |

ROADMAP Phase 5B 第一条未勾项的两个条件（R7-B、真实 HAL 模块链接）至此均已完成。
**本班不自行勾选**，理由是 §8 第 1、3 两条：产物与出厂模块存在确凿结构差异，
且从未被加载验证。是否勾选交用户裁决。

## 10. 复现

```sh
G=<本目录>
bash $G/build.sh "$G" <AOSP头文件根> "$G/kheaders"
/opt/homebrew/bin/ld.lld -shared -soname audio.primary.msm8994.so \
  -o $G/out/audio.primary.msm8994.so $G/out/*.o \
  -L$G/lib -lc -lcutils -ldl -lexpat -lhardware -llog -lm \
  -lprocessgroup -ltinyalsa -laudioroute -ltinycompress
python3 $G/elfinfo.py $G/out/audio.primary.msm8994.so
```
