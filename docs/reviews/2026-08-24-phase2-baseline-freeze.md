# Phase 2 基线冻结：Leo Player Shell v0.2.7

日期：2026-08-24

## 冻结结论

Phase 2 的可逆 MIUI HOME 原型基线冻结为 `v0.2.7-dev.1`。该基线已经安装在
设备 `68f5f468` 上，Leo HOME 候选为默认 HOME；没有修改 system、vendor、boot、recovery
或原厂 MIUI Launcher。

这不是可刷入固件，也不是 Phase 3 的系统镜像。它是下一阶段继续开发和回归比较的稳定起点。

## 实机状态

- 包：`io.github.leoaudio.shell.debug`；
- versionCode：`9`；
- versionName：`0.2.7-dev.1-home-debug`；
- 默认 HOME：`io.github.leoaudio.shell.debug/.MainActivity`，系统解析为 `isDefault=true`；
- 原厂 Launcher：`com.miui.home/.launcher.Launcher`，仍启用并可从维护页打开；
- PIN：已设置，候选更新后仍可验证；
- 系统分区：未改动；
- 权限：应用不请求 Android 权限，不含启动广播、悬浮窗或安全设置能力。

## 已冻结的行为

- Leo 就绪页和 Spotify 显式启动；
- 隐藏七次点击维护入口；
- 本地 6 位 PIN、PBKDF2 派生值、五次失败后 30 秒锁定；
- 五分钟维护会话及退出即锁定；
- Wi-Fi、VPN、Spotify 应用信息和 Leo 应用信息入口；
- 维护页返回 MIUI Launcher；
- 默认 HOME 语义启动；
- HOME 根页面三按钮返回键不退出、不黑屏；
- 旧 MIUI 维护页布局崩溃修复；
- 安全预览变体仍不声明 HOME。

## 构建证据

以下命令均已通过：6 个单元测试、两个变体 Android Lint、源码门禁和 APK 清单审计。

- `safePreviewDebug` SHA-256：
  `1951be6edd76d0df0938ba6d838b7a66cff721871f61d8079e300eb91ebba95e`；
- `homeCandidateDebug` SHA-256：
  `5212d206b32825fc8ef0f3221eb9558c6c4bfb05cab98c2f84f1d5270a5b756b`。

设备历史崩溃记录中出现的 `v0.2.5` 维护页 InflateException 是修复前的旧记录；本次
v0.2.7 日志没有新的 Leo 崩溃。冻结判断以当前版本、当前日志和实机行为为准。

## 尚未冻结为完成项

- v0.2.7 更新后的 Spotify → Home 完整回归；
- 冷启动/热重启后默认 HOME 保持；
- 耳机插拔、网络中断、Spotify 崩溃和长时间播放观察；
- 正式 release 签名、更新机制和 Phase 3 系统镜像构建。

## 回退

维护页可打开 MIUI Launcher；Leo 应用信息页可清除默认项或卸载候选包。ADB 仍可显式
启动 `com.miui.home/.launcher.Launcher`。安全预览包继续作为非 HOME 的旁路验证入口。
