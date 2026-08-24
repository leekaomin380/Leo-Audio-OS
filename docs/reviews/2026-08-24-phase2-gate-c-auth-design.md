# Phase 2 Gate C：维护认证与本机恢复设计

日期：2026-08-24

## 目标

Gate C 要解决的不是高强度防 Root 对抗，而是确保专用播放器日常使用者不能误入 Android
维护面，同时保证设备所有者在没有电脑时能够返回 MIUI 并清除默认 HOME。

## 威胁边界

原型防护范围：

- 偶然触碰和普通使用者进入维护页；
- 对 PIN 的少量在线猜测；
- PIN 明文进入日志、仓库或普通备份；
- 维护会话长期保持开启。

原型不声称抵抗已经取得 Root、ADB 或物理镜像访问的攻击者。当前测试机本身已经 Root，
此类主体可以修改应用私有数据或直接停用 Launcher；这不属于应用 PIN 能解决的问题。

## v0.2 设计

- 隐藏手势后先进入非导出的认证 Activity；
- 首次由设备所有者在本机设置 6 位 PIN；
- 只保存随机 16-byte salt 和 `PBKDF2WithHmacSHA1` 120,000 次派生的 256-bit 结果；
- PIN 字符数组使用后覆盖，不写日志，不经 ADB 传输；
- 连续失败 5 次后，当前认证进程锁定 30 秒；
- 认证成功只创建 5 分钟进程内会话，进程死亡即失效；
- 主动退出维护立即清除会话；
- 维护 Activity 非导出，且每次创建/恢复都检查会话；
- 认证后才启用原厂 MIUI 桌面出口；
- 另有 Leo Shell 应用信息入口，用于清除默认项或卸载，形成无电脑恢复路径。

构建与静态审计结果：

- 单元测试、Android Lint、源码清单和编译 APK 清单检查全部通过；
- `safePreviewDebug` 仍不包含 `HOME`，且不请求任何 Android 权限；
- `homeCandidateDebug` 只做离线清单比较，仍不安装；
- `safePreviewDebug` SHA-256：
  `b4b6c57d1843dc147d953444b0016b4831f6c0742527c00be00be88d5b8493ba`；
- `homeCandidateDebug` SHA-256：
  `e0f277391dfa1e905c8a5d00e1a2c0405fc23f970a5ef311a10af1b7674ca5e1`。

## 仍需实机证明

1. Android 7.0 上 PIN 派生与保存成功；
2. 错误 PIN、正确 PIN 和锁定表现；
3. 退出维护后再次进入必须重新认证；
4. 直接启动非导出维护 Activity 被拒绝；
5. 原厂 MIUI Launcher 可以显式打开；
6. Leo Shell 应用信息页可以进入；
7. 更新 APK 后 PIN 是否按预期保留；
8. 清除数据和卸载后的恢复行为。

在这些检查完成前，不安装 `homeCandidate`，不把 Leo Shell 设为默认 HOME。

## 首次实机安装与认证

- 以 MIUI 系统安装器、设备所有者显式确认的方式，从 Gate B v0.1 覆盖更新至
  `0.2.0-dev.1-preview-debug`；
- 更新后默认 HOME 复查仍为 `com.miui.home/.launcher.Launcher`；
- 设备所有者在手机本地完成首次 6 位 PIN 设置和确认；
- 电脑端只轮询前台 Activity，确认认证后进入非导出的 `MaintenanceActivity`；
- 没有采集认证页面截图、输入内容、应用私有首选项或 PIN 派生值；
- 新维护页中原厂 MIUI 桌面出口和 Leo Shell 应用信息入口已经显示。

下一门槛是错误 PIN 计数、主动退出后重新认证、五分钟过期，以及两个本机恢复入口。

## 首次交互发现：主线程停顿

设备所有者故意输入一次错误 PIN 后，剩余次数正确变为 4，但在结果出现前感受到明显
延迟。原因是 120,000 次 PBKDF2 派生运行在主界面线程；骁龙 810 上这会形成可见卡顿。

安全成本本身不降低，修复策略是把保存和验证全部移到单线程后台执行器：计算期间显示
“正在验证/保存”、禁用输入和提交，结果再返回主线程。Activity 销毁时移除回调并停止
执行器，PIN 字符数组仍在后台任务结束时覆盖。

修复版 `0.2.1-dev.1` 同时把失败计数移到进程级节流器，避免通过退出再进入认证页重置
次数。新增 3 个节流器单元测试后，共 6 个单元测试、Lint 和双 APK 清单校验全部通过：

- `safePreviewDebug` SHA-256：
  `293b3cfac23b0fc17f65322882f1397ebe9e3250817c0a2e06684b1348dc78e2`；
- `homeCandidateDebug` SHA-256：
  `1f88bd8bb800479f5ec5688da7c487aea0c2dae7d07dbc6acb5a45b5599b3375`。

修复版仍不包含 HOME 或 Android 权限；需覆盖安装后复测 UI 响应和 PIN 保留。

## v0.2.1 覆盖安装

第一次打开安装器时，MIUI 只是恢复旧的安装完成任务，用户界面看似已处理，但实机包仍
报告 `versionCode=2`。因此没有依据视觉提示误报成功；关闭旧安装器任务后重新打开精确
APK，由设备所有者再次确认更新。

第二次实机读取确认：

- `versionCode=3`；
- `versionName=0.2.1-dev.1-preview-debug`；
- 默认 HOME 仍为 `com.miui.home/.launcher.Launcher`；
- 既有 PIN 配置由 Android 应用数据正常保留。

等待设备所有者验证后台计算期间的进度提示和界面响应。

设备所有者随后确认版本正确，并在输入 PIN 后看到“正在验证，请稍候…”。计算结束后实机
前台进入 `MaintenanceActivity`。因此后台化修复达到目标：刻意的 PBKDF2 等待仍存在，
但界面提供确定反馈，不再表现为冻结。

## 本机恢复与导出边界

设备所有者完成两条恢复路径的实机测试：

1. “Leo Shell 应用信息”依次进入 Android/MIUI 的应用详情页，可以访问清除默认和卸载；
2. “打开原厂 MIUI 桌面”显示二次确认，并成功进入
   `com.miui.home/.launcher.Launcher`。

随后从 ADB shell 直接启动 `MaintenanceActivity`，系统返回 `SecurityException` 和
`not exported`，证明维护页不能绕过认证从外部 Intent 进入。默认 HOME 复查仍是 MIUI
Launcher。

Gate C 尚余：五分钟会话过期、进程死亡失效和完整失败锁定实机测试。完成后才安装
`homeCandidate`。

## 进程死亡与主动超时审计

设备所有者认证进入维护页后，通过 ADB 只结束 Leo Shell 进程并重新启动普通首屏。再次
触发隐藏手势时，应用正确显示 PIN 认证页，没有沿用旧会话；PIN 配置本身正常保留。

准备测试五分钟过期时，代码审计发现 v0.2.1 只在 `onResume()` 检查会话：若用户一直
停留在维护页，无法在到期瞬间主动退出。v0.2.2 增加前台倒计时和到期回调，显示剩余
`M:SS`，到期清除会话并 `finish()`；切到系统设置时停止刷新，返回时重新检查实际期限。

v0.2.2 的 6 个单元测试、Lint、源码清单和双 APK 清单审计全部通过：

- `safePreviewDebug` SHA-256：
  `af2d2f6ca597001f070cdb29378b75e9445dd3c9aca9ed45782db36d1999ea61`；
- `homeCandidateDebug` SHA-256：
  `b6ae0af1cea5e79c5ae3493b1321d704dcf624322d5225794c1263566708f1d4`。

v0.2.2 覆盖安装后，实机确认 `versionCode=4`、PIN 保留、默认 HOME 仍为 MIUI。设备
所有者认证进入维护页，截图确认倒计时从约 `4:52` 正常递减。为观察前台到期瞬间，测试
期间临时把 `stay_on_while_plugged_in` 从 `0` 设置为 USB 的 `2`；测试后必须恢复为 `0`。

五分钟期限到达后，`MaintenanceActivity` 主动结束并返回 Leo 普通首屏；设备所有者与
ADB 前台 Activity 均确认结果。测试用 `stay_on_while_plugged_in` 已从 `2` 恢复原值 `0`，
默认 HOME 仍为 MIUI Launcher。前台到期门槛通过。

## 锁定实机反馈

设备所有者连续输入五次错误 PIN，系统正确触发 30 秒锁定；估计期限结束后输入正确 PIN，
可以重新进入维护模式。功能成立，但锁定页只显示固定说明，没有每秒更新剩余时间，用户
只能估计何时结束。

v0.2.3 增加认证页锁定 ticker：锁定期间禁用 PIN 和提交，每秒显示剩余秒数；退出认证
页再进入时根据进程级期限继续倒计时，归零后自动恢复输入。下一次实机复测还要明确证明
退出再进入不能重置期限。

v0.2.3 的 6 个单元测试、Lint、源码清单和双 APK 清单审计全部通过：

- `safePreviewDebug` SHA-256：
  `c6116730b5e2879ae42a3a86f717d3af4f5e8b9bb511008a230d73b1ce12150b`；
- `homeCandidateDebug` SHA-256：
  `617a2eb314fff1bc3fcc6df8b0bf20ac52bcc6d8ebd2ac68af999d2f834f1620`。

覆盖安装后实机确认 `versionCode=5`、PIN 保留、默认 HOME 仍为 MIUI；等待最后一次显式
倒计时和退出再进入测试。

设备所有者最终确认：第五次错误后显示逐秒倒计时；退出认证页再进入时期限继续而不重置；
归零后正确 PIN 可以进入维护页。Gate C 至此通过。
