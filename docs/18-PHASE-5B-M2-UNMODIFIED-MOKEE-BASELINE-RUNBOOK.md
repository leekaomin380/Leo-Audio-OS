# 18：Phase 5B M2 原版 MoKee 实机基准路书

> 状态：原版候选的离线重建门已通过；设备尚未连接，第二份回滚介质尚未在线，当前不授权 wipe、
> recovery 安装或任何分区写入。公开 manifest 永久保持 `device_write_authorized=false`，临场授权
> 只对一次明确动作有效。

## 1. 本轮唯一目标

在一台已解锁的 Xiaomi Mi Note Pro（`leo`）上，短期运行**未经音频覆盖、未经删包、未经 GApps
或 Magisk 注入**的 MoKee Android 10 原版基准，判断社区 bring-up 的真实启动、网络和音频能力。

本轮不是 Leo Audio OS 第二代发布，也不修改 MoKee 内容。只有 M2 运行证据完整，M3 才能设计
最小 HiFi Controller；只有音频等价，M4 才能开始源码白名单删减。

## 2. 锁定输入和离线候选

| 对象 | 大小 | SHA-256 | 裁决 |
| --- | ---: | --- | --- |
| 原版 ZIP | 647,032,071 | `e1d32441513d49108802cc426b0891f7c3be577f2cb41d4030b4fe2ddf614390` | ZIP/MD5/身份通过 |
| system raw | 1,744,830,464 | `7238ee916246f6ac4564d7386639494323bae01b67eb8bed6b0168b2d47689c3` | 两次独立重建一致，`e2fsck -f -n` 通过 |
| system sparse | 1,564,010,920 | `695eba5e3e1b1469f3fe2feeb299934f94d6b9e53e82d13717df324e20bffe7b` | 双构建一致，回展开与 raw 一致 |
| boot | 23,928,832 | `9470dd6a01120480289c17d0da161e73b2eb6361ece3ea72041b07da088934af` | 与 ZIP 成员一致 |

私有 system 候选位于
`resources/private/phase5b-mokee/m2-candidate-v0.1/sparse-pair/system-a.img`；boot 位于
`resources/private/phase5b-mokee/extracted/boot.img`。公开绑定见
`manifests/mokee-m2-baseline-candidate-v0.1.json`。

MoKee OTA 的 updater 只显式写 `system` 和 `boot`。其 `backuptool` 仅在现有 system 的
`ro.mk.version=MK100*` 时工作；当前 MIUI 不满足前置条件。M2 采用等价的离线 raw→sparse 候选和
受控 fastboot 路径，不运行 addon 继承，从而得到干净基准，也不依赖来源不明的自定义 recovery。

## 3. 为什么不能直接复用网上的 `leo` TWRP

Team Win 官方下载页中的旧 `leo` 条目对应另一种旧设备，并不能仅凭相同代号用于 Xiaomi Mi Note
Pro。当前项目没有锁定、审计和实测过适用于本机的第三方 recovery。因此 M2 不下载、不写入、不
临时启动未知 recovery；stock recovery 保持原样作为清除数据和救援入口。

## 4. 写入前硬门

以下各项必须全部通过：

1. 手机在 Android、fastboot 两种模式下都唯一枚举为同一台 `leo`；
2. bootloader 仍处于 unlocked，电量、线缆和 USB 枚举稳定；
3. `system=1,744,830,464` 字节，boot 与 userdata 几何符合已冻结基线；
4. 当前 firmware/trustzone 满足 `TZ.BF.3.0.R1-00226`；
5. stock recovery 可进入、可导航、可返回 fastboot，且测试时不选择 wipe；
6. 本机 Phase 4 黄金 system/boot 和 stock system/boot/recovery 全量哈希通过；
7. 上述回滚材料至少另有一份独立物理介质在线并完成实际读回；
8. 如需保留当前 Spotify 安装版本，先只读导出 base 与全部 split APK；不尝试迁移登录态；
9. 用户已知悉 Android 7→10 需要清除 userdata，照片、下载、应用数据和登录状态都会消失；
10. 在看到确切候选、哈希、分区和回滚后，用户当场确认第一次破坏性动作。

任何一项不满足都停止。历史验证记录不替代本次实时读取。

## 5. 设备预检和证据保存

在 Android 状态先保存只读证据：产品代号、build、boot 完成、电池、当前数据占用、TrustZone
版本、当前 boot/system 块设备、Spotify APK 路径和 recovery 入口。不得记录账号令牌或复制
userdata 登录数据库。

进入 fastboot 后读取产品、解锁状态、电池电压、boot/system/userdata 分区尺寸和 USB 稳定性。
所有输出进入 Git 忽略的本次私有目录；发现身份漂移、`getvar` 异常或线缆抖动立即返回系统。

## 6. 分阶段写入顺序

### 6.1 第一次临场确认：wipe 与 system

第一次确认必须把两件不可逆影响一起说明：清除 userdata，以及用
`695eba…fe7b` 覆盖 `system`。确认后：

1. 使用已实测的 stock recovery 执行清除数据；
2. 返回 fastboot，重新读取身份和分区尺寸；
3. 只向 `system` 写入锁定 sparse；
4. 写入回执必须为 `OKAY`，失败时不得继续写 boot；
5. 不正常重启，先临时启动锁定的 MoKee boot。

此时 `recovery`、`persist`、`modem`、`tz`、`aboot`、Bootloader 等均不得写入。

### 6.2 临时 boot 验收

临时 boot 只证明这一份 system/boot 配对能否运行，不把它描述为持久安装。最低验收：

- 到达系统、完成基础设置，显示/触摸/实体键正常；
- ADB 可用且设备身份仍为 `leo`；
- Wi-Fi、DNS、HTTPS 和时间同步正常；
- 外放与有线耳机均有声，插拔路由不崩溃；
- 收集 AudioFlinger、AudioPolicy、HAL maps、mixer、PCM、kernel、ACDB、设备节点和 AVC denial；
- 记录 ESS probe、QUAT MI2S 控件、采样格式、温度与 crash；
- 安装锁定 Spotify APK 后验证播放、切歌、封面、下载和息屏；若 APK/登录尚未准备好，明确记为
  M2 未闭合，不能用本地播放器代替 Spotify 全部验收；
- 能通过 ADB 或实体按键返回 fastboot。

不得仅凭“耳机有声”宣布 `HIFI_ACTIVE`。

### 6.3 第二次临场确认：持久 boot

只有临时 boot 的启动、网络、基本音频和返回 fastboot 全部通过，才展示 boot 的完整 SHA-256，
单独询问是否写 `boot`。获得确认后只写同一份 `9470…34af` boot，正常重启并重新执行冷启动、
Wi-Fi、外放、耳机、ADB 与 recovery 入口检查。

## 7. 回滚顺序

首选回滚到已经实机验收的 Phase 4 黄金配对：

| 对象 | SHA-256 |
| --- | --- |
| Phase 4 system sparse | `afa12b23e4570f96cc5e4ee70cf754779c75cf834a9d61f481f08d1a96e21eb1` |
| Phase 4 project boot | `dfca241d75d494e0d85502d1368a3475f0e2576dd69b28274fcf4532a2779685` |

第二回滚层为 exact stock system/boot/recovery。回滚仍只写确有必要的 `system`/`boot`；不运行
`flash_all`，不碰 firmware、persist 或 Bootloader。由于 M2 已清除 userdata，回滚能恢复可启动
系统，但不能恢复被清除的应用数据和登录状态。

## 8. 当前停止点

2026-08-27 离线候选门通过，但当前主机未发现 ADB/fastboot 设备；外置回滚盘未挂载，文件服务器
也暂不可达。因此 `device_write_ready=false`。下一步只是在手机接入后完成第 4–5 节，不得越过
第 6.1 节的临场确认。
