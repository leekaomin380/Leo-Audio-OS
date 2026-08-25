# Phase 3 Gate 3：最小 Shell 集成契约审计

日期：2026-08-25

## 裁定

Gate 3 可以在不取得 Xiaomi platform key、不修改 stock sepolicy、不使用 `/system/priv-app`、
不移除 MIUI Launcher 和不写设备的前提下实施。最小集成结构为
`/system/app/LeoShell/LeoShell.apk`，相对冻结的 Gate 2 只新增目录和 APK 两条语义记录。

契约允许进入机械实现，长期 Leo Shell app key 的密钥仪式随后已完成；但恢复工程仍不满足首次
system 写入条件，因此当前仍不讨论刷写。

## 证据与推理链

1. 现有 release flavor 的 package 是 `io.github.leoaudio.shell`，没有 debug suffix；Manifest
   请求零权限，只有三个 Activity，无 service/receiver/provider/shared UID。
2. 原厂 `mac_permissions.xml` 只把 Xiaomi signer 映射为 `platform` seinfo；项目独立 signer
   不匹配，因此保持 `default`。
3. 原厂 `seapp_contexts` 对 `_app + default + non-priv-app` 的最终规则是 `untrusted_app`；
   `/system/priv-app` 才会触发 `isPrivApp=true → priv_app`。所以 `/system/app` 是最小权限选择。
4. Gate 2 所有 app/priv-app 文件与目录的实际 filesystem label 都是 `system_file`，新增两条
   可使用相同 label，而不扩写运行时 policy。
5. Phase 2 已在 Android 7 实机证明 HOME intent、Spotify 显式启动、维护认证和 MIUI Launcher
   出口可运行；Gate 3 仍不会把这些历史事实冒充新 system 镜像的实机验证。

## 构建探针

现有 `homeCandidateDebug`：

- 908442 bytes；
- Android Debug signer，只有 v2；
- AGP 9.3.2 自动引入 `kotlin-stdlib:2.2.10`；
- 主 dex 1090 class definitions，APK 含多个 dex 和 Kotlin builtins。

使用 Android 官方提供的 built-in Kotlin opt-out 做不改源码探针后：

- `homeCandidateReleaseRuntimeClasspath` 为 `No dependencies`；
- unsigned release APK 为 22040 bytes；
- 单一 `classes.dex`，无 native library 或 Kotlin builtins；
- package、minSdk 和 HOME Manifest 身份保持不变；
- 尚未签名，因此不是 Gate 3 输入。

该探针只证明 Java-only 最小构建可行。机械实现必须使用 module-level `enableKotlin=false`，
不能把命令行兼容参数当成长期构建定义。

## 进入机械实现前必须闭合

1. 把 versionCode 固定为 10、versionName 固定为 `0.3.0-gate3.1-home`；
2. 固化 Java-only module 配置，并让依赖、dex、APK payload 门禁失败即停止；
3. 把 system app 不可普通卸载的事实写入维护页：回退措辞改为“清除默认项或停用”；
4. 建立 release APK 的 Manifest、signer 和 v1/v2 校验脚本；
5. 建立只接受两个新增路径的 overlay 与差异验证器；
6. 在用户明确授权后单独执行 app key 密钥仪式，公开证书与 fingerprint，私钥离线双备份。

上述六项现已完成；U 盘曾出现间歇性读取超时，虽然恢复验证通过，仍应增加第二个可靠离线副本。
下一步是 Terra medium 的 staging、metadata、ext4 和 sparse 机械构建。

## 风险边界

- 干净 `/data` 上存在两个 HOME 候选，可能出现 Resolver；Gate 3 不预写默认 HOME。
- 当前设备安装的是 `.debug` package，与 release package 不同；未来实机测试必须先记录两者并
  设计迁移，不能把 debug 数据或 PIN 自动视为 release 数据。
- 预装 system app 不能依赖普通卸载回退；MIUI Launcher、ADB/recovery 停用和 Gate 2 镜像恢复
  必须分别验证。
- PIN 是维护模式门，不是磁盘加密或高强度防暴力认证；进程重启会重置失败计数。
- Gate 3 仍使用 development-unverified 零尾 system，不能与 stock `wait,verify` boot 配对。
