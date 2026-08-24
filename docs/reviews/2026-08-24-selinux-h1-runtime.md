# SELinux H1 播放状态复核

## 结论

2026-08-24 在参考机插入耳机并持续播放 Spotify 时完成 H1 只读采集。播放路径成立，
四个音频相关域没有产生 SELinux denial。与同次启动中的空闲快照相比，唯一新增的
设备文件句柄是：

```text
u:r:audioserver:s0 → /dev/snd/pcmC0D0p [audio_device]
```

这把 stock policy 中 `audioserver → audio_device:chr_file` 的授权，从静态规则和空闲
控制节点证据推进到真实 PCM 播放数据路径。

## 采集边界

- 设备：`leo`，SELinux Enforcing；
- 状态：有线耳机、`persist.audio.hifi=true`、Spotify 持续播放；
- 操作：只读 ADB/Root 采集，没有清日志、改策略、切 permissive、重启或刷写；
- 私有证据：`resources/private/selinux-runtime/20260824-1806-H1/`；
- 完整音频状态：`resources/private/runtime-states/20260824-180630-H1-selinux/`。

两个证据集合的 `SHA256SUMS` 文件哈希分别为：

```text
cb20b507d68c21b9222eb2d2391431801758424849be4a5fc0b87f5ab536c285
7637a30088c492062235d01c82e22321e9275f7c62695a8c40584415107edd06
```

原始文件、进程映射和日志不进入公开 Git。

## H1 状态真实性

本次不是“耳机插着但播放器已经 standby”的假阳性：

- Spotify client track：44.1 kHz、PCM16、双声道，active；
- AudioFlinger deep-buffer 输出：48 kHz、PCM16、双声道，`Standby: no`；
- 输出设备：`WIRED_HEADPHONE`；
- ALSA card 0 / PCM 0：`RW_INTERLEAVED`、S16_LE、双声道、48 kHz；
- `QUAT_MI2S_RX Audio Mixer MultiMedia1 = On`；
- QUAT MI2S 后端：S24_LE、48 kHz；
- HAL 再次选择 `hifi-headphones`，DiracSound 仍作为 insert effect 存在。

## 文件句柄对照

比较时先去掉时间、文件描述符编号和重复项，只比较“进程域实际指向的目标”。结果：

| 域 | 空闲状态已有 | H1 新增 | H1 移除 |
|---|---|---|---|
| `audioserver` | control、hwdep、校准、RTAC、ION、Binder 等 | `/dev/snd/pcmC0D0p` | 无 |
| `audiod` | 一个长期 socket | 无 | 无 |
| `adsprpcd` | `/dev/adsprpc-smd` | 无 | 无 |
| `rfs_access` | `/dev/uio1`、`uio2`、`uio3` 与长期 socket | 无 | 无 |

因此，PCM 是播放相对空闲状态最清楚的新增内核对象。后三个服务没有新增句柄并不表示
它们与播放无关：它们可能通过启动时已建立的长期 FD、共享内存、ioctl 或 Binder 完成
支撑，普通 FD 快照无法观察每次调用。

## AVC 审计

保留的内核日志中，以下 source context 的 `avc: denied` 数量为 0：

```text
audioserver
audiod
adsprpcd
rfs_access
```

日志里确实存在 `shell` 域读取音频标签文件时的 denial；这些来自我们的只读检查命令，
source context 是 `u:r:shell:s0`，不是播放服务失败，不能混入音频闭包判断。

## 判断与下一步

本次成功播放且没有音频域 denial，说明 stock 有效策略覆盖了已观察到的 H1 路径。
它仍不能证明现有权限已经最小化，也不能证明 `audiod`、`adsprpcd` 或 `rfs_access`
可以删除。

后续收紧顺序应为：

1. 第二代兼容构建先保留四个域和当前对象标签；
2. 收集冷启动、长播放、暂停恢复和 DSP subsystem restart 的 AVC/功能结果；
3. 用专用测试机逐个缩小 `domain_deprecated` 继承；
4. 每次只改一组权限，并同时验证启动、Spotify、离线播放、耳机插拔和恢复。

在有第二台测试机和可启动回滚镜像前，不在当前参考机上停用这些基础服务做破坏性试验。
