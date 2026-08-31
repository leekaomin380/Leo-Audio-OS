# 17：Leo HiFi 控制与状态显示契约

> 状态：设计基线。它定义 Phase 5B M3 及后续 `leo_audio` 产品的功能预期；不授权向设备写入、
> 不授权修改 MoKee 镜像，也不把静态证据当作真机 HiFi 已成立的证明。
>
> **[2026-08-29 修订]** 本文已按 `docs/research/CLAUDE-OPUS5-HIFI-CONTROLLER-ARCHITECTURE.md`（`805989e`）
> 与 `docs/research/M3-HIFI-ARCHITECTURE-RULING-DRAFT.md`（`94d0370`）的裁决修订。
> 可执行契约见 [`19：Phase 5B M3 Leo HiFi Controller 工程合同`](19-PHASE-5B-M3-HIFI-CONTROLLER-CONTRACT.md)。
> 旧结论一律保留，被修正处以本样式的行内批注标出，并给出依据与日期。修订清单见文末 §11。

## 1. 目的

Leo Audio OS 的 HiFi 不能只是一个“增强音效”开关。系统必须能以可审计的方式回答：

1. 当前声音走的是外放、普通耳机，还是 ESS9018/QUAT MI2S 路径？
2. 若处于 HiFi 路径，供电、时钟、路由、校准和播放流是否均已生效？
3. 若无法确认，系统是否已安全回退，而不是以“耳机有声”伪装 HiFi 成功？

唯一可信控制者是 Android audio HAL 内的 Leo HiFi Controller。Leo Home 和维护页只能读取状态，
不得直接写 ALSA mixer、sysfs、DAC I2C 或 `persist.*` property。

## 2. 架构边界

```text
播放流、耳机插拔、路由变化、格式变化
                 ↓
       Leo HiFi Controller（audio HAL）
                 ↓
供电 / 时钟 / QUAT MI2S / ESS9018 / ACDB 的有序控制
                 ↓
      硬件读回、mixer 读回、内核与 HAL 错误
                 ↓
   Leo Audio Status Service（只读、受 SELinux 约束）
                 ↓
       Leo Home 摘要      隐藏维护页证据
```

> **[2026-08-29 修订 · 依据：`docs/04` §5、M2 §5 实测 `hifi-headphones` mixer path 为空]**
> 上图中「供电 / 时钟 / QUAT MI2S / ESS9018 / ACDB 的有序控制」需要收窄：
> **ESS 的供电、晶振、reset、mute、OPA 与模拟 switch 由内核 `es9018.c` 与 `msm8994.c` machine driver
> 在 QUAT MI2S DAI startup/shutdown 时自动完成，HAL 只观察、不驱动。**
> HAL 实际写入的只有三类控件：路由（`audio_route`）、`QUAT_MI2S BitWidth`/`SampleRate`、ES9018 `Volume`。

控制器在 M3 首先作为 Android 10 Qualcomm HAL 的最小源码补丁/重写目标。禁止直接覆盖 Android 10
的 audioserver、framework 或整块 Android 7 stock HAL。状态服务在其后建立；普通应用不拥有任何
vendor 设备节点、property 写入或 binder 控制权限。

> **[2026-08-29 补充 · 依据：`docs/research/M3-SOURCE-PROVENANCE.md`]**
> 补丁目标已精确到：`MoKee/android_hardware_qcom_audio` 分支 `mkq-mr1-caf-msm8994`
> HEAD `7f4cac748b6f62897294cdaece9d1aec27e1e927`，manifest 路径 `hardware/qcom-caf/msm8994/audio`，
> 文件 `hal/msm8974/platform.c`、`hal/msm8974/platform.h`、`hal/audio_hw.c`，构建产物为 **32-bit**。
> 补丁点清单见 `docs/19` §10。

## 3. 状态模型

| 状态 | 语义 | 对普通界面显示 |
| --- | --- | --- |
| `IDLE` | 无活动输出；不应维持高功耗 DAC 路径 | 就绪 |
| `SPEAKER` | 外放路由；ESS HiFi 路径关闭 | 外放 |
| `WIRED_STANDARD` | 已插耳机，但走标准耳机路径 | 耳机 · 标准 |
| `HIFI_ARMING` | 正在依序启用供电、时钟、QUAT 和 ESS | HiFi · 正在连接 |
| `HIFI_ACTIVE` | 所有要求的运行时证据已闭合 | HiFi · 已激活 |
| `HIFI_DEGRADED` | 有声音但关键证据不完整；不得声称 HiFi 已成立 | 耳机 · 受限 |
| `ERROR_FALLBACK` | 初始化或运行失败，已回退到安全标准路由 | 耳机 · 安全回退 |

每次状态变更必须带单调递增 generation、时间、触发原因和失败码。控制状态与显示状态分离：
`requested_mode` 表示策略意图，`effective_mode` 只表示已经读回确认的真实路径。

> **[2026-08-29 补充]** 除 generation / 时间 / 原因 / 失败码外，还必须携带 **evidence bitmap**
> （E1–E10' 各占一位），使「部分证据缺失」可被精确表达而不是笼统降级。失败码表见 `docs/19` §4.3。

## 4. 允许的转换

1. 耳机插入或播放开始：`IDLE` / `SPEAKER` → `WIRED_STANDARD`；
2. 满足 HiFi 资格后：`WIRED_STANDARD` → `HIFI_ARMING`；
3. ESS、QUAT、mixer、ACDB 与流参数全部核验：`HIFI_ARMING` → `HIFI_ACTIVE`；
   > **[2026-08-29 修订 · 依据：stock 与 MoKee 的 `audio_platform_info*.xml` 均无 `hifi-headphones` 的
   > `acdb_id`；MIUI 原厂即以「device 34 缺少 ACDB ID」告警运行]**
   > **ACDB 不再是 `HIFI_ACTIVE` 的必要条件。** 正确判据是「ACDB 查询无错误，且『无该设备条目』
   > 视为预期结果」。详见 `docs/19` §8。
4. 任一非致命证据缺失：`HIFI_ARMING` / `HIFI_ACTIVE` → `HIFI_DEGRADED`；
5. 写入失败、设备消失、耳机拔出、播放流归零或 HAL 崩溃：进入 `ERROR_FALLBACK`、
   `WIRED_STANDARD` 或 `IDLE`，并确保有序下电；
6. 不允许从 `ERROR_FALLBACK` 直接显示 `HIFI_ACTIVE`；必须重新经过 `HIFI_ARMING` 与全部读回。

第一版不承诺按照耳机阻抗自动切换“高级模式”。只有在 stock 运行证据与原厂逻辑均明确后，
才把耳机类型、采样率和位宽纳入策略输入。

> **[2026-08-29 加强 · 依据：stock HAL `platform_get_output_snd_device` @0x145dc–0x14614 反汇编]**
> 该结论现有直接证据：**MIUI 原厂的 HiFi 判据里根本不含阻抗**，只读一个布尔量 `my_data->hifi`。
> 另据 M2 §7.1，耳机阻抗在 QUAT 后端启动前是无效值，**不可作为策略输入，也不作为证据门**。

## 5. `HIFI_ACTIVE` 的证据门

不得只根据 property、UI 状态或主观听感进入 `HIFI_ACTIVE`。至少需要：

- 有线输出设备与 AudioPolicy/HAL route 一致；
- ESS9018 内核驱动已 probe，且所需设备节点可用；
- QUAT MI2S 路由及关键 mixer controls 的写入和读回一致；
- ESS 供电、时钟、mute/OPA 状态满足已验证的目标序列；
- Forte ACDB/loader 没有失败或 linker/SELinux denial；
- 活动播放流仍存在；
- 所有证据属于同一个 route generation，而非历史残留日志。

> **[2026-08-29 修订 · 依据：M2 §6.2/§7.2 实测 + `94d0370` §8.3]**
> 上列七条保留为历史记录，但作为**执行契约已被 `docs/19` §4.2 的 E1–E10' 取代**。两处关键变化：
>
> 1. **新增致命项 E5（旁路三联断言）**——原列表完全没有覆盖 M2 实测到的
>    `MultiMedia<N> → SLIMBUS_0_RX` 假阳性。断言为：
>    E5a `SLIMBUS_0_RX Audio Mixer MultiMedia1..16` 读回全 Off；
>    E5b `HPHL DAC Switch` 读回 Off；
>    E5c `SLIM RX1 MUX` 与 `SLIM RX2 MUX` 读回 ZERO。任一失败即 `ERROR_FALLBACK`。
> 2. **删除「Forte ACDB/loader 没有失败」作为必要条件**——该条对 HiFi 设备结构性不可满足，
>    改为三态 `OK / ABSENT_EXPECTED / ERROR`，仅 `ERROR` 降级。
>
> 另新增致命项 E6：`QUAT_MI2S BitWidth` 与 `SampleRate` 的**读回值**必须等于控制器的确定性目标
> （第一版为 `S24_LE` / `KHZ_48`）。理由见 `docs/19` §5.2 关于陈旧速率的说明。

M2 必须先采集原版 MoKee 实测基线，才能确定上述各项的确切节点、控制名称和阈值。M3 不得用
MIUI 静态字符串替代 Android 10 实机闭包。

> **[2026-08-29 已闭合]** M2 已完成。确切控件名为：
> `QUAT_MI2S_RX Audio Mixer MultiMedia<N>`、`SLIMBUS_0_RX Audio Mixer MultiMedia<N>`、
> `HPHL DAC Switch`、`SLIM RX1 MUX`、`SLIM RX2 MUX`、`QUAT_MI2S BitWidth`、`QUAT_MI2S SampleRate`、
> `Volume`；ESS 绑定证据为 `/sys/bus/i2c/devices/6-0048/driver`。

## 6. 状态服务与界面

### 普通 Leo Home

普通界面只呈现低干扰摘要，不提供危险开关：

```text
外放
耳机 · 标准
HiFi · ESS9018 · 已激活
耳机 · 安全回退
```

采样率/位宽只有在 HAL 已实际确认时才显示；未知状态显示“未确认”，不填充猜测值。普通模式不显示
日志、内核路径、调试 property 或可修改控件。

> **[2026-08-29 补充 · 依据：`805989e` §5.5]** 当输出经过 SRC 时，界面**必须显式标注「重采样」**，
> 并且**禁止把 24-bit 容器显示为音质指标**（16-bit 源进 S24_LE 不增加信息量）。
> 在 N2 闭合前，不得对任何第三方播放器声称存在 44.1 kHz 无 SRC 通路。

### 隐藏维护页

经既有 PIN 维护门进入后可读：当前/请求状态、generation、上次转换、失败码、AudioPolicy route、
HAL 输出设备、活动流、QUAT mixer 读回、ESS/时钟/电源证据、ACDB load 结果、最近 SELinux denial。

> **[2026-08-29 补充]** 维护页还须显示：ES9018 `Volume` 读回原始值、`SLIM RX1/RX2 MUX` 读回、
> `HPHL DAC Switch` 读回、活动流计数、evidence bitmap、以及 ACDB 的三态结果
> （`无该设备条目（与原厂一致）` 是正常显示，不是错误）。

维护页的“重新探测”只能请求 HAL 做一次安全重新评估，不能绕过状态机直接写硬件。导出诊断必须脱敏，
不得包含 Spotify token、账户信息、节点订阅或专有 blob 字节。

## 7. 安全与权限

- HAL 是唯一可写 vendor audio 控制面的域；
- Status Service 默认只读，采用 signature permission，并限制给 Leo Home 与维护界面；
- 使用新的 `vendor.leo.audio.*` 只读发布状态可作为早期调试辅助，但不是长期可信控制面；
  > **[2026-08-29 修订]** `vendor.leo.audio.hifi.enable` 与 `vendor.leo.audio.hifi.volume`
  > **就是**长期控制面：HAL 是唯一写入者，Leo Audio Policy Service 是唯一请求者，
  > 请求经 HAL `set_parameters` 的 `leo_hifi_mode` / `leo_hifi_volume` 键进入。
  > 只读状态另走 `get_parameters("leo_hifi_status")`。
  > **禁止复用 `persist.audio.hifi` 与 `persist.audio.hifi.volume`**——MIUI 语义未完全证明，
  > 且 MoKee 无对应 `property_contexts` 条目。
- 最终 `user` 构建中 SELinux 必须 Enforcing，ADB 默认关闭，无 Magisk/常驻 root；
- 状态服务不可让第三方应用推断播放内容、Spotify 账户、设备序列号或网络身份；
- status API 版本化，未知字段必须 fail-closed 为“未确认”。

## 8. 分阶段交付

| 阶段 | 交付 | 完成条件 |
| --- | --- | --- |
| M2 | 原版 MoKee 观测协议 | 不改镜像地采集 route、mixer、内核、ACDB、denial 与功耗基线 |
| M3-A | HAL 调试状态 | `dumpsys`/结构化日志给出状态、generation 与失败码；不接 UI |
| M3-B | 最小 HiFi Controller | 每次只变更一层，成功/失败均可安全回退 |
| M3-C | 只读 Status Service | HAL 读回证据可由受限客户端查询 |
| M4 | Leo Home/维护页显示 | 普通摘要与维护明细均不具备硬件直写能力 |
| M5 | 发布验收 | user + Enforcing + 默认关闭 ADB；冷启动、插拔、息屏、崩溃和恢复均通过 |

> **[2026-08-29 细化]** 阶段拆分已细化为 M3-0 / M3-A / M3-B / M3-C / M3-D + M3.5，见 `docs/19` §11。
> 硬约束：**M3-B（路由）与 M3-C（音量）不得合并**——音量变化会掩盖路由问题，反之亦然。
> 另新增 M3-d 项：每次进入与退出 HiFi 都确定性写入并读回 `KHZ_48` / `S24_LE`。

## 9. 验收矩阵

每一候选至少测试外放、耳机插入、播放开始/暂停/结束、拔耳机、采样率变化、异常 HAL 重启、
Spotify 崩溃、息屏、重启和安全回退。每次测试都同时记录：可见状态、HAL status、AudioPolicy、
mixer 读回、kernel log、ACDB/SELinux 记录、温度与恢复结果。

任何“状态显示 HiFi”但 mixer/内核/校准证据不一致的情况都视为阻断缺陷；任何“有声音但状态不确定”
必须展示为 `HIFI_DEGRADED` 或 `ERROR_FALLBACK`，不能静默标为成功。

> **[2026-08-29 扩充]** 验收矩阵已扩充为 A1–A18（见 `805989e` §8 与 `docs/19` §12.3），
> 其中四项是本文原列表没有的：
> **A3** A/B/A 因果验证（必须含旁路断言）、**A7** 与 MIUI 黄金参照的 SPL 对照、
> **A13/A14** 故障注入（ESS 未绑定、mixer 写失败）、**A16** 多流场景不得切换时钟家族。


---

## 10. 采样率契约（2026-08-29 新增）

> 依据：`805989e` §5、`94d0370` §3、`docs/19` §1.4。

1. **第一版默认时钟家族为 48 kHz。** 控制器在每次进入与退出 HiFi 时确定性写入
   `QUAT_MI2S SampleRate = KHZ_48`、`QUAT_MI2S BitWidth = S24_LE` 并读回。
   「不写」不等于「正确」——原厂实现没有任何 teardown 复位，会留下陈旧速率。
2. **只在 M3.5 的受控场景（单应用、单流、有线 HiFi、DIRECT 输出）尝试 44.1 kHz 直通。**
   M3 范围内不做任何 44.1 尝试。
3. **只改后端速率是被禁止的。** 若前端仍为 48 kHz 而后端设为 44.1 kHz，
   SRC 只是从 AudioFlinger 移到 ADSP，并触发 `docs/04` §7.4 中未验证的 LPASS slave 时钟路径。
4. **以下任一成立即必须显示「重采样」，且不得使用 bit-perfect 字样**：
   活动流 > 1；输出路径不是 DIRECT；`QUAT_MI2S SampleRate` 读回与 `out->sample_rate` 不对应；
   存在活动 effect；Android 音量不在最大刻度。
5. **N2 未闭合前**（DIRECT PCM 是否映射到 offload usecase 族），
   不得对 Apple Music 或任何第三方播放器声称存在用户可达的 44.1 kHz 无 SRC 通路。

## 11. 修订记录

| 日期 | 位置 | 修订 | 依据 |
| --- | --- | --- | --- |
| 2026-08-29 | §2 架构图 | ESS 供电/时钟/mute/OPA 由内核负责，HAL 只观察 | `docs/04` §5；M2 §5（`hifi-headphones` path 为空） |
| 2026-08-29 | §2 末段 | 补丁目标精确到仓库/分支/commit/文件，产物为 32-bit | `M3-SOURCE-PROVENANCE.md` |
| 2026-08-29 | §3 | 状态附加 evidence bitmap | `94d0370` §8.1 |
| 2026-08-29 | §4 转换 3 | ACDB 不再是 `HIFI_ACTIVE` 必要条件 | `audio_platform_info*.xml` 无 `hifi-headphones` 条目 |
| 2026-08-29 | §4 末段 | 「不按阻抗切换」获得反汇编级证据并加强 | stock HAL `0x145dc–0x14614`；M2 §7.1 |
| 2026-08-29 | §5 | 证据门被 `docs/19` §4.2 的 E1–E10' 取代；新增 E5 旁路三联断言与 E6 后端读回；删除 ACDB 必要条件 | M2 §6.2/§7.2 |
| 2026-08-29 | §5 末段 | M2 已闭合，列出确切控件名 | M2 运行时采集 |
| 2026-08-29 | §6 | SRC 必须显式标注；24-bit 容器不得作为音质指标 | `805989e` §5.5 |
| 2026-08-29 | §7 | `vendor.leo.audio.*` 升为长期控制面；禁止复用 `persist.audio.hifi*` | `94d0370` §6 |
| 2026-08-29 | §8 | 阶段细化为 M3-0/A/B/C/D + M3.5；B 与 C 不得合并 | `docs/19` §11 |
| 2026-08-29 | §9 | 验收扩充为 A1–A18，新增 A3/A7/A13/A14/A16 | `805989e` §8 |
| 2026-08-29 | §10 | 新增采样率契约 | `94d0370` §3、§7 |

**未被修订的原有结论**（继续有效）：§1 目的三问、§3 七状态语义与显示文案、§4 转换 1/2/4/5/6、
§6 普通界面只呈现低干扰摘要、§7 SELinux Enforcing / ADB 默认关闭 / 无 Magisk、
§7 状态服务不得让第三方推断播放内容或账户信息、§8 M2/M4/M5 的完成条件。
