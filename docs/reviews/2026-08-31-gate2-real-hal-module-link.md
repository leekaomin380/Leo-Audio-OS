# Gate 2：真实 Android HAL 模块链接 — 完成

> ## ⚠️ 更正（2026-08-31 09:2x，同日晚于本文其余内容）
>
> **本文 §1、§6、§7 关于首版产物的结论有实质错误，已由后续构建更正。原文保留在下方不删改。**
>
> 首版构建**漏配了 `-DHW_VARIANTS_ENABLED` 与源文件 `hal/msm8974/hw_info.c`**。
> 该开关不在设备树里，而是 `hal/Android.mk:14` 在 msm8994 所属的 B-family 块中
> **无条件设置**（`MULTIPLE_HW_VARIANTS_ENABLED := true`）；本文作者只核对了设备树的
> `AUDIO_FEATURE_*` 开关，漏掉了 Android.mk 自身设置的这一行。
>
> 后果是**功能性的，不是形式上的**：
> `audio_extn.h:189` 在未定义 `HW_VARIANTS_ENABLED` 时把 `hw_info_init()` 定义为 `(0)`，
> 于是 `platform.c:1213` 的 `my_data->hw_info` 恒为 0，`if (!my_data->hw_info)` 恒真，
> **整个 `else` 分支——包含 `audio_route_init()` 与 mixer XML 加载——成为死代码被消除。**
>
> 因此 §7「122 个未解析符号 100% 由设备库满足、缺失 0」虽然字面为真，
> **却是一个假象**：符号之所以全部闭合，是因为一大块逻辑根本没有被编译进去。
> 首版产物 `cac5689f…2ee44` 是一个 `platform_init` 残废的模块，**不具备任何参考价值**。
>
> 该缺陷由 agy 任务 J112 在做编译选项考古时发现并明确上报，随后由本人逐条核验证实。
> 这是本轮委派中唯一一次外部代理推翻了协调者自己的结论。
>
> 更正后的结果见文末 §11。原 §1–§10 内容保留，作为错误记录。

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


---

# 11. 更正后的构建与结果（权威版本）

## 11.1 修正内容

在 §4 的编译配置基础上追加：

- `-DHW_VARIANTS_ENABLED` 与源文件 `hal/msm8974/hw_info.c`（源文件数 11 → **12**）
  —— 修正 §「更正」所述的死代码消除缺陷
- `-D_FORTIFY_SOURCE=2 -fstack-protector-strong` —— 依 agy J112 的二进制考古
  （出厂模块含 `__memcpy_chk` / `__strlcat_chk` / `__strlcpy_chk` / `__vsnprintf_chk`；
  `__stack_chk_fail` 调用计数：出厂 75，`-fstack-protector` 44，`-strong` 72，`-all` 276）
- 链接加 `crtbegin_so.o` / `crtend_so.o`（真 bionic 源码编出）与 `--gc-sections`
  —— 依 agy J111。`--gc-sections` 是关键：它回收未被调用的 `atexit` / `pthread_atfork`，
  使新增未解析符号只有 `__cxa_finalize` 一个，**与出厂模块「有 `__cxa_finalize`、
  无 `__cxa_atexit`」精确一致**。另两个 agy 任务未加 `--gc-sections`，多引入了
  `__cxa_atexit` 与 `__register_atfork`，与出厂不符。

## 11.2 死代码消除的实证

| 符号 | 修正前 | 修正后 | 出厂 |
|---|---|---|---|
| `audio_route_init` | 无 | **有** | 有 |
| `dlerror` | 无 | **有** | 有 |
| `malloc` | 无 | **有** | 有 |
| `__android_log_assert` | 无 | **有** | 有 |
| `__cxa_finalize` | 无 | **有** | 有 |
| `__open_2` | 无 | **有**（FORTIFY 后） | 有 |

## 11.3 更正后产物与出厂模块的差分

产物 SHA256 `7f8b2e7388597b91d0a31caf89080089d5849e2ed1d81080a162d42272925034`

| 检查 | 结果 |
|---|---|
| SONAME | 一致 |
| `DT_NEEDED` | 11 项（出厂 12，多 `libc++.so`，属 Android 构建系统默认追加） |
| 导出 `HMI` | 是 |
| 导出符号交集 | **183**（首版 180） |
| `.fini_array` | 有，2 项 `__on_dlclose` / `__on_dlclose_late` |
| 未解析符号闭合 | **0 个不可由设备 12 库满足** |

双向符号差异已 100% 归因：

- **出厂有本次无：1 个** —— `memset`
- **本次有出厂无：12 个** —— 7 个 `__aeabi_*`（`idiv`/`ldivmod`/`memclr`/`memclr8`/
  `memset8`/`uidiv`/`uidivmod`）与上一条是同一件事的两面：Apple clang 21 把 `memset`
  等降级为 ARM EABI 内建，出厂用的 Android clang 保留了 `memset`；
  5 个为 M3 新引入（`mixer_ctl_get_enum_string`、`mixer_ctl_get_value`、
  `property_set`、`stat`、`strerror`）

## 11.4 feature-OFF 等价性（agy J113，已由本人独立复核）

打过 5 个 M3 补丁但关闭 `LEO_HIFI_ENABLED` 的树，与未打补丁的 `7f4cac74` 干净树，
**分别构建链接后的 `.so` 逐字节相同**，SHA256 `7bd528bcd181a09352b254cc4e9db6e9f5e6f7bc02f6929e09ac1c33a6255b39`。

复核方法：先证伪「两棵树其实是同一棵」这一假阳性路径（实测两树有 4 个改动文件 +
2 个新增文件），再逐个 `cmp` 10 个 `.o` 全部相同、最终 `.so` `cmp` 逐字节相同、
`leo_hifi.o` 正确缺席。

项目此前只在 **token 层**验证过 feature-OFF 等价，**本次是链接产物层的逐字节等价**。

## 11.5 仍未闭合

1. `memset` ↔ `__aeabi_*` 的编译器降级差异 —— 属工具链差异（Apple clang 21 vs
   Android clang），不是配置错误，除非换用 Android 官方 clang 否则无法消除。
2. `libc++.so` 未出现在 `DT_NEEDED` —— 出厂由构建系统默认追加，本模块是纯 C，
   未验证其必要性。
3. **未加载验证。** 产物从未被 `dlopen`、从未由 audioserver 加载、从未在设备上运行。
   **链接成功 ≠ 可加载 ≠ 可播放。**
4. 出厂模块另有 `.note.gnu.build-id` 与 `.gnu_debugdata` 两个 section，本次产物无。
5. Gate 3（ROM 集成、离线镜像审计、回退材料）全部未开始。

## 11.6 方法论教训

首版那个错误能通过全部形式检查——编译无错、链接成功、SONAME 正确、导出 `HMI`、
符号闭合 100%——**却是一个功能上残废的模块**。

「符号全部闭合」在存在死代码消除时是一个**危险的伪指标**：缺的代码不会产生
未解析符号，只会安静地消失。今后凡以符号闭合作为门禁，必须同时核对
**关键符号是否存在**（如本例的 `audio_route_init`），而不只看「有没有解析不了的」。
