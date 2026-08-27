# 17：Leo HiFi 控制与状态显示契约

> 状态：设计基线。它定义 Phase 5B M3 及后续 `leo_audio` 产品的功能预期；不授权向设备写入、
> 不授权修改 MoKee 镜像，也不把静态证据当作真机 HiFi 已成立的证明。

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

控制器在 M3 首先作为 Android 10 Qualcomm HAL 的最小源码补丁/重写目标。禁止直接覆盖 Android 10
的 audioserver、framework 或整块 Android 7 stock HAL。状态服务在其后建立；普通应用不拥有任何
vendor 设备节点、property 写入或 binder 控制权限。

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

## 4. 允许的转换

1. 耳机插入或播放开始：`IDLE` / `SPEAKER` → `WIRED_STANDARD`；
2. 满足 HiFi 资格后：`WIRED_STANDARD` → `HIFI_ARMING`；
3. ESS、QUAT、mixer、ACDB 与流参数全部核验：`HIFI_ARMING` → `HIFI_ACTIVE`；
4. 任一非致命证据缺失：`HIFI_ARMING` / `HIFI_ACTIVE` → `HIFI_DEGRADED`；
5. 写入失败、设备消失、耳机拔出、播放流归零或 HAL 崩溃：进入 `ERROR_FALLBACK`、
   `WIRED_STANDARD` 或 `IDLE`，并确保有序下电；
6. 不允许从 `ERROR_FALLBACK` 直接显示 `HIFI_ACTIVE`；必须重新经过 `HIFI_ARMING` 与全部读回。

第一版不承诺按照耳机阻抗自动切换“高级模式”。只有在 stock 运行证据与原厂逻辑均明确后，
才把耳机类型、采样率和位宽纳入策略输入。

## 5. `HIFI_ACTIVE` 的证据门

不得只根据 property、UI 状态或主观听感进入 `HIFI_ACTIVE`。至少需要：

- 有线输出设备与 AudioPolicy/HAL route 一致；
- ESS9018 内核驱动已 probe，且所需设备节点可用；
- QUAT MI2S 路由及关键 mixer controls 的写入和读回一致；
- ESS 供电、时钟、mute/OPA 状态满足已验证的目标序列；
- Forte ACDB/loader 没有失败或 linker/SELinux denial；
- 活动播放流仍存在；
- 所有证据属于同一个 route generation，而非历史残留日志。

M2 必须先采集原版 MoKee 实测基线，才能确定上述各项的确切节点、控制名称和阈值。M3 不得用
MIUI 静态字符串替代 Android 10 实机闭包。

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

### 隐藏维护页

经既有 PIN 维护门进入后可读：当前/请求状态、generation、上次转换、失败码、AudioPolicy route、
HAL 输出设备、活动流、QUAT mixer 读回、ESS/时钟/电源证据、ACDB load 结果、最近 SELinux denial。

维护页的“重新探测”只能请求 HAL 做一次安全重新评估，不能绕过状态机直接写硬件。导出诊断必须脱敏，
不得包含 Spotify token、账户信息、节点订阅或专有 blob 字节。

## 7. 安全与权限

- HAL 是唯一可写 vendor audio 控制面的域；
- Status Service 默认只读，采用 signature permission，并限制给 Leo Home 与维护界面；
- 使用新的 `vendor.leo.audio.*` 只读发布状态可作为早期调试辅助，但不是长期可信控制面；
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

## 9. 验收矩阵

每一候选至少测试外放、耳机插入、播放开始/暂停/结束、拔耳机、采样率变化、异常 HAL 重启、
Spotify 崩溃、息屏、重启和安全回退。每次测试都同时记录：可见状态、HAL status、AudioPolicy、
mixer 读回、kernel log、ACDB/SELinux 记录、温度与恢复结果。

任何“状态显示 HiFi”但 mixer/内核/校准证据不一致的情况都视为阻断缺陷；任何“有声音但状态不确定”
必须展示为 `HIFI_DEGRADED` 或 `ERROR_FALLBACK`，不能静默标为成功。
