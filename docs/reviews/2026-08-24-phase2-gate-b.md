# Phase 2 Gate B：Safe Preview 安装前审计

日期：2026-08-24

## 目标

只允许普通应用形态的 `safePreview` 进入实机。它必须不能成为 HOME、不能开机自启、
不能自动拉起 Spotify，也不能请求 Android 权限。

## 安装前基线

- 设备：Xiaomi Mi Note Pro / `leo`；
- 系统：Android 7.0 / API 24；
- 当前 HOME：`com.miui.home/.launcher.Launcher`；
- Spotify：`com.spotify.music`，实机可用；
- 目标包：`io.github.leoaudio.shell.preview.debug`；
- 回退：卸载目标包；原厂 HOME 不作任何变更。

## 构建和清单结果

- `safePreviewDebug`：构建成功；
- `homeCandidateDebug`：只为离线清单比较构建，不安装；
- `safePreview` 编译清单包含 `LAUNCHER`，不包含 `HOME`；
- `homeCandidate` 编译清单包含 `LAUNCHER + HOME + DEFAULT`；
- 两个变体均不请求权限，不监听 `BOOT_COMPLETED`，不申请悬浮窗或安全设置权限；
- `safePreviewDebug` SHA-256：
  `d2a596c60bcf6a739e7b7b7baf2500b3f2b7302cb8bf0c3a90694924a6e7a803`；
- `homeCandidateDebug` SHA-256：
  `9848fe40b1f25cbd17f5bdf42e429cf322036f2fe905efcfdad91b083864d5d4`。

## Gate B 决定

允许安装并显式启动 `safePreviewDebug`，随后检查：

1. 默认 HOME 仍为 MIUI Launcher；
2. Spotify 只能由按钮触发；
3. 返回应用后不出现自动拉起循环；
4. 维护页原厂桌面出口保持禁用；
5. 卸载包后设备状态恢复。

不允许安装 `homeCandidateDebug`，也不允许清除或更改当前 HOME 默认项。

## 第一次安装尝试

ADB 返回 `INSTALL_FAILED_USER_RESTRICTED: Install canceled by user`。MIUI 未允许本次
USB 安装，因此应用没有写入设备、Activity 没有产生，当前 HOME 复查仍为
`com.miui.home/.launcher.Launcher`。

这是预期的用户授权边界，不以 Root 或关闭 MIUI 安全机制绕过。下一次尝试前，由设备
所有者在屏幕上明确允许 USB 安装；安装命令和 APK 哈希保持不变。

## 显式安装与首次启动结果

由于 MIUI 的“USB 安装管理”在显示确认按钮前直接禁止 ADB streamed install，改用透明
的本机确认路径：将同一个已核验 APK 放入 `/sdcard/Download/`，打开 MIUI 系统安装器，
由设备所有者在完整安装页面亲自确认。

- 安装成功，实机包版本为 `0.1.0-dev.1-preview-debug`；
- 实机包报告 `minSdk=24`、`targetSdk=36`；
- 安装后默认 HOME 仍为 `com.miui.home/.launcher.Launcher`；
- `MainActivity` 显式启动成功；
- 首屏正确识别 Spotify 已安装，并显示当前 MIUI HOME；
- 首次实机截图确认没有黑屏、严重布局溢出或意外系统入口；
- `homeCandidateDebug` 仍未安装。

Gate B 的安装与首屏部分通过。Spotify 按钮、隐藏维护手势和三个维护设置入口继续进行
交互验收。

## Spotify 显式启动

设备所有者点击“打开 Spotify”后，MIUI 首次显示“正在尝试开启 Spotify，是否允许”的
跨应用启动确认。所有者明确允许后，Spotify 的 `MainActivity` 正常进入前台，已有账号
和播放界面正常显示。

该行为证明首版采用的是用户动作触发，而不是开机广播或后台循环拉起。MIUI 的首次跨
应用授权需要纳入安装验收；后续还需验证授权是否持久、拒绝时的表现和清除数据后的行为。

## 隐藏维护入口骨架

设备所有者从安全预览首屏在 5 秒内连续点击 `LEO` 七次，成功进入
`MaintenanceActivity`。实机前台 Activity 和截图一致证明：

- 隐藏手势可重复触发；
- 维护警告明确显示“本地认证尚未实现”；
- Wi-Fi、VPN、Spotify 应用信息三个只读/系统设置入口可见；
- 原厂桌面出口为灰色且不可点击；
- 没有在认证和 Gate C 之前提前暴露恢复动作。

维护设置入口仍需逐项返回测试；之后才能引入本地认证和原厂桌面恢复动作。

设备所有者随后逐项确认 Wi-Fi 设置、VPN 设置和 Spotify 应用信息均能打开，并能返回
维护预览。Gate B 至此通过，下一步进入 Gate C 的维护认证与无电脑恢复验证。
