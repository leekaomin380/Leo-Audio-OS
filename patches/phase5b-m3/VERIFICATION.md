# 离线验证记录（M3 补丁、源码布局、feature-OFF 等价性、故障注入）

日期：2026-08-29（第二轮：作者自审后重跑）
环境：macOS 26 / arm64，clang 17。**无 Android 构建环境；未编译 HAL 模块；未连接设备。**

## 1. 干净审计环境

```
$ git clone --depth 1 --branch mkq-mr1-caf-msm8994 \
        https://github.com/MoKee/android_hardware_qcom_audio.git src
remote: https://github.com/MoKee/android_hardware_qcom_audio.git
HEAD  : 7f4cac748b6f62897294cdaece9d1aec27e1e927
branch: mkq-mr1-caf-msm8994
克隆后工作树 dirty 条目数: 0
```

> 未复用任何已打过补丁的目录；另有一份同 commit 的 pristine 克隆用于 feature-OFF 比对。

## 2. `sh -n` 语法检查

```
$ sh -n scripts/verify-m3-source-layout.sh
  ok
$ sh -n scripts/verify-m3-patch-contract.sh
  ok
$ sh -n scripts/verify-m3-flag-off-equivalence.sh
  ok
$ sh -n tests/host-mock-leo-hifi/run.sh
  ok
```

## 3. `git apply --check` + 实际应用 + `git diff --check`

```
$ git apply --check 0001-leo-add-symbolic-hifi-device.patch
  APPLIES
$ git apply --check 0002-leo-add-hifi-route-controller.patch
  APPLIES
$ git apply --check 0003-leo-add-volume-state-and-readback.patch
  APPLIES
$ git apply --check 0004-leo-make-quat-backend-deterministic.patch
  APPLIES
$ git apply --check 0005-leo-add-status-and-fallback.patch
  APPLIES
$ git diff --cached --check
  clean
```

## 4. `scripts/verify-m3-patch-contract.sh`

```
$ sh scripts/verify-m3-patch-contract.sh patches/phase5b-m3
series: patches/phase5b-m3/0001-leo-add-symbolic-hifi-device.patch patches/phase5b-m3/0002-leo-add-hifi-route-controller.patch patches/phase5b-m3/0003-leo-add-volume-state-and-readback.patch patches/phase5b-m3/0004-leo-make-quat-backend-deterministic.patch patches/phase5b-m3/0005-leo-add-status-and-fallback.patch
added source lines: 1248 (non-comment: 862)

PASS: no numeric snd_device assignment or comparison
PASS: no literal usecase->id comparison (comments excluded)
PASS: MIUI device number 34 appears only in comments, never in code
PASS: platform_check_hifi_backend_cfg is not referenced
PASS: entry hook is platform_leo_hifi_snd_device_enabled (enable_snd_device)
PASS: no guard on the stale usecase->out_snd_device
PASS: changes to upstream files are wrapped in #ifdef LEO_HIFI_ENABLED
PASS: dB logging goes through the sign-safe helper
PASS: no abs()-based dB formatting
PASS: KHZ_48 target defined
PASS: S24_LE target defined
PASS: backend writer leo_hifi_set_backend present
PASS: exit-side backend restore present (disable_audio_route)
PASS: no usecase gating at all (backend is pinned per device) -- rule not applicable
PASS: volume clamp bounds present
PASS: volume read-back present
PASS: volume failure fallback to the factory floor present
PASS: no 213/225/229 product default before R6/R7
PASS: HiFi device keeps acdb id -1 (no borrowed calibration)
PASS: bypass assertion covers 'SLIMBUS_0_RX Audio Mixer MultiMedia'
PASS: bypass assertion covers 'HPHL DAC Switch'
PASS: bypass assertion covers 'SLIM RX1 MUX'
PASS: bypass assertion covers 'SLIM RX2 MUX'
PASS: bypass assertion covers 'RX1 MIX1 INP1'
PASS: bypass assertion covers 'RX2 MIX1 INP1'
PASS: bypass assertion covers 'CLASS_H_DSM MUX'
PASS: bypass assertion covers 'QUAT_MI2S_RX Audio Mixer MultiMedia'
PASS: fatal evidence mask present
PASS: bypass fatal mask is separate from the observation mask
PASS: E4 (a QUAT front end really came up) is an evidence bit
PASS: leo-specific build flag LEO_HIFI_ENABLED present
PASS: runtime default is OFF
PASS: no shell-out from the HAL
PASS: no binary-patching machinery

verify-m3-patch-contract: ALL CHECKS PASSED
NOTE: this proves contract compliance only; the series is UNCOMPILED
      and UNVERIFIED on hardware.
exit=0
```

## 5. `scripts/verify-m3-source-layout.sh`

```
$ sh scripts/verify-m3-source-layout.sh <pristine> <device audio.primary.msm8994.so>
PASS: parsed 35 SND_DEVICE_OUT_* symbols from platform.h
PASS: every SND_DEVICE_OUT_* symbol has at least one designated table entry
SKIP: SND_DEVICE_OUT_LEO_HIFI_HEADPHONES not present (unpatched baseline)
PASS: source device_table matches the binary at all 97 indices below the insertion point

verify-m3-source-layout: ALL CHECKS PASSED
exit=0

$ sh scripts/verify-m3-source-layout.sh <patched> <device audio.primary.msm8994.so>
PASS: parsed 36 SND_DEVICE_OUT_* symbols from platform.h
PASS: every SND_DEVICE_OUT_* symbol has at least one designated table entry
PASS: device_table[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES] = "hifi-headphones"
PASS: acdb_device_table[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES] = -1 (no borrowed calibration)
PASS: snd_device_name_index contains SND_DEVICE_OUT_LEO_HIFI_HEADPHONES
PASS: SND_DEVICE_OUT_LEO_HIFI_HEADPHONES is the last OUT entry (no existing index moves)
PASS: compile-time range guard present
PASS: source device_table matches the binary at all 36 indices below the insertion point
PASS: every entry above the insertion point is a clean +1 shift (only the new device was added)
PASS: inserted device is 'hifi-headphones' at index 36

verify-m3-source-layout: ALL CHECKS PASSED
exit=0
```

## 6. `scripts/verify-m3-flag-off-equivalence.sh`（新增）

```
$ sh scripts/verify-m3-flag-off-equivalence.sh <patched> <pristine>
platform.h                     TOKEN-IDENTICAL (796 tokens)
platform.c                     TOKEN-IDENTICAL (10830 tokens)
audio_hw.c                     TOKEN-IDENTICAL (10044 tokens)

verify-m3-flag-off-equivalence: FEATURE OFF IS TOKEN-IDENTICAL TO STOCK
exit=0
```

> 这是 feature flag 关闭时"与原版 MoKee 完全一致"的最强形式：
> 去掉 `#ifdef LEO_HIFI_ENABLED` 块后，三个被改动的上游文件与基线**逐 token 相同**。

## 7. `tests/host-mock-leo-hifi/run.sh`（新增，故障注入）

```
$ sh tests/host-mock-leo-hifi/run.sh research-cache/audit2/src
== strict syntax/type gate on the unmodified leo_hifi.c ==
   clean (no warnings)
== undefined symbols required by leo_hifi.o ==
   ___memset_chk
   ___snprintf_chk
   ___stack_chk_fail
   ___stack_chk_guard
   ___stderrp
   _atoi
   _fprintf
   _fputc
   _leo_log_count
   _mixer_ctl_get_enum_string
   _mixer_ctl_get_value
   _mixer_ctl_set_array
   _mixer_ctl_set_enum_by_string
   _mixer_get_ctl_by_name
   _property_get
   _property_set
   _stat
   _strcmp
   _usleep
== build and run the fault-injection scenarios ==
== S0  dB formatting boundaries (sign-safe integer path) ==
== S1  runtime flag OFF: controller never selects HiFi ==
== S2  nominal enable -> HIFI_ACTIVE ==
== S3  Volume control missing ==
== S4  QUAT SampleRate control missing ==
== S5  QUAT BitWidth control missing ==
== S6  ESS sysfs absent, then late re-probe ==
== S6b re-probe budget is bounded ==
== S6c structural mismatch is permanent, never retried ==
== S7  write succeeds but read-back diverges ==
== S8  Volume request out of range ==
== S8b in-range apply ramps and lands exactly ==
== S9  backend half-set: BitWidth ok, SampleRate write fails ==
== S9b backend enum read-back diverges ==
== S10 MultiMedia5 appears, analog outlet cut -> recorded, NOT fatal ==
== S11 analog outlet open -> FATAL ==
== S12 second playback usecase on SLIMBUS with outlet open ==
```

> **host mock 不是 Android 构建**。它把补丁后的 `leo_hifi.c` 与 mock 的
> tinyalsa / property / log 接口链接起来，只验证决策逻辑。
> 22 组场景、88 条断言全部通过；场景清单见
> `docs/research/M3-PATCH-AUTHOR-SELF-AUDIT.md` §4。

## 8. 未做的检查

- **未做 Android 模块构建**：`platform.c` / `audio_hw.c` 的改动没有经过任何编译器；
- **未连接设备**：本轮零 `adb` / `fastboot`；
- 未审阅 `platform_api.h`、`audio_extn`、设备树 SELinux 侧；
- 四个脚本都只针对 MoKee `mkq-mr1-caf-msm8994` 的布局，脚本头部列出了全部假设，
  布局变化时报 “cannot parse” 而不是静默通过。
