# Phase 4：首次受控写入与持久启动验收

日期：2026-08-26

设备：Xiaomi Mi Note Pro（`leo`）单台参考机

基线：MIUI `V9.2.3.0.NXHCNEK` / Android 7.0

## 裁决

**正式 project system/boot 配对已在参考设备上完成首次受控写入、临时启动验收和持久启动验收。**

这证明当前第一代、MIUI 基础上的 Leo Audio OS 原型可在真实 `leo` 上通过 legacy dm-verity 启动，
保留既有 userdata 中的 Spotify 安装与登录态，并维持外放、有线耳机和原厂 HiFi 播放。它不证明
第二代源码系统已经完成，也不构成对其他设备的刷写授权或公开固件发布。

## 写入身份与范围

| 成员 | SHA-256 | 实际动作 |
| --- | --- | --- |
| verified system raw | `e18a6fc83c59e09415d4a802a052c66fccf46e420b1f25f752e85546f8affad4` | 配对身份核验 |
| Android sparse system | `afa12b23e4570f96cc5e4ee70cf754779c75cf834a9d61f481f08d1a96e21eb1` | 首次确认后写入 `system` |
| project boot | `dfca241d75d494e0d85502d1368a3475f0e2576dd69b28274fcf4532a2779685` | 先临时启动，第二次确认后写入 `boot` |
| release-set manifest | `ec1f23178e7825b28ac1dbb6f348a7eed97b7f3776e69b1a58d63ab4d8123e5a` | 绑定正式 tuple |

实际分区写入只有 `system` 和 `boot`。没有写入或清除 `userdata`、`recovery`、`persist`、`modem`、
`tz`、`aboot`、Bootloader 或其他分区；没有执行 `flash_all`。

## 写入前保护

1. fastboot 身份为 `MSM8994`，`oem device-info` 报告 bootloader 与 critical 均已解锁；
2. exact stock recovery 的已知前缀与冻结 SHA-256 相符；正常 recovery 路径实测音量键导航、
   MiAssistant/ADB sideload 与返回 fastboot；未选择数据清除；
3. 直接 `fastboot boot` stock recovery 时出现 `ro.bootmode=unknown`、无按键输入并自动超时重启，
   因此没有把该路径误记为完整通过；真正的救援入口由正常 recovery 启动路径证明；
4. 写入前 system block device 大小为 `1744830464` bytes，SHA-256 为
   `f54d6199e5becb90a8d9c7187bc1b675d28ab82244aa2c0e18cb9cff84778482`，与 exact stock system
   `ec6edfd79adb1f6053adcc6fcb1927fabd93fe3756d9e7c7af8a7abd0dcd3e7d` 不同；
5. 该当前 system 由手机只读流出，一次流同时写入两块独立外置物理介质；两份均完成完整物理
   读回，大小和 SHA-256 一致。公开记录不保存设备序列号、介质 UUID 或卷名；
6. exact stock boot/system/recovery 与 development fallback 保留在私有恢复材料中。

## 执行记录

### 1. system

用户在看到唯一目标、哈希与风险后明确确认写入 `system`。Android sparse 被 fastboot 分为 6 段，
6 次发送和 6 次写入全部返回 `OKAY`，总耗时 `65.215s`。写入后设备仍稳定枚举为 fastboot。

fastboot 输出的 `skip copying system image avb footer` 是主机工具面对 Android 7 legacy verified
boot 镜像的通用 AVB 提示；本项目使用 BootSignature v1 与 system dm-verity，不使用 AVB footer。

### 2. 同 hash project boot 临时启动

没有立即写入 boot。先以 `fastboot boot` 临时启动上述 `dfca241d...79685`，发送和启动均为
`OKAY`。Android 完成启动后：

- `/system` 为 `/dev/block/dm-0` 上的只读 ext4；
- 内核日志出现 `Enabling dm-verity for system (mode 0)`；
- 未发现 verity、EXT4 或 I/O 错误；
- `/system/app/LeoShell/LeoShell.apk` 为 `0.3.0-gate3.1-home`；
- Spotify `9.1.50.1906` 的 base 与 3 个 split（共 4 个 APK）继续存在于 userdata；
- 原有 userdata 的 HOME preference 最初仍指向 MIUI Launcher，经 Android 7 支持的
  `cmd package set-home-activity` 可逆切换后，HOME 解析和实体 Home 键均进入 Leo Shell；
- 用户确认 Spotify 登录保留，外放、有线耳机和 HiFi 均正常。

HOME preference 的行为说明“把 Shell 放入 `/system/app`”不等于替换既有 userdata 中的默认桌面
选择。后续首次开机/恢复出厂后的 provisioning 必须显式设计，不能依赖人工 ADB 命令。

### 3. 连续播放与热状态

耳机、HiFi、Spotify 熄屏连续播放约 10 分钟。采样期间：

- Spotify 从第 1 首连续跨越到第 3 首；
- 一次短暂 `buffering` 自行恢复，没有形成持续故障；
- 用户中途解锁并调整音量，随后重新熄屏；该交互被保留为测试扰动；
- 电池温度保持在约 `32.0–32.2°C`；
- 最高 thermal zone 从 `47°C` 回落，最终稳定在约 `41–43°C`；
- 未发现音频服务崩溃、verity、EXT4 或 I/O 错误。

这是短时、有 USB 连接的功能/热稳定性样本，不替代固定曲目、固定网络、电流与环境温度受控的
长期功耗基准。

### 4. boot 持久化

临时启动和音频验收通过后，用户第二次独立明确确认只写 `boot`。写入前再次核对设备身份、解锁
状态、目标 boot 的两份构建哈希与 exact stock boot 回滚哈希。`fastboot flash boot` 的发送和写入
均返回 `OKAY`，总耗时约 `0.9s`。

随后执行正常重启，而非再次 `fastboot boot`。Android 报告 `sys.boot_completed=1`；system 继续
从只读 `/dev/block/dm-0` 挂载，dm-verity 正常启用，Leo Shell 仍是默认 HOME。用户再次确认 Leo
就绪页、Spotify 登录与短时耳机播放正常。此时 project boot 才被判定为持久启动通过。

`ro.boot.verifiedbootstate=orange` 与 bootloader 已解锁相符，不被解释为 dm-verity 失败。

## 当前有效状态

- 第一代 Leo Audio OS 的正式 project system 与 project boot 已持久运行；
- 原厂 MIUI framework、音频 HAL/DSP/ESS 依赖仍是底座；
- userdata 被保留，所以这不是 clean-flash 或第二代源码 ROM；
- Leo Shell 是默认 HOME，但 MIUI Launcher 未删除，保留可逆退路；
- Spotify、原厂外放、有线耳机与 HiFi 首轮验收通过；
- stock recovery 未改写，fastboot/recovery 救援路径仍保留。

## 尚未证明

- 尚未在第二台 `leo` 重复刷写；
- 尚未实际执行 boot/system 回滚恢复，也未实测 USB-OTG 恢复；
- 尚未完成多次冷启动、异常断电、低电量、长时待机与数小时播放；
- 尚未实现启动计数、失败自动回退、安全模式或签名更新；
- 尚未证明恢复出厂后的 HOME provisioning、Spotify/GMS 重新安装与登录流程；
- 尚未完成受控环境下的功耗、CPU residency、PCM offload 与音频分析仪对照。

因此本次裁决限定为：**单台参考机的首次受控写入与持久功能验收通过**，不是 1.0 发布裁决。
