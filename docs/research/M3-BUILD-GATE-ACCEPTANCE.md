# M3 构建门验收标准（独立审计）

日期：2026-08-29
角色：构建门**协调者与独立审计**（实际构建由 agy 在另一工作树执行）
唯一补丁基线：`research/claude-opus5-hifi-architecture` @ **`b99b728`**，
`patches/phase5b-m3/0001…0005`
源码基线：`MoKee/android_hardware_qcom_audio` @ `mkq-mr1-caf-msm8994`
HEAD `7f4cac748b6f62897294cdaece9d1aec27e1e927`
边界：本文不修改 main、不修改 agy 工作树、不产生写入授权。

---

## 0. 证据等级（六级，不得混称）

| 级 | 名称 | 判据 | 当前状态 |
| ---: | --- | --- | --- |
| **L1** | 语法检查通过 | 编译器接受源文件（可用 mock 头文件） | ✅ **已达成**，仅 `leo_hifi.c` |
| **L2** | ARM32 目标文件生成通过 | 用 Android 目标 clang + bionic sysroot 产出 `.o` | ❌ 未达成 |
| **L3** | Android HAL 模块编译通过 | `mmma hardware/qcom-caf/msm8994/audio/hal` 全部 `.c` 编译成功 | ❌ 未达成 |
| **L4** | 共享对象链接通过 | 产出 `audio.primary.msm8994.so`（32-bit ARM） | ❌ 未达成 |
| **L5** | ROM 集成通过 | 该 `.so` 进入可用的 `system` 镜像 | ❌ 未达成 |
| **L6** | 实机验证通过 | 设备上按验收矩阵实测 | ❌ 未达成 |

**明确不算任何一级的事项**：`git apply --check`、`sh -n`、grep 静态合同、
token 级等价比对、host mock 的编译与运行。
**L1 也不等于 L2**：`leo_hifi.c` 是对 **mock 头文件**编译的，不是对 bionic / AOSP 头文件。
**L2 生成 relocatable object ≠ L3/L4。**

---

## 1. `platform_api.h` 声明闭合性 —— **发现一处约定违背（非阻断，须在 L3 前修）**

`hal/platform_api.h`（122 行，`#ifndef AUDIO_PLATFORM_API_H`，无 `extern "C"`）是本树中
**platform 层向 `audio_hw.c` 暴露接口的唯一约定位置**。它已经声明了本系列涉及的全部上游接口：

```text
:29  platform_get_snd_device_name
:30  platform_get_snd_device_name_extn
:32  platform_add_backend_name
:60  platform_get_output_snd_device
:64  platform_get_parameters
:66  platform_set_parameters
:96  platform_check_and_set_codec_backend_cfg
:120 platform_check_backends_match
```

本系列新增的四个 platform 层导出**定义在 `msm8974/platform.c`，却声明在
`msm8974/leo_hifi.h`**：

```text
platform_leo_hifi_snd_device_enabled   platform.c:3592
platform_leo_hifi_backend_exit         platform.c:3610
platform_leo_hifi_route_enabled        platform.c:3548
platform_leo_hifi_route_disabled       platform.c:3559
```

`audio_hw.c` 因此需要 `#include "leo_hifi.h"`（在 `#ifdef LEO_HIFI_ENABLED` 内）。

**是否会导致编译失败：不会。** `LOCAL_C_INCLUDES` 含
`$(LOCAL_PATH)/$(AUDIO_PLATFORM)`（`Android.mk:243`），而 `LEO_HIFI_ENABLED`
只在 `AUDIO_PLATFORM = msm8974` 时定义，包含路径必然可解析。

**但这是方向倒置**：平台无关的 `audio_hw.c` 依赖了平台私有头文件。
一旦有人在 `AUDIO_PLATFORM != msm8974` 的板子上误设 `AUDIO_FEATURE_ENABLED_LEO_HIFI`，
内层守卫会阻止 `-DLEO_HIFI_ENABLED`，所以后果被围住了；但约定仍应纠正。

**要求（L3 完成前必须处理，作为后续 0006）**：
把四个原型移入 `platform_api.h` 的 `#ifdef LEO_HIFI_ENABLED` 块，
并从 `audio_hw.c` 删除 `#include "leo_hifi.h"`。
**本轮不改 `b99b728`**，以免在 agy 构建过程中移动基线。

---

## 2. Android.mk 源文件与条件编译

```makefile
# 位于 LOCAL_CFLAGS += -DUSE_VENDOR_EXTN 之后（Android.mk:50）
ifeq ($(strip $(AUDIO_FEATURE_ENABLED_LEO_HIFI)),true)
ifeq ($(strip $(AUDIO_PLATFORM)),msm8974)
    LOCAL_SRC_FILES += $(AUDIO_PLATFORM)/leo_hifi.c
    LOCAL_CFLAGS += -DLEO_HIFI_ENABLED
endif
endif
```

| 检查 | 结论 |
| --- | --- |
| 位置是否安全 | ✅ 平台 `LOCAL_CFLAGS :=` 覆盖链在 `Android.mk:16–37`，本块在 `:50` 之后，用 `+=`，不会抹掉 `-DPLATFORM_MSM8994` |
| 作用域 | ✅ **设备级**开关，不再牵连 msm8992 与其他共用 msm8974 平台源码的机型 |
| 源文件路径 | ✅ `$(AUDIO_PLATFORM)/leo_hifi.c` = `hal/msm8974/leo_hifi.c` |
| 双重守卫 | ✅ 外层设备意图、内层平台事实 |
| 需要的设备侧改动 | `device/xiaomi/leo/BoardConfig.mk` 增加 `AUDIO_FEATURE_ENABLED_LEO_HIFI := true`（**不在本系列内**，属设备树，必须单独记录） |

**构建门必须验证的负向用例**：不设该 flag 时，`leo_hifi.c` 不进 `LOCAL_SRC_FILES`，
`-DLEO_HIFI_ENABLED` 不出现在编译命令行。可用 `mmma … showcommands` 或
`out/.../import_includes` / `.o` 列表核对。

---

## 3. `LEO_HIFI_ENABLED` 的定义、传播与作用域

| 项 | 结论 |
| --- | --- |
| 定义点 | 只有 Android.mk 上述一处 |
| 传播 | 模块级 `LOCAL_CFLAGS`，本模块所有 `.c` 统一，**不存在同一模块内部分 TU 有、部分没有**的 ODR 风险 |
| 覆盖的文件 | `platform.h`（枚举）、`platform.c`（表、结构体成员、四个导出、参数键）、`audio_hw.c`（三个调用点 + include）、`leo_hifi.c/h`（整文件） |
| 未被 `#ifdef` 覆盖的 leo 引用 | **0 处**（`verify-m3-patch-contract.sh` 与 `verify-m3-flag-off-equivalence.sh` 双重检查） |

---

## 4. 三个源文件的编译时风险

| 风险 | 结论 | 依据 |
| --- | --- | --- |
| 未声明函数（implicit declaration） | `leo_hifi.c` 零告警通过 `-Wall -Wextra -Wshadow -Wsign-compare -Wformat=2`；`platform.c` / `audio_hw.c` **未经编译器** | L1 记录 |
| 类型转换 | `mixer_ctl_get_value` 返回 `int`，传入 `mixer_ctl_get_enum_string` 前显式 `(unsigned int)` 且先判 `>= 0`；`snd_device_t` → `int` 显式转换 | 代码 |
| 重复符号 | 新增 16 个导出符号，前缀 `leo_hifi_` / `platform_leo_hifi_`；与设备上 `701019bd…` 的 71 个 `platform_*` 导出**零碰撞** | `objdump -T` |
| 文件内 static 泄漏 | `leo_ctl` / `leo_ctl_opt` / `leo_probe` / `leo_write_volume_ctl` / `leo_set_enum_checked` / `leo_state_name` / `leo_enum_is_live` / `leo_quat_front_end_live` / `leo_hifi_fallback` 全部 `static` | `nm -g` 只列出 12 个 T |
| 头文件循环 | `leo_hifi.h` 只含 `<stdbool.h> <stddef.h> <tinyalsa/asoundlib.h>` | 代码 |
| 负数组断言 | `leo_assert_hifi_dev_in_out_range` / `leo_assert_out_in_boundary`；**触发即为补丁缺陷**（枚举越出 OUT 段或 OUT/IN 边界被破坏） | 设计意图 |

---

## 5. 链接依赖与导出符号 —— 可核验的硬判据

### 5.1 `DT_NEEDED` 必须**完全不变**

`leo_hifi.c` 的外部依赖闭包只有 `liblog`（宏）、`libcutils`（`property_get/set`）、
`libtinyalsa`（5 个 `mixer_*`）、libc。三者都已在 `LOCAL_SHARED_LIBRARIES` 里。

设备上 `701019bd…` 的 `NEEDED` 集合（12 条）：

```text
liblog.so  libcutils.so  libhardware.so  libtinyalsa.so  libtinycompress.so
libaudioroute.so  libexpat.so  libprocessgroup.so  libc++.so  libc.so
libm.so  libdl.so
```

**判据 D1**：打补丁后的产物 `readelf -d` 的 `NEEDED` 集合必须与未打补丁产物**逐条相同**。
新增任何一条即为缺陷。

### 5.2 导出符号集合必须是"基线 + 恰好这 16 个"

`Android.mk` 无 version script、无 `-fvisibility`（`grep LOCAL_LDFLAGS|version_script|fvisibility` 零命中），
因此这些符号会以默认可见性导出：

```text
leo_hifi_init                     leo_hifi_route_wanted
leo_hifi_set_mode                 leo_hifi_ctl_to_db
leo_hifi_read_volume              leo_hifi_apply_volume
leo_hifi_restore_volume_floor     leo_hifi_set_backend
leo_hifi_check_bypass             leo_hifi_on_route
leo_hifi_on_route_off             leo_hifi_status_string
platform_leo_hifi_snd_device_enabled   platform_leo_hifi_backend_exit
platform_leo_hifi_route_enabled        platform_leo_hifi_route_disabled
```

（`leo_hifi_user_to_ctl` 是 `static inline`，不产生符号。）

**判据 D2**：
`objdump -T 打补丁产物` 的函数符号集合 = `objdump -T 未打补丁产物` 的集合 **∪ 上面 16 个**，
且**没有任何符号消失**。

---

## 6. feature OFF 等价性 —— 三层判据

| 层 | 判据 | 现状 |
| --- | --- | --- |
| 源码层 | 去掉 `#ifdef LEO_HIFI_ENABLED` 块后，`platform.h` / `platform.c` / `audio_hw.c` 与基线**逐 token 相同**（796 / 10830 / 10044） | ✅ `scripts/verify-m3-flag-off-equivalence.sh` |
| 目标文件层 | **不设** `AUDIO_FEATURE_ENABLED_LEO_HIFI` 构建，`platform.o` / `audio_hw.o` 与未打补丁构建**逐字节相同** | ⏳ 需 L3 |
| 共享对象层 | 同上条件下产出的 `.so` 与未打补丁构建**逐字节相同**（或至少符号表与 `NEEDED` 相同） | ⏳ 需 L4 |

**判据 D3（配对测试，构建门的核心）**：同一棵树、同一工具链，
**先不设 flag 构建一次**，产物必须与"完全不打补丁"的构建一致；
**再设 flag 构建一次**，产物必须满足 D1 + D2。
只有两次都通过，才能说"默认关闭时与原版 MoKee 等价"。

---

## 7. 如何证明产物来自最新补丁

构建完成后必须同时记录并满足：

| # | 证据 | 命令 |
| ---: | --- | --- |
| P1 | 源码树 HEAD | `git -C hardware/qcom-caf/msm8994/audio rev-parse HEAD` → `7f4cac74…` |
| P2 | 应用的补丁指纹 | `sha256sum patches/phase5b-m3/0*.patch`，并与 `b99b728` 中的文件逐一比对 |
| P3 | 树状态 | 打完补丁后 `git status --porcelain` 只列出预期的 6 个文件（`Android.mk`、`audio_hw.c`、`platform.c`、`platform.h`、新增 `leo_hifi.c/h`） |
| P4 | 产物指纹 | `sha256sum` 产出的 `audio.primary.msm8994.so`；**双次构建应一致**（沿用 Phase 3/4 的双构建规范） |
| P5 | 产物含本补丁的标记字符串 | `strings` 必须命中：`vendor.leo.audio.hifi.enable`、`vendor.leo.audio.hifi.volume`、`leo_hifi_status`、`hifi-headphones`、`QUAT_MI2S BitWidth`、`QUAT_MI2S SampleRate`、`/sys/bus/i2c/devices/6-0048/driver`、`acdb=absent_expected` |
| P6 | 产物含本轮修正的证据 | 必须存在 `platform_leo_hifi_snd_device_enabled` 导出符号（这是"进入钩子已移到 `enable_snd_device()`"的可验证痕迹）；**不得**存在任何 `platform_check_hifi_backend_cfg` 引用 |
| P7 | ABI | `file` 必须报 `ELF 32-bit LSB shared object, ARM`；`.note.android.ident` 的 API level 应为 29 |
| P8 | D1 / D2 / D3 | §5、§6 |

**P6 是区分"最新补丁"与上一版草案的关键**：上一版把钩子挂在
`platform_check_and_set_codec_backend_cfg()`，不会产生
`platform_leo_hifi_snd_device_enabled` 这个符号。

---

## 8. 本次 GO 裁决（逐层，不给笼统结论）

| 目标层 | 裁决 | 条件 |
| --- | --- | --- |
| **L1 语法检查** | **GO（已完成）** | 仅 `leo_hifi.c`，对 mock 头文件 |
| **L2 ARM32 目标文件** | **GO — 可以开始** | 前提：Linux x86_64 主机 + AOSP 工具链 + `generated_kernel_headers`；见 `M3-COMPILE-READINESS.md` §3 |
| **L3 HAL 模块编译** | **GO — 可以开始**，但必须同时跑 D3 的"不设 flag"配对构建 | 首轮错误按 `M3-COMPILE-READINESS.md` §4 的表分类为"补丁引入"或"环境缺失" |
| **L4 共享对象链接** | **条件 GO** | 必须满足 D1 + D2 + P1…P7 |
| **L5 ROM 集成** | **NO-GO** | L4 未完成；且 §1 的 `platform_api.h` 约定问题应先由 0006 修掉 |
| **L6 实机验证** | **NO-GO** | `docs/19` §13.2 写入前 GO 未满足；R7-B 未完成 |

**任何层的通过都不得被表述为"编译成功"或"可以刷机"。**
