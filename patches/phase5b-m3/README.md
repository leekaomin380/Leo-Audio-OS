# Phase 5B M3 — Leo HiFi Controller 补丁系列（草案）

状态：**可应用草案**（`git apply --check` 全绿），**未经编译、未经真机验证**。
日期：2026-08-29

---

## 1. 基线

```text
仓库    https://github.com/MoKee/android_hardware_qcom_audio
分支    mkq-mr1-caf-msm8994
commit  7f4cac748b6f62897294cdaece9d1aec27e1e927   (2020-01-14)
manifest MoKee/android @ mkq-mr1 : snippets/mokee.xml:114
         path="hardware/qcom-caf/msm8994/audio" revision="mkq-mr1-caf-msm8994"
设备树  https://github.com/MoKee/android_device_xiaomi_leo @ mkq-mr1 (b994edcc)
```

谱系定级为 **exact build provenance**，依据见
[`docs/research/M3-SOURCE-PROVENANCE.md`](../../docs/research/M3-SOURCE-PROVENANCE.md)。
目标产物是 **32-bit** `audio.primary.msm8994.so`（设备上运行的是
`701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47`）。

## 2. 应用方式

```bash
cd <aosp>/hardware/qcom-caf/msm8994/audio
git checkout 7f4cac748b6f62897294cdaece9d1aec27e1e927 -b leo-m3
git am /path/to/patches/phase5b-m3/000*.patch      # 或 git apply
```

顺序不可打乱：0002 引入的头文件被 0003/0004/0005 追加，0005 依赖 0004 的
`leo_hifi_set_backend()`。

## 3. 系列内容

| 补丁 | 内容 | 默认行为改变 |
| --- | --- | --- |
| `0001-leo-add-symbolic-hifi-device.patch` | `SND_DEVICE_OUT_LEO_HIFI_HEADPHONES` + `device_table` / `acdb_device_table`(-1) / `snd_device_name_index` + 两个 C89 编译期断言 | **无**（新设备无人选择） |
| `0002-leo-add-hifi-route-controller.patch` | 新增 `hal/msm8974/leo_hifi.{c,h}`；`platform_init` 控件预解析 + 自检 + ESS 绑定检查；`backend_tag_table` / `hw_interface_table`；`platform_get_output_snd_device` 分支；`leo_hifi_mode` 参数键；Android.mk + `-DLEO_HIFI_ENABLED` | **无**（`vendor.leo.audio.hifi.enable` 缺省 false） |
| `0003-leo-add-volume-state-and-readback.patch` | ES9018 `Volume` 的钳位、写入、读回、分帧、回退；`leo_hifi_volume` 参数键 | **无**（`platform_init` 不写 `Volume`，控件保持 `mixer_paths.xml` 的 205） |
| `0004-leo-make-quat-backend-deterministic.patch` | 进入侧挂 `enable_snd_device()`、退出侧挂 `disable_audio_route()`，两边确定性写入并读回 `S24_LE` / `KHZ_48` | **无**（只在 HiFi snd_device 上触发） |
| `0005-leo-add-status-and-fallback.patch` | 旁路观测（只有模拟出口致命）、E4（QUAT 前端读回）、状态机、generation、evidence/bypass bitmap、`leo_hifi_status` 只读接口、统一回退 | **无** |

## 4. 设计约束（逐条对应 `docs/19`）

| 约束 | 实现位置 |
| --- | --- |
| 默认功能关闭，原版行为不变 | `vendor.leo.audio.hifi.enable` 缺省 `false`；`leo_hifi_route_wanted()` 为假时 `platform_get_output_snd_device` 走原路径 |
| Leo 专属 feature flag | `LEO_HIFI_ENABLED`，仅在 `msm8994/msm8992` 的 Android.mk 分支定义；`platform.c` / `audio_hw.c` 的每处改动都被 `#ifdef` 包住，其他平台编译产物不变 |
| 不硬编码 MIUI 设备编号 34 | 全系列零裸数字；`leo_assert_hifi_dev_in_out_range` / `leo_assert_out_in_boundary` 编译期断言；`leo_hifi_init()` 运行期比对 `device_table` 名字，不符即本次 boot 彻底禁用 |
| 设备表/名称表/ACDB 表索引一致 | 三张表全部使用指定初始化器并同步追加；`snd_device_name_index` 按枚举顺序插入 |
| 不给 `hifi-headphones` 伪造 ACDB ID | `acdb_device_table[...] = -1` + 注释禁令；状态里报 `acdb=absent_expected` |
| 路由成功以读回为准 | `leo_hifi_on_route()` 的 evidence bitmap；`LEO_EV_FATAL_MASK` 不满足即 `ERROR_FALLBACK` |
| `Volume` 写入失败不阻断启动 | `platform_init` 不写 `Volume`；`leo_hifi_init()` 任何失败只置 `supported=false` 并返回 |
| R6/R7 前保持 205 | `platform_init` 只读 property 不应用；`LEO_HIFI_CTL_FLOOR = 205` 为绝对下限 |
| 进入/退出均显式恢复 `KHZ_48`/`S24_LE` | `platform_check_and_set_codec_backend_cfg`（进入，路由之前）+ `disable_audio_route`（退出，路由之后） |
| 不修改零调用者 `platform_check_hifi_backend_cfg` | 该符号在本基线中**根本不存在**；系列内 0 处引用 |
| 活路径挂在正确位置 | 后端进入：`select_devices()` → `enable_snd_device()`（`audio_hw.c:637`，第一次看到新设备，且早于 `enable_audio_route()` 启动 DAI）；后端退出：`disable_audio_route()`；状态机：`enable_audio_route()` 之后。**不挂 `platform_check_and_set_codec_backend_cfg()`**——那里 `usecase->out_snd_device` 还是旧设备 |
| offload 用语义判定 | M3 按**设备**钉后端，不按 usecase，故本系列无 offload 判定。M3.5 需要时必须用 `is_offload_usecase()`（`audio_hw.h:374` / `audio_hw.c:1333`），禁止写 `id == 3` |
| feature OFF 与上游等价 | **token 级相同**：`scripts/verify-m3-flag-off-equivalence.sh` 证明去掉 `#ifdef LEO_HIFI_ENABLED` 后 `platform.h` / `platform.c` / `audio_hw.c` 与上游逐 token 一致（796 / 10830 / 10044 tokens） |
| 禁止二进制 patch | 全系列为源码补丁 |

## 5. 尚未做的事（重要）

1. **未编译（Android）。** 本机没有 Android 构建环境。新文件 `leo_hifi.c` 已在
   `clang -std=c99 -Wall -Wextra -Wshadow -Wsign-compare -Wformat=2` 下**对 mock 头文件**
   零告警通过，并在 host mock 下跑完 22 组故障注入（88/88）；但
   `platform.c` / `audio_hw.c` 的改动**没有经过任何编译器**。
   详见 [`docs/research/M3-COMPILE-READINESS.md`](../../docs/research/M3-COMPILE-READINESS.md)。
2. **未真机验证。** 任何"路由已生效""音量已生效"的说法在 M3-B/M3-C 实测前都不成立。
3. **`platform_api.h` 未审阅**（本轮只下载了四个文件）。`platform_leo_hifi_*` 目前只在
   `leo_hifi.h` 声明；若上游要求 platform 层导出走 `platform_api.h`，M3-0 需相应调整。
4. **`struct stream_out` 偏移未对照 MoKee**。0004 不依赖流参数（固定 48 kHz），所以不受影响；
   M3.5 若要读 `out->sample_rate` 必须先核对。
5. **SELinix / `property_contexts` 未包含**（`docs/19` §9.4，属 device tree 侧，M3-D）。
6. **Status Service（binder）未包含**（M3-D）。

## 6. 回滚

第一层回滚不需要刷机：把 `vendor.leo.audio.hifi.enable` 置为 `false`，
`platform_get_output_snd_device()` 立即回到 `SND_DEVICE_OUT_HEADPHONES`。
第二层是撤回补丁重新构建。第三层才是按 `docs/18` 回滚 `system`。

> **[2026-08-29 更新]** `boot` 已持久写入 boot 分区（回读 SHA-256
> `9470dd6a01120480289c17d0da161e73b2eb6361ece3ea72041b07da088934af`，与候选一致；
> `misc` 残留 BCB 造成的 recovery 循环已清除）。重启现在是可用的恢复手段，
> 但仍不是首选，因为它会丢弃现场证据。
