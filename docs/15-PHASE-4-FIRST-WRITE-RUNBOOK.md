# 15：Phase 4 首次受控写入路书

## 1. 当前裁决

本路书定义未来动作顺序，不授权当前设备写入。development pair 使用一次性测试密钥，任何
verifier 通过都不能替代用户在破坏性动作前的明确确认。

截至 2026-08-26，正式 `leo-phase4-release-set-v1` 已完成双密钥、双介质重挂载、system/boot/
sparse 双构建、原厂 system sparse→raw 回滚闭环，以及 8 项内容故障与 7 项 tuple 混配故障测试。
正式 manifest 仍固定 `device_write_authorized=false`、`allowed_partitions=[]`；离线技术门通过不改变
第 3–5 节的设备预检、救援路径实测和临写确认要求。

## 2. 写入前必须全部闭合

- 正式 `leo-verity-v1` 与 `leo-boot-v1` 已完成分域密钥仪式；
- 两个独立离线加密副本均完成断开、重连和恢复读取测试；
- 正式 system raw/sparse 与 project boot 各双构建逐字节一致；
- release-set verifier 与全部负向测试通过，manifest 绑定所有 hash；
- exact stock boot、stock recovery、stock system 与已知可启动 development boot 均可读；
- 手机用户数据已有独立备份，设备电量、USB 线和主机空间满足要求；
- 用户本人在场。

任一条件缺失即停止，不以 probe key、旧 Magisk footer 或单份 U 盘备份替代。

## 3. 设备只读预检

用户将手机进入 fastboot 后，只读取：设备枚举、产品代号、解锁状态、电池状态、分区尺寸和
当前 slot/boot 状态。所有输出保存到一次性审计目录，并与 `leo`/V9.2.3.0 基线比较。身份不唯一、
USB 抖动、boot/system 尺寸不符或 rollback hash 缺失时立即停止。

## 4. 救援路径实测

先临时启动 exact stock recovery，不写 recovery 分区。用户确认屏幕、按键/触摸、ADB 或
sideload、返回 fastboot 均正常，且不得选择清除数据。无法稳定返回 fastboot 时停止。

## 5. 第一次系统试验

在这里暂停并再次向用户展示即将写入的唯一目标 `system`、sparse SHA-256、预计耗时和回滚
命令。只有取得当场明确确认后，才写入 manifest 中的正式 project system；不得触碰 userdata、
persist、modem、tz、aboot、recovery 或其他分区。

写完后不直接正常重启，也不持久化 project boot。先临时启动 manifest 中同一配对的 project
boot，依次验证：dm-verity、首次启动、显示、触摸、Leo Shell、Wi-Fi、Spotify 登录/播放/下载、
耳机插拔、HiFi 路由、温度和返回 fastboot/recovery。

## 6. boot 持久化是第二次独立决定

只有临时 boot 连续通过且日志无 verity/I/O/SELinux 启动故障，才单独询问是否把完全相同 hash
的 project boot 写入 boot 分区。用户未确认时，boot 保持不动。

## 7. 回滚

任一步异常，优先保持 fastboot/recovery 可用：临时启动已知可用 development boot，或进入
exact stock recovery；按 manifest 恢复 exact stock system 与 stock boot。禁止使用会连带清除
userdata 或改写 bootloader/基带的全量 `flash_all`。回滚后重新读取 hash 和启动状态，不以出现
MI 标志作为恢复成功证据。
