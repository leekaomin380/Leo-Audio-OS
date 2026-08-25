# Leo Audio OS

> One device. One purpose. Music.

Leo Audio OS 是一个面向 Xiaomi Mi Note Pro（代号 `leo`）的长期开放工程：
把这台搭载 ESS9018K2M、OPA1612 和 Qualcomm MSM8994 的旧手机，重新构建为
一台克制、稳定、可恢复的专用有线网络音频播放器。

项目不是要给旧手机再安装一套“功能更多”的 ROM，而是从最小 Android 基础出发，
只保留 Spotify 播放、原厂 HiFi 音频链、Wi-Fi、存储、更新和维护所必需的能力。
普通使用状态下，设备只表现为播放器；只有进入隐藏维护模式时，才显露 Android
底层。

## 当前状态

项目已经完成 **Phase 1：音频依赖闭包 v0.2**，冻结了 **Phase 2：播放器 Shell 原型
v0.2.7 基线**，以及 **Phase 3 Gate 2：无修改 system 重建与 development-unverified 容器**。
Gate 2 已完成 ext4 文件级语义重建和 sparse 回环；没有刷写系统镜像。

- 还没有可供刷入的 Leo Audio OS 固件；
- 当前实机仍运行已验证的 MIUI 9 HiFi 播放器方案；
- 当前 MIUI 上的 Leo HOME Shell v0.2.7 已完成可逆安装验证；
- 不应根据本仓库当前内容执行分区写入；
- 原厂音频运行路径、HAL/ELF、stock boot/DTB、首批内核配置和 SELinux 有效授权
  闭包已经建立；最终最小保留集仍待功能与故障测试证明。

已经完成的 MIUI、Root、精简、框架补丁与回滚实践继续在
[`mi-note-pro-hifi-streamer`](https://github.com/leekaomin380/mi-note-pro-hifi-streamer)
维护。本仓库专门承载第二代专用系统。

## 产品目标

- 保留原厂 ESS9018、Qualcomm DSP、Audio HAL、ACDB 校准和 I²S 路径；
- 从系统构建阶段排除电话、短信、相机、主题、商店等非播放器能力；
- 开机直接进入播放器界面，不提供普通桌面和应用抽屉；
- 提供受控的隐藏维护模式，用于 Wi-Fi、VPN、更新、诊断和恢复；
- 正式版使用只读系统、项目 release keys、SELinux Enforcing；
- ADB 默认关闭，正式播放器版本不依赖 Magisk 或常驻 Root；
- Spotify、GMS 和 Xiaomi 专有文件由设备所有者合法提供，项目不重新分发；
- 每个发布版本都必须具有确定的恢复路径和实机验收记录。

## 文档

- [01：可利用资源地图](docs/01-RESOURCE-MAP.md)
- [02：工程学习与协作方式](docs/02-ENGINEERING-LEARNING-MODE.md)
- [03：原厂音频依赖闭包](docs/03-AUDIO-DEPENDENCY-CLOSURE.md)
- [04：官方内核音频路径](docs/04-OFFICIAL-KERNEL-AUDIO-PATH.md)
- [05：Stock Boot 与 DTB 审计](docs/05-STOCK-BOOT-DTB-AUDIT.md)
- [06：原厂内核配置重建](docs/06-KERNEL-CONFIG-RECONSTRUCTION.md)
- [07：原厂 SELinux 音频闭包](docs/07-STOCK-SELINUX-AUDIO-CLOSURE.md)
- [08：音频组件分类与 Phase 1 收口](docs/08-AUDIO-COMPONENT-CLASSIFICATION-V0.2.md)
- [09：Phase 2 播放器 Shell 原型路书](docs/09-PHASE-2-PLAYER-SHELL-RUNBOOK.md)
- [10：Phase 3 MIUI 原型固件构建器路书](docs/10-PHASE-3-MIUI-BUILDER-RUNBOOK.md)
- [11：Phase 3 Gate 1 ext4 元数据审计契约](docs/11-PHASE-3-GATE1-EXT4-AUDIT-CONTRACT.md)
- [12：Phase 3 Gate 2 无修改重建契约](docs/12-PHASE-3-GATE2-UNMODIFIED-REBUILD-CONTRACT.md)
- [Phase 2 基线冻结记录](docs/reviews/2026-08-24-phase2-baseline-freeze.md)
- [Phase 3 Gate 2 冻结记录](docs/reviews/2026-08-25-phase3-gate2-freeze.md)
- [Phase 3 Gate 0 评审](docs/reviews/2026-08-24-phase3-gate0.md)
- [产品愿景与命名](docs/VISION.md)
- [初始系统架构](docs/ARCHITECTURE.md)
- [长期路线图](docs/ROADMAP.md)

## 仓库结构

```text
apps/       专用播放器 Shell 与维护界面
build/      用户自备原厂 ROM 的可复现构建系统
docs/       愿景、架构、研究、验证与发布文档
resources/  公开源码清单、哈希和私有材料边界
scripts/    采集、分析、构建、校验与恢复工具
```

## 安全与发布边界

仓库可以发布源码、补丁、文件清单、哈希和构建方法，但不发布：

- Xiaomi ROM、Bootloader、DSP/基带固件和提取的专有库；
- Google Mobile Services、Spotify APK 或其他第三方安装包；
- 修改后的设备镜像、账号数据、设备序列号或用户文件；
- 未经实机验证或没有明确回滚路径的刷写指令。

代码与原创文档按 MIT License 发布。第三方组件仍受其各自许可约束。
