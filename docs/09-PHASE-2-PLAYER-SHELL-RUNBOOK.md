# 09：Phase 2 播放器 Shell 原型路书

## 1. 阶段目标

Phase 2 在当前已验证的 MIUI 9 / Android 7.0 实机上实现一个**完全可逆的专用播放器
外壳**。它负责产品入口、Spotify 生命周期、维护入口与故障恢复，但不替换 `system`、
`vendor`、`boot`、`recovery`，也不删除原厂 Launcher。

阶段结束时，普通使用状态应表现为一台网络音频播放器；维护人员仍能通过受控路径恢复
MIUI 桌面、网络配置、诊断和 ADB。这个原型用于验证产品行为，不声称已经完成精简 ROM。

## 2. 已冻结的实机基线

| 项目 | 当前值 |
|---|---|
| 设备 | Xiaomi Mi Note Pro / `leo` |
| 系统 | Android 7.0 / API 24，当前 MIUI 基线 |
| 当前 HOME | `com.miui.home/.launcher.Launcher` |
| 播放器 | `com.spotify.music` |
| 音频边界 | 保持已验证的 32-bit `audioserver` + stock 32-bit primary HAL |
| 安装方式 | 首期仅使用普通 APK + ADB，不写系统分区 |

Spotify 版本会继续由私有输入清单和实机证据登记；公开仓库不包含 APK、账号数据或
第三方签名材料。

## 3. 产品状态模型

```text
BOOT
  -> NORMAL_SHELL
       -> SPOTIFY
       -> RECOVERY_PROMPT      (Spotify 缺失、崩溃或无法启动)
       -> MAINTENANCE_AUTH     (隐藏手势触发)
            -> MAINTENANCE
                 -> NORMAL_SHELL
                 -> STOCK_HOME (明确确认的安全退出)
```

`NORMAL_SHELL` 不提供应用抽屉。`MAINTENANCE` 是 Android 通用能力的受控窗口，不是第二个
普通桌面。任何自动跳转都必须有次数限制，避免 Shell 与 Spotify 形成崩溃循环。

## 4. 关键节点与交付物

### P2.0 — 基线和安全门

- [x] 确认设备在线、系统 API、当前 HOME 和 Spotify 包名；
- [x] 记录安装前 HOME、包状态和恢复命令；
- [x] 确认原厂 Launcher 保持启用；
- [x] 确认 ADB 可在 Shell 失效时停用或卸载原型；
- [x] 形成安装前检查脚本和只读报告。

**Gate A：**没有两条相互独立的恢复路径，不设置 Leo Shell 为默认 HOME。

### P2.1 — 产品行为与最小 Shell

- [x] 建立兼容 API 24 的独立 Android 工程；
- [x] 以隔离构建变体注册 `HOME`/`DEFAULT`/`LAUNCHER`，安全预览不包含 `HOME`；
- [x] 实现克制的普通模式界面；
- [x] 检测 Spotify 是否安装，并由用户动作显式启动；
- [x] Spotify 缺失或启动失败时留在可诊断界面，不循环拉起。

**Gate B：**本地构建、清单审计和普通 Activity 启动通过，才能安装到实机。

### P2.2 — Spotify 生命周期

- [ ] 区分未安装、可启动、前台退出、进程崩溃和系统回收；
- [ ] 为自动恢复设置退避、次数上限和人工停止入口；
- [ ] 不读取 Spotify 私有数据，不向 Spotify 授予 Root；
- [ ] 验证登录、播放、切歌、下载和离线播放不受 Shell 影响；
- [ ] 验证返回键、Home 键、锁屏和解锁后的确定行为。

### P2.3 — 隐藏维护模式

- [x] 采用不易误触、但无需联网即可复现的隐藏触发动作；
- [x] 使用本地认证，不把凭据写入仓库或日志；
- [x] 提供 Wi-Fi、VPN、Spotify 和基础恢复的受控入口；
- [x] 明确显示维护状态，并在超时后返回普通模式；
- [x] 提供经过二次确认的“回到原厂桌面”。

**Gate C：**维护入口、认证、超时和原厂桌面出口全部实测后，才允许选择 Leo Shell 为
默认 HOME。

### P2.4 — 故障保护

- [ ] Shell 连续崩溃不会阻塞开机；
- [ ] Spotify 连续崩溃不会形成拉起风暴；
- [ ] 配置损坏时进入安全界面，而不是黑屏；
- [ ] 保留 ADB 卸载/停用路径和原厂 Launcher；
- [ ] 记录每个故障的用户可见表现、恢复步骤和日志证据。

### P2.5 — 实机回归

- [ ] 冷启动、热重启和解锁；
- [ ] 耳机未插入、插入、拔出和重新插入；
- [ ] Spotify 播放、暂停、切歌、崩溃和恢复；
- [ ] Wi-Fi 与 VPN 中断、恢复；
- [ ] 长时间暂停后重新播放；
- [ ] 维护模式进入、超时、退出和错误认证；
- [ ] 临时 ADB 开启/关闭；
- [ ] 恢复 MIUI Launcher 和卸载 Shell。

### P2.6 — 阶段收口

- [ ] 发布源码、构建说明、测试矩阵和隐私边界；
- [ ] 固化 APK 哈希、源码提交和实机验收记录；
- [ ] 确认现有 HiFi 播放链与 Phase 1 基线一致；
- [ ] 将验证成功的产品行为转化为 Phase 3 镜像构建输入。

## 5. 安全与回退设计

Phase 2 的不可破坏约束：

1. 不执行分区刷写；
2. 不删除、不冻结 `com.miui.home`；
3. 不以 Magisk 模块或 system overlay 获得唯一 HOME；
4. 不把 ADB 作为唯一恢复通道；
5. 未通过 Gate C 前，不在“始终使用”对话框中选择 Leo Shell；
6. 每次设备写操作前先记录目标、当前状态、回退命令和预期结果；
7. 安装包签名、版本和 SHA-256 必须进入测试记录。

初期两条恢复路径为：

- Android 设置/Resolver：清除 Leo Shell 的默认 HOME，选择 MIUI Launcher；
- ADB：停用或卸载项目包，并显式启动 `com.miui.home/.launcher.Launcher`。

进入默认 HOME 实验前，还应增加无需电脑的第三条本机恢复入口。

## 6. 验收标准

Phase 2 只有在以下条件同时满足时结束：

- 日常路径不需要进入 MIUI Launcher；
- 开机和解锁能够稳定到达播放器入口；
- Spotify 正常播放，并保持 Phase 1 已验证的有线 HiFi 路径；
- Spotify、网络或 Shell 故障后存在确定恢复行为；
- 维护模式可进入、可认证、可退出；
- 原厂 Launcher 与 ADB 恢复路径未丢失；
- 原型可卸载，卸载后设备恢复当前 MIUI 行为；
- `system`、`vendor`、`boot` 和 `recovery` 未发生改变。

## 7. 停止条件

出现以下任一情况，立即停止推进默认 HOME 或自动启动实验：

- 原厂 Launcher 被禁用、丢失或无法显式启动；
- ADB 授权失效且本机维护入口尚未验证；
- Shell 出现连续崩溃、黑屏或无法解除默认项；
- Spotify 播放链、耳机 HiFi 路径或暂停关断行为发生退化；
- 任何步骤要求修改分区或跨越本路书的授权边界。

## 8. 用户配合节点

用户只需要在实机验收节点配合：

1. 首次安装后观察普通 Activity；
2. Gate C 通过后确认一次 HOME 选择对话框；
3. 插拔耳机并完成固定曲目播放/暂停；
4. 模拟网络中断和恢复；
5. 最终亲自验证隐藏维护入口和无电脑恢复。

所有可能改变默认 HOME 的动作都在执行前单独说明，不以脚本悄然完成。
