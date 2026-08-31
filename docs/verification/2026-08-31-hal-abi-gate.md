# HAL ABI 门判定 —— 2026-08-31

判定对象：`outputs/hifi-eight-way-20260831/diagnostic-candidates/final-hal-on/audio.primary.msm8994.so`
（SHA256 `bfd4c93471c78fc24cd4e9d4a862b69119bf734caec13595fcc4eeaeafa01c3d`，232036 B，未 strip）

对照基准：设备现役 `/system/vendor/lib/hw/audio.primary.msm8994.so`
（SHA256 `701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47`，175296 B，已 strip）

设备 `68f5f468` / `mokee_leo` / MK100.0-leo-221019-RELEASE / Android 10 / msm8994。
**全程只读**：`adb pull` 与 `adb shell` 查询，未写入任何内容。

---

## 结论

**GO —— 候选可被 `dlopen` 成功加载。但它是降级构建，只能作为功能探针，不能作为最终交付。**

| 门 | 结果 | 依据 |
|---|---|---|
| 符号可解析性 | ✅ **133/133** | 严格 NEEDED 传递闭包内逐符号判定，零缺口 |
| 浮点调用约定 | ✅ 完全一致 | `e_flags` 双方均 `0x05000200`；`Tag_ABI_VFP_args` 双方均缺席（base standard） |
| 文本重定位 | ✅ 双方均无 `DT_TEXTREL` | Android 10 会拒绝含 TEXTREL 的库 |
| 栈权限 | ✅ 双方 `PT_GNU_STACK` 均不可执行 | |
| RELRO | ✅ 双方均有 `PT_GNU_RELRO` | |
| 结构性 ABI 标注 | ✅ 一致 | `Tag_ABI_enum_size=2`、`align_needed=1`、`PCS_wchar_t=4` |
| 架构基线 | ⚠️ 降级但安全 | 候选 ARMv7 / 原版 ARMv8-A(cortex-a53)；ARMv7 是 AArch32 子集，向下兼容 |
| 立即绑定加固 | ⚠️ 降级 | 原版 `DT_FLAGS=0x8`(BIND_NOW)、`DT_FLAGS_1=0x1`(DF_1_NOW)；候选均为 `0x0`（惰性绑定）。非加载失败，是加固回退 |
| 导出完整性 | ⚠️ 功能回归 | 候选缺 8 个原版导出符号，全部属 sound-trigger 集成 |
| `libc++.so` 直接 NEEDED | ✅ 无害 | 经 `libcutils`/`libprocessgroup`/`libtinycompress` 传递引入；无任何符号只由它提供 |

---

## 符号差异的精确构成

候选相对原版**多出 14 个未定义符号**，**少 1 个**（`memset`），净 +13：

**A 组 —— 编译器辅助例程（8 个）**
`__aeabi_idiv` `__aeabi_uidiv` `__aeabi_uidivmod` `__aeabi_ldivmod` `__aeabi_uldivmod`
`__aeabi_memclr` `__aeabi_memclr8` `__aeabi_memset8`

原版**自身静态定义**了这些（libgcc 被静态链入）；候选把它们留作动态解析。
起初判断这会导致 `dlopen` 失败——**该判断被实测推翻**：这台设备的 Bionic `libc.so`
导出了全部 8 个（`__aeabi_idiv` 仅 libc 提供；其余 `libc++`/`libprocessgroup`/`libtinycompress` 也提供）。

**B 组 —— M3 补丁引入的真实调用（6 个）**
`mixer_ctl_get_value` `mixer_ctl_get_enum_string` `pcm_get_buffer_size`（libtinyalsa）
`property_set`（libcutils）`stat` `strerror`（libc）
三个库均已在候选的直接 NEEDED 中，正常解析。

候选**新导出** 22 个 `leo_hifi_*` / `platform_leo_hifi_*` 符号，即 M3 的实现面。

## 缺失的导出符号

候选未导出、原版导出：
```
audio_hw_call_back
audio_extn_sound_trigger_init / deinit / check_and_get_session
audio_extn_sound_trigger_set_parameters / stop_lab
audio_extn_sound_trigger_update_device_status / update_stream_status
```
另有 `__divdi3` `__divmoddi4` `__udivmoddi4` `__udivmodsi4` `__udivsi3` 等编译器例程
（原版静态链入的副产物，非接口）。

**核查结论：不会导致加载失败。**拉取设备上的 `sound_trigger.primary.msm8994.so` 分析，
它**不从外部引用**这族符号中的任何一个（该 HAL 与 audio HAL 之间走 dlopen + 函数指针，
不走动态符号绑定）。因此这是**功能回归**——候选在 sound-trigger 支持被编译掉的配置下构建，
部署后热词/语音唤醒相关能力会失效——而不是加载障碍。

## `.ARM.attributes` 逐 tag 比对

| 属性 | 候选 | 原版 | 定性 |
|---|---|---|---|
| `Tag_CPU_name` | — | `cortex-a53` | 仅标注 |
| `Tag_CPU_arch` | 10 (ARMv7) | 14 (ARMv8-A) | 候选基线更低，向下兼容 |
| `Tag_FP_arch` | 3 (VFPv3-D16) | 继承 v8 | 同上 |
| `Tag_Advanced_SIMD_arch` | 1 (NEONv1) | 3 (NEON for ARMv8) | 同上 |
| **`Tag_ABI_VFP_args`** | **缺席** | **缺席** | ✅ 双方 base standard，**传参约定一致** |
| `Tag_ABI_enum_size` | 2 | 2 | ✅ |
| `Tag_ABI_align_needed` | 1 | 1 | ✅ |
| `Tag_ABI_PCS_wchar_t` | 4 | 4 | ✅ |
| `Tag_ABI_FP_exceptions` | 0 | 1 | 仅表示代码是否使用 FP 异常，链接期无影响 |
| `Tag_MPextension_use` / `Virtualization_use` / `FP_HP_extension` | 无 | 1 / 3 / 1 | 候选未启用扩展 |

`Tag_ABI_VFP_args` 是唯一会造成**静默数据损坏**的属性（决定浮点参数走 VFP 寄存器还是核心寄存器）。
双方都缺席，即都用 base standard，与 `e_flags` 的 soft-float ABI 位一致。这一项是干净的。

---

## 这对路线选择意味着什么

候选的三处降级——ARMv7 基线、无 BIND_NOW、sound-trigger 编译掉——**同源于一个原因：
它不是用 MoKee/AOSP 的构建配置产出的**，而是主机工具链在部分源码集上的诊断产物。
交接文档把它标为 `diagnostic-candidates` 是准确的。

因此：

- **可以**用它做一次 Stage 2 功能验证，证明 schema3 端到端链路工作。风险受控，回退材料已逐字节核实。
- **不能**把它当最终交付。最终 `.so` 必须用 `lunch mokee_leo-userdebug && mka audio.primary.msm8994`
  在真实源码树上产出。Phase 0 已证明该树完整可得（`MoKee/android` @ `mkq-mr1`，654 projects，
  aosp 500 走 googlesource 钉 `android-10.0.0_r41`，mokee 154 走 GitHub）。
- 该单模块构建**远小于整 ROM**，但仍需 Linux 主机与完整源码树——macOS 本机做不到。
  这与用户已在考虑的云构建方案合流。

## 附带确定的两件事

**lib64 是死代码。**全进程扫描 `/proc/*/maps`，只有 pid 6379
（`/vendor/bin/hw/android.hardware.audio@2.0-service`）映射 HAL，且只映射 32 位那份；
该进程零个 lib64 映射。设备上只有一个音频 HAL 服务二进制且是 32 位。
→ Stage 2 只替换 32 位版本；lib64 保持不动，部署脚本对其尺寸 187784 做不变量断言。

**重启链路。**`vendor.audio-hal-2-0` 是 `oneshot`，杀掉不会被 init 自动拉起。
但 `audioserver` 的 init 定义含 `onrestart restart vendor.audio-hal-2-0`，
故 `setprop ctl.restart audioserver` 一条命令即可级联重启两者。部署与回退脚本均走这条路径。
