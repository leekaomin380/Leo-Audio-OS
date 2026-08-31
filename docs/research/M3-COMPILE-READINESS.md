# M3 编译就绪度

日期：2026-08-29
结论先行：**未证明可编译。** 补丁系列**不可上机**。

---

## 1. 达到的验证等级

任务给出的三级优先级，本轮达到的是**第 2 级的一部分 + 一个额外的运行级 host mock**。

| 级别 | 要求 | 本轮 | 说明 |
| --- | --- | --- | --- |
| 1 真实模块编译 | 用锁定源码 + 最小依赖构建 `audio.primary.msm8994.so` | **未达成** | 缺 Android 构建系统与平台头文件，见 §3 |
| 2 预处理 / 语法检查 | clang/gcc 对补丁文件做语法与类型检查 | **部分达成** | `leo_hifi.c` 通过严格编译；`platform.c` / `audio_hw.c` **未通过编译器**，只做了 token 级比对 |
| 3 依赖闭包 | include / symbol / build 依赖清单 | **达成** | §2、§3 |
| （额外） | host mock 逻辑执行 | **达成** | 88/88，见 `tests/host-mock-leo-hifi/` |

### 明确不算"编译成功"的事项

以下都**不是**编译验证，本文与提交信息中均不作此声明：

* `git apply --check` / `git apply`
* `sh -n`
* grep 静态合同检查（`verify-m3-patch-contract.sh`）
* token 级等价比对（`verify-m3-flag-off-equivalence.sh`）
* host mock 的编译与运行（它编译的是 `leo_hifi.c` **对 mock 头文件**，不是对 Android 头文件）

---

## 2. 已经通过编译器的部分

对象：补丁应用后的 `hal/msm8974/leo_hifi.c`（新文件，658 行）。

```sh
clang -std=c99 -Wall -Wextra -Wno-unused-parameter -Wshadow -Wsign-compare \
      -Wformat=2 -c leo_hifi.c -I <mock-include> -I . \
      -DLEO_ESS_SYSFS_DRIVER='"/tmp/leo-ess-mock/driver"' -o leo_hifi.o
# exit 0, 零告警
```

mock 头文件只提供 `leo_hifi.c` 实际使用的接口，签名逐字取自
AOSP `external/tinyalsa` `android-10.0.0_r47` 的 `include/tinyalsa/asoundlib.h`：

```c
struct mixer_ctl *mixer_get_ctl_by_name(struct mixer *mixer, const char *name);
int         mixer_ctl_get_value(struct mixer_ctl *ctl, unsigned int id);
const char *mixer_ctl_get_enum_string(struct mixer_ctl *ctl, unsigned int enum_id);
int         mixer_ctl_set_array(struct mixer_ctl *ctl, const void *array, size_t count);
int         mixer_ctl_set_enum_by_string(struct mixer_ctl *ctl, const char *string);
unsigned int mixer_ctl_get_num_values(struct mixer_ctl *ctl);
```

`leo_hifi.o` 的未定义符号闭包（即该文件对外的全部依赖）：

```text
tinyalsa : mixer_get_ctl_by_name  mixer_ctl_get_value  mixer_ctl_get_enum_string
           mixer_ctl_set_array    mixer_ctl_set_enum_by_string
libcutils: property_get  property_set
liblog   : (宏，展开为 __android_log_print)
libc     : atoi snprintf strcmp memset stat usleep
```

**没有隐藏依赖**：没有 `dlopen`、没有线程、没有文件写入、没有 `system()`。

### 尚未通过编译器的部分

`hal/msm8974/platform.c` 与 `hal/audio_hw.c` 的改动。它们的正确性目前依赖于：

* `git apply` 成功（上下文匹配）；
* `verify-m3-flag-off-equivalence.sh` 证明 flag 关闭时与上游逐 token 相同；
* 人工审阅（见 `M3-PATCH-AUTHOR-SELF-AUDIT.md` §3 的编译边界表）。

**这不足以排除编译错误。** 具体风险：

1. `platform.c` 中新增的 `struct listnode *node; struct audio_usecase *uc;`
   在 C99 下声明于块首，语法无误，但 `list_for_each` / `node_to_item` 宏来自
   `cutils/list.h`，其展开未被编译器检查过；
2. `audio_hw.c` 里 `#include "leo_hifi.h"` 依赖 `LOCAL_C_INCLUDES` 中的
   `$(LOCAL_PATH)/$(AUDIO_PLATFORM)`（Android.mk:243），路径正确性未经构建验证；
3. `platform_leo_hifi_*` 的四个声明在 `leo_hifi.h`，定义在 `platform.c`。
   若上游约定要求 platform 层导出必须走 `platform_api.h`，链接虽然会成功，
   但可能不符合代码规范——`platform_api.h` 本轮未取得审阅。

---

## 3. 达成第 1 级还缺什么

### 3.1 缺失的工具链

| 项目 | 说明 |
| --- | --- |
| Android 10 构建系统 | `build/soong` + `build/make`，`Android.mk` 需要 `BUILD_SHARED_LIBRARY`、`include-path-for` 等 |
| 目标 clang | AOSP `prebuilts/clang/host/linux-x86`（Android 10 用 clang-r353983c 一代） |
| Bionic sysroot | 32-bit `armeabi-v7a`，API 29 |
| 构建主机 | **Linux x86_64**。当前主机是 macOS 26/arm64，AOSP 构建系统不支持 |

### 3.2 缺失的头文件与生成物（`platform.c` / `audio_hw.c` 的直接 include 闭包）

```text
系统 / bionic   errno.h pthread.h stdint.h stdlib.h math.h dlfcn.h fcntl.h
                sys/{time,resource,prctl,ioctl}.h

libcutils       cutils/{str_parms,properties,atomic,sched_policy,list}.h
liblog          log/log.h
libhardware     hardware/{audio,audio_effect,audio_amplifier}.h        ← LOCAL_HEADER_LIBRARIES := libhardware_headers
system/media    system/audio.h  system/thread_defs.h
                audio_effects/effect_{aec,ns}.h
external        tinyalsa/asoundlib.h  tinycompress/tinycompress.h  expat.h
audio-route     audio_route/audio_route.h                            ← $(call include-path-for, audio-route)
内核生成头       sound/compress_params.h  sound/asound.h  sound/msmcal-hwdep.h
                                                                     ← LOCAL_HEADER_LIBRARIES := generated_kernel_headers
仓库内           audio_hw.h audio_defs.h voice.h platform.h platform_api.h
                edid.h audio_extn/audio_extn.h voice_extn/voice_extn.h
```

`generated_kernel_headers` 是**构建期生成**的，来自 `kernel/xiaomi/msm8994` 的
`make headers_install`；离线无法凭空提供。

### 3.3 需要的 Android / CAF 依赖仓库

| 路径 | 仓库 / 分支 |
| --- | --- |
| `hardware/qcom-caf/msm8994/audio` | `MoKee/android_hardware_qcom_audio` @ `mkq-mr1-caf-msm8994`（已锁定，本轮已克隆） |
| `device/xiaomi/leo` | `MoKee/android_device_xiaomi_leo` @ `mkq-mr1`（`b994edcc`） |
| `device/xiaomi/msm8994-common` | `MoKee/android_device_xiaomi_msm8994-common` |
| `vendor/xiaomi/leo` | 私有 vendor blobs，**不进公开仓库**，需设备所有者本地提取 |
| `kernel/xiaomi/msm8994` | 生成 `generated_kernel_headers` |
| AOSP / MoKee 平台树 | `system/core`、`hardware/libhardware`、`external/tinyalsa`、`external/tinycompress`、`external/expat`、`system/media`、`build/*` |

### 3.4 最小构建主机资源

| 资源 | 最小值 | 说明 |
| --- | --- | --- |
| OS | Linux x86_64（Ubuntu 20.04 一代） | AOSP 构建系统不支持 macOS/arm64 |
| 磁盘 | **≥ 250 GiB** 完整同步；只做本模块的裁剪同步约 **60–80 GiB** | `docs/16` §14 的 6 GiB 停止线在当前 Mac 上必然触发，因此这一步必须换主机 |
| 内存 | ≥ 16 GiB | |
| 同步后剩余空间 | ≥ 6 GiB | 沿用 `docs/16` 的停止条件 |

### 3.5 下一条精确命令

在满足 §3.4 的 Linux 主机上，取得完整树之后：

```bash
source build/envsetup.sh
lunch mokee_leo-userdebug
mmma hardware/qcom-caf/msm8994/audio/hal -j8
```

产物应为
`out/target/product/leo/obj_arm/SHARED_LIBRARIES/audio.primary.msm8994_intermediates/LINKED/audio.primary.msm8994.so`
（32-bit）。M3-0 的完成判据是：**先在不打补丁的情况下**跑一遍，
把产物与设备上的 `701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47`
做符号级/节区级对照，差异逐项可解释；**之后**才打补丁。

---

## 4. 哪些错误会是补丁引入的，哪些只是环境缺失

真正运行 §3.5 之前，用这张表分类首轮编译错误：

| 症状 | 归类 |
| --- | --- |
| `fatal error: 'sound/compress_params.h' file not found` | **环境**（`generated_kernel_headers` 未生成） |
| `fatal error: 'audio_route/audio_route.h' file not found` | **环境**（`include-path-for` 未解析） |
| `fatal error: 'leo_hifi.h' file not found`（来自 `audio_hw.c`） | **补丁**（`LOCAL_C_INCLUDES` 的 `$(AUDIO_PLATFORM)` 路径假设不成立） |
| `implicit declaration of function 'platform_leo_hifi_*'` | **补丁**（`#ifdef` 括入了声明或包含顺序错） |
| `undefined reference to 'leo_hifi_*'` | **补丁**（`AUDIO_FEATURE_ENABLED_LEO_HIFI` 已开但 `leo_hifi.c` 未进 `LOCAL_SRC_FILES`，或内层 `AUDIO_PLATFORM` 守卫误判） |
| `error: 'leo_assert_hifi_dev_in_out_range' declared as an array with a negative size` | **补丁**（枚举被插到 OUT 段之外，或 OUT/IN 边界被破坏）——这正是该断言存在的目的 |
| `-Werror` 触发的 `unused-function` / `sign-compare` | **补丁**（但 `leo_hifi.c` 已在 `-Wall -Wextra -Wshadow -Wsign-compare -Wformat=2` 下零告警） |
| `error: 'SND_DEVICE_OUT_LEO_HIFI_HEADPHONES' undeclared`（在 flag 关闭的构建里） | **补丁**（有引用漏在 `#ifdef` 外）——`verify-m3-patch-contract.sh` 与 `verify-m3-flag-off-equivalence.sh` 现在覆盖这一类 |

---

## 5. 结论声明

* **未证明可编译（not proven buildable）。** 只有新文件 `leo_hifi.c` 通过了对 mock 头文件的
  严格语法/类型检查；两个上游文件的改动**没有经过任何编译器**。
* **不可上机（not flashable）。** 没有构建产物，M3-0 未开始，写入前 GO 条件
  （`docs/19` §13.2）一条都不满足。
* 最终裁决保留给 Codex。
