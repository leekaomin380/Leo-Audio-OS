# M3 补丁作者自审、故障反证与设计推翻记录

日期：2026-08-29
角色：补丁作者的对抗性自审（目标是推翻自己的方案，不是证明它对）
审计基线：全新浅克隆 `MoKee/android_hardware_qcom_audio` @ `mkq-mr1-caf-msm8994`
HEAD `7f4cac748b6f62897294cdaece9d1aec27e1e927`，克隆时工作树 0 dirty，
**未复用任何已打过补丁的目录**。
边界：未连接设备、未运行 `adb`/`fastboot`、未写镜像或分区、未改 main 与 agy 工作树。

---

## 0. 被推翻或修正的原设计（六项）

| # | 原设计 | 判定 | 修正 |
| ---: | --- | --- | --- |
| **X1** | 后端进入钩子挂在 `platform_check_and_set_codec_backend_cfg()`，守卫 `usecase->out_snd_device == LEO_HIFI` | **推翻（真实缺陷）** | 移到 `enable_snd_device()`，新增 `platform_leo_hifi_snd_device_enabled()` |
| **X2** | 旁路三联断言 E5a/E5b/E5c 全部致命 | **推翻（过严）** | 只有模拟出口开放致命；其余降级为"旁路尝试"记录位 |
| **X3** | 证据门无"QUAT 前端确实打开"这一项 | **补漏（真实缺口）** | 新增致命证据位 E4 + `QUAT_MI2S_RX Audio Mixer MultiMedia1..16` 控件缓存 |
| **X4** | `leo_hifi_init()` 任何失败 → 本次 boot 永久禁用 | **修正** | 有界只读重探测（≤3 次）；仅结构性 `TABLE_MISMATCH` 永久禁用 |
| **X5** | dB 日志用 `(v*5-1275)/10` + `abs(%10)` | **修正** | `leo_hifi_ctl_to_db()` 分离符号；C 向零截断会把 −0.5 dB 打成 `0.5` |
| **X6** | 0001（枚举/表）不加 feature flag，"行为等价即可" | **加强** | 全部放进 `#ifdef LEO_HIFI_ENABLED`；现在 flag 关闭时**预处理 token 流与上游逐 token 相同** |

另有两项范围调整（不是缺陷，但改变了合同）：

* Android.mk 的开关由"msm8994/msm8992 平台"改为**设备级** `AUDIO_FEATURE_ENABLED_LEO_HIFI := true`，
  msm8992 与其他共用 msm8974 平台源码的机型完全不受影响；
* `platform_set_parameters()` 改为**先快照 usecase id 再调 `select_devices()`**，
  不在活链表上迭代同时调用可能触碰该链表的函数。

---

## 1. 五个高风险点的裁决

### A. `platform_check_and_set_codec_backend_cfg` 钩子时序 —— **原设计错误，已修**

真实调用序（`hal/audio_hw.c` @ `7f4cac74`，行号为该 commit 的上游行号）：

```text
select_devices()                                    audio_hw.c:937
  out_snd_device = platform_get_output_snd_device()  :997/1000   ← 选设备（我们的判定点）
  disable_audio_route(adev, usecase)                 :1058       ← usecase->out_snd_device 仍是【旧】设备
  disable_snd_device(adev, usecase->out_snd_device)  :1059
  check_and_route_playback_usecases(adev, usecase, out_snd_device)  :1079
       └─ platform_check_and_set_codec_backend_cfg(adev, uc_info)   :744
          ★ 此处 uc_info->out_snd_device 依然是【旧】设备
  enable_snd_device(adev, out_snd_device)            :1080       ← 第一次看到【新】设备
  usecase->out_snd_device = out_snd_device           :1099       ← 赋值发生在这里
  enable_audio_route(adev, usecase)                  :1113       ← 应用 mixer path，QUAT DAI 在此启动
```

**因此原来的守卫读的是上一个设备**：标准→HiFi 时永远不触发（进入侧完全失效），
HiFi→标准时反而触发（写在错误的边）。这是一个会让 M3-4「进入侧确定性」整条失效的缺陷。

**修正**：进入钩子改挂 `enable_snd_device()`（`audio_hw.c:637`，位于引用计数早退之后、
`audio_route_apply_and_update_path(device_name)` @ `:686` 之前）。

逐条回答：

| 问题 | 结论 | 依据 |
| --- | --- | --- |
| 写 `KHZ_48`/`S24_LE` 时 QUAT 控件是否已存在 | **是**。它们是声卡注册时就存在的静态 kcontrol | M2 实机 `05-hal-state.txt`：QUAT 路由全 Off 时 `1015 QUAT_MI2S BitWidth = S24_LE`、`1016 QUAT_MI2S SampleRate = KHZ_48` 仍可读 |
| 是否需要后端先启动 | **否，而且必须在启动之前写**。内核 machine driver 在 `hw_params` 时采样这两个 kcontrol | `docs/04` §3（`msm8994.c:2229-2242` backend fixup 取 QUAT kcontrol 值） |
| 写在 `enable_audio_route` 之前是否有效 | **有效且必要**。QUAT DAI 由 `enable_audio_route` 应用的 `<usecase> hifi-headphones` 路径启动 | M2 §6.1：翻转 `QUAT_MI2S_RX Audio Mixer MultiMedia1` 即触发 `msm8994_quat_mi2s_snd_startup` |
| 是否会被后续代码覆盖 | **不会**。`grep -rn QUAT_MI2S` 在整棵 `hardware/qcom-caf/msm8994/audio` @ `7f4cac74` **零命中** | 本轮 grep |
| 退出/失败路径是否必然恢复 | **是**。`disable_audio_route()` 钩子（旧设备仍在 `usecase->out_snd_device`）+ 统一 fallback 均调 `leo_hifi_set_backend()` | 代码 + host mock S9/S11 |
| 多 usecase 是否反复切换或死锁 | **不会**。写入幂等（目标恒为 `S24_LE`/`KHZ_48`）且带读回；`enable_snd_device` 的 `snd_dev_ref_cnt > 1` 早退使第二个 usecase 不重复写；不引入任何新锁，只调 tinyalsa | `audio_hw.c:620/626`；host mock S12 |

### B. `backend_tag_table` / `hw_interface_table` / 设备表 —— **成立，且发现一个必须记录的副作用**

* 路径名精确组成：`enable_audio_route()` 用
  `strlcpy(mixer_path, use_case_table[usecase->id]); platform_add_backend_name(mixer_path, snd_device);`
  → `"deep-buffer-playback"` + `" "` + `backend_tag_table[LEO] = "hifi-headphones"`
  = **`deep-buffer-playback hifi-headphones`**，与设备树 `mixer_paths.xml:433` 逐字对应。✔
* `enable_snd_device()` 另外应用设备路径 `"hifi-headphones"`（`mixer_paths.xml:1752`，**空路径**）——
  这是预期的：ESS 的上下电/时钟由内核在 QUAT DAI startup 时完成。✔
* `hw_info_append_hw_type()` 只对各板 `snd_devices` 列表内的扬声器类设备追加后缀，
  `SND_DEVICE_OUT_LEO_HIFI_HEADPHONES` 不在任何列表内 → 设备名保持 `"hifi-headphones"`。
  与 MIUI 日志 `hw_info_append_hw_type: device_name = hifi-headphones` 一致。✔
* `platform_check_backends_match()` 用 `hw_interface_table` 的**互相 `strstr`**比较：
  `"QUAT_MI2S_RX"` 与 `"SLIMBUS_0_RX"` 互不含子串 → 判为**不同后端**。✔

**副作用（本轮新发现，必须写进合同）**：正因为判为不同后端，
`check_and_route_playback_usecases()` **不会**把其他 SLIMBUS usecase 拖到 ESS 上，
它们会留在 `headphones` 路径上，于是 `HPHL DAC Switch` 保持为 1。
即：**HiFi 播放期间来一条通知音，模拟出口就会打开**。
在新的 E5 语义下这是致命条件 → 回退到标准路由。
这是 v1 的**有意选择**（宁可回退，也不在无法离线证明的双通路上继续宣称 HiFi），
但它是一个可见的产品行为，已记入 `docs/19` 与验收项 A16。

**Feature flag 关闭时的等价性**：不再只是"行为一致"。
`scripts/verify-m3-flag-off-equivalence.sh` 证明去掉 `#ifdef LEO_HIFI_ENABLED` 块后，
`platform.h` / `platform.c` / `audio_hw.c` 与上游**逐 token 相同**
（796 / 10830 / 10044 tokens）。唯一非 C 的改动是 Android.mk 里一个自包含的 `ifeq` 块。

**打开时是否可能整体错位**：新枚举追加在 OUT 段末尾，
`verify-m3-source-layout.sh` 证明插入点以下 36 个索引与设备二进制逐项一致、
插入点以上是干净的 +1 位移（只多了这一个设备），
且三张表全部使用指定初始化器，`snd_device_name_index` 按枚举顺序插入。✔

### C. `leo_hifi_init()` 失败语义 —— **原设计过刚，已改为有界重探测**

| 维度 | 策略 1（永久禁用） | 策略 2（有界重探测）**采用** |
| --- | --- | --- |
| 启动早期 ESS 未 probe 完 | 一次竞态 = 整个 boot 失去 HiFi | 后续路由决策时最多再试 2 次 |
| 声卡先注册、codec component 后绑定 | 控件缺失 → 永久禁用 | 同上，控件在重探测时已就位 |
| HAL 重启 | 自然重新 `platform_init` → 重新探测 | 同左 |
| 瞬态失败永久失效 | **会** | 不会 |
| 爆音风险 | — | **无**：探测只做 `stat()` + `mixer_get_ctl_by_name()`，**不写任何控件** |
| 循环重路由 | — | **无**：探测失败时返回的仍是原来的标准设备，`select_devices()` 因设备未变而早退（`audio_hw.c:1024`） |
| 高功耗 | — | **无**：上限 3 次/boot |

**例外**：`device_table` 名字不符（`LEO_FAIL_TABLE_MISMATCH`）**永久禁用且不重试**——
它不可能自愈，而在不知道自己会启用哪个设备的情况下继续是危险的。

无论哪种失败，`leo_hifi_init()` 都不返回错误、不阻断 `platform_init()`，
因此**不会阻断 Android 启动，也不会阻断普通耳机播放**（host mock S3–S6c、S16）。

### D. MultiMedia5 / SLIMBUS 旁路断言 —— **正负方向都已验证，语义已改**

新的观测模型覆盖完整 WCD 链，两个声道都在内：

```text
MultiMediaN -> SLIMBUS_0_RX -> SLIM RX1/RX2 MUX -> RX1/RX2 MIX1 INP1
             -> CLASS_H_DSM MUX -> HPHL DAC Switch -> 耳机插孔
```

| 位 | 控件 | 语义 |
| --- | --- | --- |
| `LEO_BP_SLIM_FE` | `SLIMBUS_0_RX Audio Mixer MultiMedia1..16` | 有前端送入 WCD 后端 |
| `LEO_BP_MUX_LIVE` | `SLIM RX1 MUX`、`SLIM RX2 MUX` | 左右两路接收 mux 未停 |
| `LEO_BP_MIX_LIVE` | `RX1 MIX1 INP1`、`RX2 MIX1 INP1` | 左右两路插值器输入未停（可选控件） |
| `LEO_BP_CLASSH` | `CLASS_H_DSM MUX` | **右声道 DAC 的实际闸门**（本声卡只有一个 `HPHL DAC Switch`，无 `HPHR DAC Switch`） |
| `LEO_BP_OUTLET` | `HPHL DAC Switch` | **模拟出口，唯一致命位** |

判定：**致命 = `LEO_BP_OUTLET`**；其余组合 = 记录为"旁路尝试"，不降级。
依据是 M2 `16-falsification.txt`：`SLIMBUS_0_RX ← MultiMedia5 = On` 而
`HPHL DAC Switch = Off`、`SLIM RX1/2 MUX = ZERO` 时**无声**——
断开模拟出口就足以使 WCD 路径不可闻。

正向验证（必须成立，否则断言写反了）：

* **标准耳机播放态**：WCD 链全部活跃是**正常**的。状态机在 `to_hifi_device == false` 时
  **根本不调用** `leo_hifi_check_bypass()`，直接落到 `WIRED_STANDARD`，
  `fail_code` 不为 `WCD_BYPASS`，`bypass` 位为 0。host mock **S13** 已验证。
* **HiFi 态**：QUAT 开启且模拟出口切断 → `HIFI_ACTIVE`（S2）。
* **MultiMedia5 出现但出口切断** → 记录 `LEO_BP_SLIM_FE`，**仍 `HIFI_ACTIVE`**（S10）。
* **出口开放** → `LEO_FAIL_WCD_BYPASS` → `ERROR_FALLBACK`（S11、S12）。
* **`ERROR_FALLBACK` 回到标准路由后被清除**为 `WIRED_STANDARD`，不会把普通耳机态
  长期显示成系统错误（S13b）。

### E. dB 日志算术 —— **已修，并补边界测试**

`dB = -127.50 + 0.50 × v`，十分之一 dB 的精确值是 `dq = 5v - 1275`。
原写法用商和余数推符号，在 `dq ∈ (-10, 0)` 时 C 向零截断使商为 0，**符号消失**：
`v = 254` 会打印 `0.5 dB`，真值是 `-0.5 dB`。
虽然 v=254 超出当前 `LEO_HIFI_CTL_CEIL = 237`，但一旦 R7-B 之后放宽上限就会命中，
而日志错误会污染后续证据链。

新实现 `leo_hifi_ctl_to_db()` 单独返回符号字符串，纯整数、无浮点。
host mock **S0** 逐值验证 `0 / 1 / 204 / 205 / 213 / 225 / 229 / 253 / 254 / 255`
全部正确（`-127.5 / -127.0 / -25.5 / -25.0 / -21.0 / -15.0 / -13.0 / -1.0 / -0.5 / 0.0`）。

---

## 2. 用 error -5 反向审计补丁（任务 B）

### 2.1 实机现象的源码机制（全部可在 `7f4cac74` 中定位）

```text
out_write()                       audio_hw.c:2465  ret = pcm_write(out->pcm, ...)
                                            :2467  if (ret < 0)
                                            :2488  ALOGE("%s: error %zd - %s", ..., pcm_get_error())
                                                   → "out_write: error -5 - cannot write stream data: I/O error"
                                            :2495  out_standby(&out->stream.common)
                                            :2496  usleep(一个 buffer 周期)
下一次 out_write → out->standby 为真 →
start_output_stream()             audio_hw.c:1766  select_devices(adev, out->usecase)
                                            :1778  pcm_open(...)
```

即：**包外手工翻转 mixer 会打断一个已经打开的 PCM**，HAL 按既定策略 standby + 重开流，
`select_devices()` 重新按 `platform_get_output_snd_device()` 的结果选设备——
在未打补丁的系统上那永远是 `SND_DEVICE_OUT_HEADPHONES(7)`，于是回到 SLIMBUS/WCD；
而手工写下的 `QUAT_MI2S_RX ← MultiMedia1` 没有任何代码会去清，形成潜在双通路。
观察到的 10.5–11.6 s 周期就是 `usleep(bytes/…)` 的重试节拍。

### 2.2 对补丁设计的三项直接影响

| # | 影响 | 补丁中的对应 |
| ---: | --- | --- |
| **1** | 路由必须在**流第一次打开之前**确定，不能事后改 | `select_devices()` 在 `start_output_stream()` 的 `pcm_open()` **之前**（1766 vs 1778）。补丁的判定点在 `platform_get_output_snd_device()`，即 `select_devices()` 内部最早的一步。**第一次 `start_output_stream` 就会选中符号化 `hifi-headphones` 并应用完整 `deep-buffer-playback hifi-headphones` 路径。** |
| **2** | 常驻脚本 / 播放后改 mixer 被实机否证 | `docs/19` §15 "不得使用的危险捷径"中的 `init.rc / 常驻 tinymix` 一条，从"违反单写入者原则"升级为**有实机反证**：它会周期性触发 `error -5` 并被 HAL 自动撤销 |
| **3** | 不能只看"有没有声音"判定成功 | 该实验中 QUAT 与 SLIMBUS 可以同时为 On。这正是 E5（模拟出口）+ E4（QUAT 前端确实开启）两个读回位存在的理由 |

### 2.3 是否可能同时遗留 SLIMBUS 与 QUAT

**同一 usecase：不会。** `select_devices()` 的顺序保证先拆后建：

```text
disable_audio_route(旧=headphones)   → 复位 "deep-buffer-playback"  → SLIMBUS_0_RX MM1 = 0
disable_snd_device(旧=headphones)    → 复位 "headphones"            → HPHL DAC Switch = 0, SLIM RX MUX = ZERO
enable_snd_device(新=hifi)           → 应用空的 "hifi-headphones"，并写 QUAT 后端（本补丁）
enable_audio_route(新)               → 应用 "deep-buffer-playback hifi-headphones" → QUAT MM1 = 1
```

**跨 usecase：可能，且这正是 §1.B 的副作用。** 第二条 SLIMBUS 流会让模拟出口保持开放，
被 E5 判为致命并回退。host mock S12 复现。

### 2.4 teardown / restart 后的状态泄漏

| 场景 | 结果 | 依据 |
| --- | --- | --- |
| 正常 teardown | `disable_audio_route()` 用 `audio_route_reset_and_update_path()` 把该路径的控件复位为 `mixer_paths.xml` 初值 → `QUAT MM1 = 0`；随后本补丁把 QUAT 后端显式写回 `S24_LE`/`KHZ_48` 并读回 | `audio_hw.c:583`、补丁 0004 |
| HAL 崩溃后重启 | `platform_init()` 内部先调 `audio_route_init()`（`platform.c:1212/1216`），重新下发 `mixer_paths.xml` 顶层默认块 → `Volume` 回 205、`QUAT MM1` 回 0；本补丁的 `leo_hifi_init()` 在其后（`platform.c:1435`）且**不写任何控件**，不会互相覆盖 | 行号见左 |
| 状态机残留 | `leo_hifi_init()` 先 `memset()` 整个结构，generation 归零、evidence 清空 | host mock **S15** |
| 音量残留 | `platform_init()` 不写 `Volume`（M3-10），HAL 重启后由 `audio_route_init` 恢复 205 | S15 |

**结论：没有发现 teardown / restart 状态泄漏路径。**

---

## 3. 逐 patch 审计结果

| Patch | 结论 | 本轮改动 |
| --- | --- | --- |
| 0001 符号化设备 | 通过 | 全部内容移入 `#ifdef LEO_HIFI_ENABLED`；flag 关闭时 token 级等价于上游 |
| 0002 路由控制器 | 通过 | Android.mk 改设备级 flag；`leo_probe()` 拆出并可重入；`set_parameters` 改快照迭代；新增 QUAT MM 与 RX/CLASS_H 控件缓存 |
| 0003 音量 | 通过 | `leo_hifi_ctl_to_db()` 符号安全；`property_set` 失败不致命；去掉多余的空值写入 |
| 0004 后端确定性 | **重写** | 进入钩子从 `platform_check_and_set_codec_backend_cfg()` 移到 `enable_snd_device()`；退出钩子保留在 `disable_audio_route()` |
| 0005 状态与回退 | **重写** | E5 语义改为"只有模拟出口致命"；新增 E4；新增 `LEO_BP_*` 观测位；`ERROR_FALLBACK` 在回到标准路由时清除 |

### 编译边界逐项

| 检查 | 结果 |
| --- | --- |
| 声明与定义一致 | `platform_leo_hifi_{snd_device_enabled,backend_exit,route_enabled,route_disabled}` 在 `leo_hifi.h` 声明、`platform.c` 定义、`audio_hw.c` 调用；三处一致 |
| `platform_api.h` | **未修改**。新接口走 `leo_hifi.h`，`audio_hw.c` 在 `#ifdef` 内包含它。若上游要求 platform 层导出必须经 `platform_api.h`，属 M3-0 的收口项（本轮未取得该文件的审阅） |
| implicit declaration | `clang -std=c99 -Wall -Wextra -Wshadow -Wsign-compare -Wformat=2` 对 `leo_hifi.c` **零告警** |
| 静态/外部符号冲突 | `leo_hifi.c` 内 `leo_ctl` / `leo_ctl_opt` / `leo_probe` / `leo_write_volume_ctl` / `leo_set_enum_checked` / `leo_state_name` / `leo_enum_is_live` / `leo_quat_front_end_live` / `leo_hifi_fallback` 全部 `static`；导出符号均以 `leo_hifi_` 或 `platform_leo_hifi_` 前缀 |
| 头文件循环 | `leo_hifi.h` 只包含 `<stdbool.h> <stddef.h> <tinyalsa/asoundlib.h>`，不包含 `audio_hw.h` / `platform.h`，无循环 |
| Android.mk / BoardConfig | `AUDIO_FEATURE_ENABLED_LEO_HIFI := true` + 内层 `AUDIO_PLATFORM = msm8974` 双重守卫；`LOCAL_CFLAGS +=` 位于平台 `:=` 赋值链（Android.mk:16–37）之后，不会覆盖 `-DPLATFORM_MSM8994` |
| msm8994 / msm8992 作用域 | 由设备级 flag 控制，msm8992 不再被牵连 |
| C/C++ 模式 | 纯 C 模块；未用 `_Static_assert`，改用 C89 负数组大小断言 |
| format string | `-Wformat=2` 通过；`%llu` 对 `unsigned long long`，`%s%d.%d` 对 dB |
| signed/unsigned | `-Wsign-compare` 通过；`mixer_ctl_get_value` 返回 `int`，传入 `mixer_ctl_get_enum_string` 前显式 `(unsigned int)` 且先判 `>= 0` |
| 空指针 | 每个 `struct mixer_ctl *` 使用前判空；`platform_leo_hifi_*` 均先判 `my_data == NULL` |
| 数组越界 | `ctl_slim_mm` / `ctl_quat_mm` 循环上界 `LEO_HIFI_MM_COUNT`；`ids[AUDIO_USECASE_MAX]` 带 `n < AUDIO_USECASE_MAX` 保护 |
| 锁序与 `usecase_list` 并发 | `adev_set_parameters()` 已持 `adev->lock` 才调 `platform_set_parameters()`；补丁不新增锁；改为先快照 id 再调 `select_devices()` |
| `select_devices` 递归/重入 | 上游本身在 `select_devices()` 内对采集 usecase 递归一次（`audio_hw.c:1003`）。补丁不新增递归；快照迭代避免了"边遍历边调用"的形态 |
| property 限制 | `vendor.leo.audio.*` 属 vendor 命名空间；在 `property_contexts` 落地前 `property_set()` 可能失败。所有调用点都 `(void)` 忽略返回值且不依赖其成功；host mock **S16** 验证失败时初始化、意图、音量路径全部照常 |
| HAL 重启 / standby / pause / 拔线 / 多播放器 | 见 §2.4 与 host mock S12/S15/S17 |
| feature OFF 与 runtime OFF | OFF 时 token 级等价（脚本证明）；runtime OFF 时 `leo_hifi_route_wanted()` 直接返回 false，不写任何控件（S1） |

---

## 4. 故障注入结果（host mock，88/88）

| 场景 | 覆盖 | 结果 |
| --- | --- | --- |
| S0 | dB 边界 0/1/204/205/213/225/229/253/254/255 | 全部正确 |
| S1 | runtime flag OFF | 不选路由、不写控件 |
| S2 | 标称启用 | `HIFI_ACTIVE`，generation=1 |
| S3 | `Volume` 控件缺失 | 探测失败、可重试、拒绝路由 |
| S4 / S5 | `QUAT SampleRate` / `BitWidth` 缺失 | 探测失败、`set_backend` 拒绝 |
| S6 | ESS sysfs 缺失 → 后来出现 | 有界重探测成功 |
| S6b | 重探测预算 | 恰好 3 次后不再尝试 |
| S6c | 结构性表不符 | 永久禁用，不消耗重试 |
| S7 | 写成功但读回偏移 | `-EIO`，`READBACK_SOFT`，`vol_applied` 清除 |
| S8 | 音量越界 | 拒绝且**值不变** |
| S8b | 正常应用 | 0→213、30→225，从不越上限 |
| S9 | 后端半成功（SampleRate 写失败） | `ERROR_FALLBACK`，E6 未置位 |
| S9b | 后端 enum 读回不符 | `BACKEND_READBACK` |
| S10 | MultiMedia5 出现、出口切断 | **记录不致命**，保持 `HIFI_ACTIVE` |
| S11 | 模拟出口开放 | 致命 → `ERROR_FALLBACK` |
| S12 | 第二条 SLIMBUS 流（完整链） | 五个观测位全中 → `ERROR_FALLBACK` |
| S13 | 标准耳机态 | **不判错误**，`bypass == 0` |
| S13b | 从 `ERROR_FALLBACK` 回到标准 | 清除为 `WIRED_STANDARD` |
| S14 | QUAT 前端未开（无对应 mixer path） | E4 未置位 → `ERROR_FALLBACK` |
| S15 | HAL 重启 | generation/evidence 归零，`Volume` 回 205 |
| S16 | `property_set` 失败 | 初始化、意图、音量路径均不受影响 |
| S17 | 播放中翻转开关 | `set_mode` 正确报告变化/无变化 |
| S18 | 状态字符串 | 含 `effective`、`acdb=absent_expected`、`backend=S24_LE/KHZ_48`、`vol_db=-25.0` |
| S19 | 读音量 | 不写 |

**这是 host mock，不是 Android 构建，也不是设备证据。**

---

## 5. 仍存在的阻断项

### 编译

* **未做 Android 模块构建。** 见 [`M3-COMPILE-READINESS.md`](M3-COMPILE-READINESS.md)。
  `platform.c` / `audio_hw.c` 的改动只经过 `git apply` 与 token 级比对，**没有经过编译器**。
* `platform_api.h` 未审阅（本轮只取了 5 个文件 + `platform_info.c` 探路）。

### 运行时

* **N-2 未闭合**：DIRECT PCM 是否映射到 offload usecase 族（M3.5 的否决性前置，本轮不涉及）。
* **通知音会打掉 HiFi**：§1.B 的副作用。属有意的安全默认，但需要 A16 实测确认可接受，
  或在 M3-B 之后决定是否把全部 playback usecase 一并迁到 ESS。
* `mixer_paths.xml` 只为 deep-buffer / low-latency / audio-ull / compress-offload 提供了
  `hifi-headphones` 路径；其他 usecase 会应用不到任何路径，由 E4 捕获并回退。

### 写入

* 本轮不产生任何写入授权。M3-0（无修改构建 + 与 `701019bd…` 符号级对照）未开始。
* R7-B（`Volume` 225）未执行，**不得记为通过**。
