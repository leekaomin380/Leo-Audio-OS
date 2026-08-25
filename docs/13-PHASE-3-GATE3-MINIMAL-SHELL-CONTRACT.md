# 13：Phase 3 Gate 3 最小 Leo Shell 集成契约

## 1. 目的

Gate 3 从冻结标签 `phase3-gate2-v0.1` 出发，只向 system 加入一个由项目独立密钥签名的
Leo Shell APK。它证明构建器能表达、审计并复现一个最小有意修改，不负责精简 MIUI，也不授权
设备写入。

Gate 3 的成功定义是：原有 3923 条 system 路径的契约级属性全部不变，只新增一个目录和一个 APK；
重建后的 ext4、完整分区容器和 sparse 回环继续通过 Gate 2 的全部门禁。

## 2. 唯一允许的文件系统差异

相对 Gate 2，只允许新增：

| ext4 路径 | 类型 | UID:GID | mode | SELinux xattr | capability |
| --- | --- | --- | --- | --- | --- |
| `/app/LeoShell` | directory | `0:0` | `0755` | `u:object_r:system_file:s0` | 无 |
| `/app/LeoShell/LeoShell.apk` | regular | `0:0` | `0644` | `u:object_r:system_file:s0` | 无 |

两个路径的 mtime 使用构建器已锁定的 `1230739200`。APK 内容哈希由最终签名产物决定并进入
Gate 3 manifest。除此之外，不允许新增、删除或修改任何文件、符号链接、xattr、权限、owner、
mtime 或 capability。

ext4 inode number 是 allocator 地址，不是稳定文件身份；加入两个 inode 后，后续原厂路径的 inode
number 可以顺延，但其他字段必须精确不变。`/app` 因增加一个直接子目录，其 directory link count
必须恰好增加 1。新目录在当前 4096-byte block geometry 下的可观察 size 必须为 4096 bytes；这些
物理变化必须独立登记，不能被笼统忽略。

预期语义计数由 3923 增至 3925：directory 由 424 增至 425，regular 由 3261 增至 3262，
symlink 保持 238。17 条音频兼容清单必须继续全部通过。

## 3. 为什么使用 `/system/app` 而不是 `/system/priv-app`

Leo Shell 只需要普通 Activity、HOME intent 和用户主动触发的系统设置入口；它不需要 privileged
permission、shared UID、platform signature、后台服务、开机广播或系统设置写权限。

原厂 boot 中的 `seapp_contexts` 已给出决定性边界：普通 `_app` 且 `seinfo=default` 进入
`untrusted_app`；`isPrivApp=true` 才进入 `priv_app`。项目独立证书不在原厂
`mac_permissions.xml` 的 Xiaomi signer 映射中，因此保持 `seinfo=default`。放入
`/system/app` 后，PackageManager 只把它识别为预装 system app，不把它提升为 privileged app。

Gate 3 因而禁止：

- 放入 `/system/priv-app`；
- 使用或仿冒 Xiaomi platform key；
- 声明 `sharedUserId` 或固定 Android UID；
- 修改 `mac_permissions.xml`、`seapp_contexts` 或二进制 sepolicy；
- 为 Leo Shell 新建 SELinux domain。

这使 APK 文件本身保持 `system_file`，运行进程保持普通应用隔离域。首次实机验证时仍须从
`ps -AZ`、`dumpsys package` 和 AVC 日志确认实际 domain，静态推导不能冒充实机结论。

## 4. APK 身份与 Manifest 契约

Gate 3 只接受 `homeCandidateRelease` 对应的 release 身份：

- package：`io.github.leoaudio.shell`；
- versionCode：10；versionName：`0.3.0-gate3.1-home`；
- minSdk：24；目标设备 Android 7.0；
- HOME Activity：`io.github.leoaudio.shell.MainActivity`；
- `MAIN + HOME + DEFAULT` 与可见 `LAUNCHER` 入口；
- `MaintenanceActivity`、`MaintenanceAuthActivity` 必须保持 non-exported；
- 不得有 `android:debuggable=true`、`testOnly`、`sharedUserId`；
- 不得声明任何 Android permission；
- 不得新增 service、receiver、provider、native library 或动态下载代码；
- 不监听 `BOOT_COMPLETED`，不申请 overlay、device-admin、accessibility、root 或
  `WRITE_SECURE_SETTINGS`。

MIUI Launcher `com.miui.home/.launcher.Launcher` 必须继续存在、启用且未修改。Gate 3 不写
preferred-activity、Role、Settings 数据库或 `/data`，因此不静默把 Leo Shell 设为默认 HOME。
在无既有默认项的干净数据分区上出现 HOME 选择器属于预期风险，必须在未来实机 Gate 明确观察。

## 5. Java-only 构建与依赖边界

当前源码全部为 Java，但 AGP 9.3.2 默认启用 built-in Kotlin，使现有 debug APK 自动带入
`kotlin-stdlib:2.2.10`：APK 为 908442 bytes，主 dex 有 1090 个 class definitions。这个产物
还使用 Android Debug 证书，只能作为 Phase 2 证据，禁止进入 system。

Android 官方允许对没有 Kotlin source 的 module 使用 `android { enableKotlin = false }`，从而
同时移除 Kotlin 编译任务和自动 stdlib 依赖。一次不改源码的本机探针已经证明：禁用后 release
runtime classpath 为 `No dependencies`，unsigned APK 为 22040 bytes、单 dex，且 Manifest
身份不变。Gate 3 机械实现必须把 module-level 设置固化并加入门禁，不能长期依赖即将由 AGP 10
移除的全局 `android.builtInKotlin=false` 兼容开关。

上游依据：

- [Android 官方：按 module 禁用 built-in Kotlin](https://developer.android.com/build/migrate-to-built-in-kotlin#selectively-disable)；
- [Android 官方：AGP 9.0 built-in Kotlin 行为变化](https://developer.android.com/build/releases/agp-9-0-0-release-notes)。

Gate 3 SBOM 应只有 Leo Shell 自身、Android Framework API 和构建工具身份；任何 runtime Maven
dependency、多个 dex、`.so`、嵌入式 APK/JAR 或 Kotlin builtins 都触发停止。

## 6. 签名边界

最终 APK 必须使用项目拥有的独立 Leo Shell app key，不使用 debug key、AOSP test key、Xiaomi
key 或 Android platform key。私钥不得进入 Git、构建日志、镜像或普通云盘；仓库只保存证书、
SHA-256 fingerprint、算法和有效期。

目标设备为 Android 7.0，原生支持 APK Signature Scheme v2。为兼顾独立离线校验与旧工具，
Gate 3 固定同时生成 v1 和 v2，禁用该平台不支持的 v3/v4 依赖；最终产物必须由 `apksigner
verify --verbose --print-certs` 确认 signer 唯一、v1/v2 为 true，且 fingerprint 等于项目 manifest。
Android 官方签名说明见 [App signing](https://source.android.com/docs/security/features/apksigning)
与 [APK Signature Scheme v2](https://source.android.com/docs/security/features/apksigning/v2)。

长期 app key 已按独立密钥仪式生成，公开证书与 fingerprint 登记在
`manifests/leo-shell-app-key-v1.*`；私钥主副本、外部加密副本和密码均保持在 Git 之外。恢复
验证与介质稳定性限制见
[`2026-08-25-phase3-gate3-key-ceremony.md`](reviews/2026-08-25-phase3-gate3-key-ceremony.md)。
该 app key 不改变 OTA、verity 和 platform key 仍未建立的事实。

## 7. 构建流程

机械实现必须分成可单独验证的步骤：

1. 从冻结的 Gate 2 staging 和 metadata 复制到新的私有 Gate 3 工作目录；
2. 构建两次 dependency-free unsigned `homeCandidateRelease`，要求字节哈希相同；
3. 使用已登记 app key 生成最终 v1+v2 APK，并记录证书 fingerprint 与 APK SHA-256；
4. 只加入上述两个路径，扩展 canned `fs_config` 和封闭世界 `file_contexts`；
5. 验证原有 3923 条契约属性精确不变；inode allocator 地址与 `/app` link count 按上述规则单列，
   新增两条精确命中且负向 lookup 仍失败；
6. 使用 Gate 2 builder 重建 ext4、运行 `e2fsck -f -n` 并导出完整语义清单；
7. 自动生成 Gate 2 → Gate 3 差异报告、SBOM、空间预算与所有产物 SHA-256；
8. 构建第二份独立候选，要求语义相同，并解释任何物理字节差异；
9. 生成零尾 partition raw、Android sparse，并完成 `sparse → raw` 全字节回环。

所有步骤继续只在本机私有目录进行。不得调用 ADB、fastboot、recovery，也不得生成或修改 boot、
verity、FEC、persist、modem、tz、aboot 等分区内容。

## 8. 静态硬门

Gate 3 候选必须同时满足：

- 基线提交可追溯到 `phase3-gate2-v0.1`；
- APK package/version/Manifest 与本契约相符，release 产物不可 debuggable；
- signer 不是 Android Debug/Xiaomi/AOSP test/platform，且 fingerprint 精确命中项目 allowlist；
- v1/v2 签名均验证通过，签名后不再做 zipalign、压缩或任何字节修改；
- runtime dependency 数为零；APK 单 dex、无 native code、无嵌套可执行载荷；
- 相对 Gate 2 只有两个新增路径，原有 3923 条契约属性不变；inode 与 link count 只接受上述精确规则；
- 新增路径 DAC、SELinux xattr、mtime 与本契约相同，无 capability；
- ext4 feature/geometry/journal 不变，`e2fsck -f -n = 0`；
- 完整分区不超出 1744830464 bytes，尾部继续全零；
- Android sparse header 与完整 raw 回环通过；
- MIUI Launcher 和全部原厂 system 应用仍在；
- 报告和 Git index 不含 APK、ROM、镜像、私钥或专有文件。

## 9. 回退与已知限制

Gate 3 只准备回退材料，不执行设备回退。未来首次实机 Gate 至少需要两条独立路径：

1. 从认证维护页显式打开 MIUI Launcher并清除 Leo 默认 HOME；
2. 从已验证 recovery/ADB 停用 `io.github.leoaudio.shell` 或恢复冻结的 Gate 2 system。

预装 system app 不能依赖“卸载 APK”作为主要回退。现有维护页中关于卸载候选包的文字适用于
Phase 2 data app，在 Gate 3 release APK 中必须改成“清除默认项或停用”，且在差异报告中登记
为 Leo Shell 自身版本变化，不得修改原厂文件。

本地 PIN 保护是设备模式切换门，不是高强度磁盘安全：首次无数据状态需要所有者 enrollment，
失败计数和 30 秒锁定仍是进程级状态，重启进程会重置。Gate 3 不扩大它的安全声明。

## 10. 停止条件

- 需要 `/system/priv-app`、platform key、shared UID 或新增 SELinux allow 才能运行；
- 不能消除 Kotlin/第三方 runtime dependency；
- 无法建立长期 app key 的离线保存和恢复策略；
- APK 需要修改 MIUI Launcher、Settings 数据库或 `/data` 才能成为 HOME 候选；
- 任一原厂路径、音频兼容项或 Gate 2 ext4 参数发生意外变化；
- recovery、system 恢复和原厂 Launcher 入口尚未形成独立回退路径，却要求写入设备；
- 任何步骤要求把私有输入或签名私钥加入公开仓库。

## 11. 下一执行档

契约审计见
[`2026-08-25-phase3-gate3-contract-audit.md`](reviews/2026-08-25-phase3-gate3-contract-audit.md)。
契约冻结后，进入 Terra medium 的机械实现：固化 Java-only module 设置、建立 release APK 门禁、
实现 staging 的二路径 overlay 和自动差异报告。遇到签名治理、SELinux/PackageManager 偏差、
fsck、verity 或不可解释的构建非确定性时，立即停下并切回 Sol high。
