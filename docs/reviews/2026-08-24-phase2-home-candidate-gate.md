# Phase 2 HOME Candidate 安装门槛

日期：2026-08-24

## 决定

Gate B 安全预览和 Gate C 维护认证均已通过。允许安装 `homeCandidateDebug`，但安装本身
不等于允许立即选择“始终使用”。候选包必须先作为普通显式 Activity 完成自己的 PIN 和
恢复出口验证。

## 当前实机状态

- 默认 HOME：`com.miui.home/.launcher.Launcher`；
- 已安装安全预览：`io.github.leoaudio.shell.preview.debug`；
- 待安装 HOME 候选：`io.github.leoaudio.shell.debug`；
- MIUI Launcher 保持启用；
- ADB 在线；
- `system`、`vendor`、`boot`、`recovery` 不变。

## 候选包审计

- 版本：`0.2.4-dev.1-home-debug` / versionCode 6；
- SHA-256：
  `ca3aa32943810eb8227d072f84609896b8463d63ea648c20c1252f03229fd0c3`；
- 标签：`Leo Shell HOME 候选`；
- 包含 `LAUNCHER + HOME + DEFAULT`；
- 不请求 Android 权限；
- 不监听 `BOOT_COMPLETED`；
- 不申请悬浮窗或安全设置权限；
- 采用与安全预览相同的已核验源码和本地调试签名；
- Android Lint、6 个单元测试、源码和编译清单校验通过。

同次构建的安全预览 SHA-256：
`8b2b48e44a55423380046b76c75f4547d928a5d55c94d9a8cad7c2871f42273b`。

## 实机顺序

1. 通过 MIUI 系统安装器由设备所有者确认安装候选；
2. 读取实机版本、HOME resolver 和包清单；
3. 不按 Home，先显式打开候选 Activity；
4. 在候选包内单独设置维护 PIN；
5. 验证候选的 Leo 应用信息和 MIUI Launcher 出口；
6. 按 Home，若出现 Resolver，先选择一次性进入候选；
7. 再次验证 Spotify、维护认证和 MIUI 出口；
8. 只有全部正常，才由设备所有者选择“始终使用”Leo HOME；
9. 选择后再次核对默认 HOME，并执行 Home/Back/Spotify/重启测试。

## 三条恢复路径

1. 候选内认证维护页：打开 MIUI Launcher；
2. 候选内 Leo Shell 应用信息：清除默认项或卸载；
3. ADB：显式启动 `com.miui.home/.launcher.Launcher`，必要时卸载
   `io.github.leoaudio.shell.debug`。

安全预览包继续保留为非 HOME 的第四入口，直到候选完成重启和崩溃测试。

## 停止条件

- 安装候选后 MIUI Launcher 无法显式启动；
- 未选择默认前就发生无法解除的 HOME 劫持；
- 候选 PIN、会话或恢复出口与已验收的安全预览不一致；
- Spotify 无法显式启动或出现拉起循环；
- 系统要求关闭安全中心、修改分区或删除 MIUI Launcher。

## 首次安装发现

候选 `0.2.4-dev.1` 安装后，实机包、HOME intent 和版本均正确；默认 HOME 仍为 MIUI。
显式启动截图却出现视觉矛盾：产品标语位置被动态改成“HOME 候选”，绿色状态仍写“安全
预览”。原因是 `shell_mode_state` ID 错放到产品标语 TextView。

该错误不影响 HOME 能力，但会误导操作者，因此在设置 PIN 和选择默认 HOME 前主动停止。
v0.2.5 修正 ID，并把“动态状态 ID 必须绑定模式状态文本”加入源布局校验器，防止同类
错误再次通过构建。

修复版通过 6 个单元测试、两个变体的 Android Lint、源码清单和编译 APK 清单审计：

- `safePreviewDebug` SHA-256：
  `fd2ec453b054b8e9f1ad418a5b14230cfdbf7484d8e48ee4e1f8f006f410ef40`；
- `homeCandidateDebug` SHA-256：
  `7b54f0df8845c786e9678fb6eb20b887976c68f5b61ea287804087d6276dd9dd`。

v0.2.5 覆盖安装后实机确认 `versionCode=7`。显式启动截图显示产品标语、绿色
“HOME 候选·尚未设为默认 HOME”和当前 MIUI HOME 三者一致，视觉门槛通过；默认 HOME
仍未改变。

## 维护页实机崩溃与兼容修复

候选包首次设置 PIN 后没有进入维护页，而是回到就绪页。只读采集的系统日志确认：认证
流程已经请求启动 `MaintenanceActivity`，但 MIUI 在解析维护页第一个 `Button` 时于
`MiuiTypedArray` / `StringBlock` 发生 `ArrayIndexOutOfBoundsException`，进程随后被系统
重建。故障发生在布局加载阶段，不是 PIN 校验失败。

操作在选择默认 HOME 前停止；默认 HOME 始终保持 `com.miui.home`，系统分区未改动。
兼容修复定为 v0.2.6：

- 从全部布局移除会进入旧 MIUI patched inflater 路径的 `android:textAllCaps`；
- 用 Manifest 占位符提供两个变体的应用标签，取消同名字符串资源覆盖，缩小资源表差异；
- 将以上两项加入源码门禁，防止以后回归；
- 只有 v0.2.6 通过构建、清单审计和实机 PIN → 维护页复测后，才恢复 HOME 候选流程。

v0.2.6 本机构建门禁已通过：6 个单元测试、两个变体的 Android Lint、源码门禁及编译
APK 清单审计均无失败项。待实机安装的产物为：

- `safePreviewDebug`：
  `395556bb664a8a0439daea3ddfbc3d994795f164aab5fec4b510d0a33fab2557`；
- `homeCandidateDebug`：
  `bf8e450ee74e5b0ccbc23b669e141c37519bd1eff9a4036d048583a1c579c31c`。

实机覆盖更新确认 `versionCode=8` / `0.2.6-dev.1-home-debug`，默认 HOME 仍为 MIUI。
候选包保留此前设置的 PIN；正确 PIN 后 `MaintenanceActivity` 在 84 ms 内显示，日志没有
`FATAL EXCEPTION`，用户也确认已经进入维护页。旧 MIUI 布局解析故障修复门通过。

候选维护页的两个本地恢复出口也已由用户实测：应用信息页可以打开并正常返回；显式打开
MIUI Launcher 可以回到原厂桌面并结束维护会话。过程中没有清除数据、停用或卸载任何
组件。由此，进入实际 HOME 语义测试前的恢复门通过。

系统未保存第三方 HOME 偏好，MIUI 由系统优先级直接获选。为避免无谓清除原厂偏好，使用
显式 `MAIN + HOME` Intent 对候选执行一次性 HOME 语义测试，不写入默认值。候选 119 ms
启动成功；用户确认可以打开 Spotify，按 Home 键可立即回到 MIUI。一次性 HOME 门通过，
允许进入由设备所有者在系统设置中选择默认 HOME 的步骤。

设备所有者随后在系统“默认桌面”页面选择 `Leo Shell HOME 候选`。系统侧解析确认
`isDefault=true`，HOME 组件为 `io.github.leoaudio.shell.debug/.MainActivity`；前台任务也
确认为带 `MAIN + HOME` 的 Leo Activity。界面绿色状态正确显示专用模式，本轮无崩溃。
进入设置默认后的运行态和重启验收。

设置默认后的返回键测试发现：在 Leo 根页按 Back 会结束根 Activity 并出现黑屏，按 Home
可立即重建 Leo；维护入口仍然正常。该现象不会损坏系统，但不符合专用设备必须始终存在
稳定前台表面的要求，因此暂停重启门。v0.2.7 在 `HOME_CAPABLE` 变体中消费根页 Back，
安全预览变体仍保留正常返回行为。实现同时覆盖 Android 7 的传统返回回调和 Android 13+
的原生预测式返回回调；源码门禁同步加入该约束。

v0.2.7 重新通过 6 个单元测试、两个变体的 Android Lint、源码门禁和编译 APK 清单审计：

- `safePreviewDebug`：
  `1951be6edd76d0df0938ba6d838b7a66cff721871f61d8079e300eb91ebba95e`；
- `homeCandidateDebug`：
  `5212d206b32825fc8ef0f3221eb9558c6c4bfb05cab98c2f84f1d5270a5b756b`。

第一次构建曾被 Android 16 预测式返回检查准确拦截；补齐新旧两条返回路径后才放行，未建立
Lint baseline，也未降低检查等级。

v0.2.7 覆盖更新后，用户确认三按钮返回键不再退出 Leo，黑屏现象消失。系统侧确认
`versionCode=9`、Leo 仍为 `isDefault=true` 的 HOME 组件，日志没有 Leo 崩溃记录；根页
返回键门通过。
