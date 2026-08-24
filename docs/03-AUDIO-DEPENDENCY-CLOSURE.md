# 03：原厂音频依赖闭包

## 状态

本文记录 Phase 1 的可验证进展。当前只完成了官方镜像静态基线和实机空闲状态采集，
尚不能宣称完整依赖闭包已经建立，也不能据此删除任何系统组件。

基线设备：Xiaomi Mi Note Pro（`leo`），Android 7.0，MIUI
`V9.2.3.0.NXHCNEK`，安全补丁 `2017-12-01`。设备已解锁并通过 Magisk 提供 Root，
SELinux 保持 Enforcing。

私有原始证据位于被 Git 忽略的 `resources/private/`，公开仓库只记录方法、哈希、
结构与结论，不包含 Xiaomi 二进制、设备标识或用户数据。

## 为什么先建立闭包

我们需要回答的不是“哪些文件名看起来像音频”，而是：

> 从 Spotify 创建播放流开始，到 ESS9018K2M 输出模拟信号为止，哪些程序、动态库、
> 配置、校准、服务、权限、固件和内核接口缺一不可？

只有回答这个问题，第一代 MIUI 精简才有安全边界，第二代系统才有可移植的输入清单。

## 已确认事实

### 1. 实机和官方 ROM 是同一基线

官方 fastboot ROM 压缩包 SHA-256：

```text
007d3d7d9a7e3e70684498070bab03ec145a73b1de44ed7299698cc4bf5ad94f
```

其 `system.img` 是 Android sparse image，展开后为 ext4。实机以下核心文件的哈希与
官方镜像登记值完全一致：

| 角色 | 路径 | SHA-256 |
|---|---|---|
| 32 位 Audio HAL | `/system/lib/hw/audio.primary.msm8994.so` | `0b8e3f6290532499ac19c881fc8cbe36c8212f3dd83fe4aa3527ff6265fe038a` |
| 64 位 Audio HAL | `/system/lib64/hw/audio.primary.msm8994.so` | `4b3fb296226c77219dc44695512f7743d708315cec5c756a88ee6e9077385de1` |
| 音频策略 | `/system/etc/audio_policy.conf` | `cfedbe8d84022e883baadfd517cbbaa1f6f51c18c45dd9feb6e66a28e4fd3b66` |
| 普通平台配置 | `/system/etc/audio_platform_info.xml` | `6fdf7373ed35892c925451b5f85ff8593403bd5efc5a902eb10ebda4237e1917` |
| I²S 平台配置 | `/system/etc/audio_platform_info_i2s.xml` | `10487b79a4aefe9d68e5bca171e6d1ada406a962efedd05b064065b107922e60` |
| 普通 mixer 路由 | `/system/etc/mixer_paths.xml` | `13db0e6e5bd04e02c36a6b84e815f492d730e107866b91e605ee653364084bb4` |
| I²S mixer 路由 | `/system/etc/mixer_paths_i2s.xml` | `ed2f1d41fbbd11bb788da8a1e8c9ce36c8940e8da913f51ee7e7feaff70b81dd` |

这证明当前运行设备的音频核心没有被此前的系统精简替换，但不证明其余依赖均未改变。

### 2. HAL 明确包含专用 HiFi 逻辑

32 位和 64 位 `audio.primary.msm8994.so` 都包含以下行为：

- 识别独立的 HiFi 耳机输出设备；
- 在普通配置与 I²S 配置之间选择；
- 读取并设置 `persist.audio.hifi`、HiFi 音量等属性；
- 设置 `QUAT_MI2S` 的位宽和采样率；
- 针对 HiFi 与 offload 的组合选择不同后端行为；
- 加载 ACDB 校准并处理耳机、扬声器等不同 sound device。

因此 HiFi 并非一个单独 APK 提供的“音效开关”，而是编译进 Qualcomm/Xiaomi Audio
HAL 的硬件路径。复制一个界面应用无法复制这项能力。

### 3. HAL 的直接 ELF 依赖并不等于完整依赖

两种位数的 HAL 都直接依赖：

```text
liblog.so
libcutils.so
libtinyalsa.so
libtinycompress.so
libaudioroute.so
libdl.so
libexpat.so
libc++.so
libc.so
libm.so
```

但 HAL 还可能在运行时加载或调用 `libacdbloader.so`、`libcsd-client.so`、`libdrc.so`、
部分 Qualcomm soundfx 库等组件。更新后的 U0 进程映射已经确认 32 位 HAL、
`libacdbloader.so` 与 `libtinycompress.so` 实际加载进 `audioserver`；其余候选库仍需
在 H1 中确认。ELF 的 `DT_NEEDED` 只能给出第一圈依赖，字符串、`dlopen`、配置引用、
init 服务和实机调用轨迹还要继续补齐。

### 4. DSP、校准和服务已经进入依赖图

实机确认存在 Qualcomm ADSP 固件集合，`adsp.mdt` 与多个 `adsp.bXX` 分段共同构成
可加载映像，不能只保留其中一个文件。

系统还包含 Forte 平台的 ACDB 校准集合，包括通用、耳机、扬声器、蓝牙和 HDMI
校准。`init` 会建立由 `audio`/`media` 用户组控制的校准数据目录。

当前运行的相关服务至少包括：

- `audioserver`：承载 Android 音频服务和 HAL；
- `audiod`：Qualcomm 厂商音频守护进程；
- `adsprpcd`：用户空间与 DSP 的 RPC 通道；
- `rfs_access`：为远端子系统访问所需文件提供支持；
- `media`、`mediacodec`、`mediaextractor` 与 `mediadrm`。

这里的“至少”很重要：服务正在运行不等于我们已经证明它在 Spotify HiFi 播放中必需。

### 5. 内核暴露了对应硬件路径

ALSA 声卡注册为 `msm8994-tomtom-mtp-snd-card`。PCM 和 mixer 控件中存在
`QUAT_MI2S` 播放路径、24 位位宽、采样率以及耳机相关控制。内核日志也显示
Quaternary MI2S 的启动、时钟与关闭过程。

空闲采集时，相关播放 mixer 处于关闭状态；这符合“没有正在播放的耳机流”，但还需
用受控的耳机插入和 Spotify 播放对照来证明具体哪些控件发生变化。

U0 中所有枚举到的 PCM `hw_params` 都为 `closed`。这比只看 mixer 更接近硬件事实：
当前没有仍然打开的 PCM 数据流。

## 当前依赖图

```text
Spotify
  → Android AudioTrack / Media framework
  → AudioFlinger + AudioPolicy
  → audio.primary.msm8994.so
      → libtinyalsa / libtinycompress / libaudioroute
      → libacdbloader + Forte ACDB calibration
      → mixer_paths_i2s.xml + audio_platform_info_i2s.xml
  → audiod / adsprpcd / ADSP firmware
  → ALSA msm8994-tomtom sound card
  → QUAT_MI2S
  → ESS9018K2M → OPA1612 → headphones
```

运行时对照已经确认 Spotify 经 mixer/deep-buffer 进入 QUAT_MI2S。官方内核源码进一步
确认了 ES9018 的 I2C 地址、五路 regulator、双晶振、reset/mute/switch/OPA GPIO、
codec-master 时钟关系和上下电顺序。完整逐行说明见
[`04-OFFICIAL-KERNEL-AUDIO-PATH.md`](04-OFFICIAL-KERNEL-AUDIO-PATH.md)。

stock boot 后续审计已确认参考机使用 MSM8994 v2.1 MTP DTB，该 DTB 的音频
节点与官方源码语义一致；参考机硬件版本为 3.2，不走 2.2 特殊供电分支。
ramdisk 内的 ADSP 启动、`audiod`、`adsprpcd`、`rfs_access`、数据目录和设备权限也已
进入静态闭包。详见 [`05-STOCK-BOOT-DTB-AUDIT.md`](05-STOCK-BOOT-DTB-AUDIT.md)。

## U0/H0/H1 运行时对照

已按以下状态完成首轮对照：

1. **U0**：未插耳机、没有播放；
2. **H0**：插入耳机、没有播放；
3. **H1**：插入耳机、Spotify 正常播放；
4. **H0-after**：暂停 Spotify，保持耳机插入并等待超过 5 秒。

| 观察项 | U0 | H0 | H1 | H0-after |
|---|---|---|---|---|
| Android 输出设备 | Speaker | Wired Headphones | Wired Headphones | Wired Headphones |
| 耳机阻抗检测 | 无读数 | 有原始读数，类型 2 | 保持 | 保持 |
| Spotify track | 无 | 无 | 44.1 kHz / PCM16 / stereo | 无 |
| AudioFlinger 输出 | Standby | Standby | MIXER + DEEP_BUFFER，48 kHz / PCM16 | Standby |
| HAL sound device | 无活动路由 | 无活动路由 | `hifi-headphones` | 无活动路由 |
| ALSA PCM | 全部 closed | 全部 closed | card 0 / PCM 0，48 kHz / S16_LE | 全部 closed |
| QUAT_MI2S mixer | Off | Off | MultiMedia1 On | Off |
| QUAT_MI2S 后端配置 | S24_LE / 48 kHz | S24_LE / 48 kHz | S24_LE / 48 kHz | S24_LE / 48 kHz |
| QUAT_MI2S 时钟 | 关闭 | 关闭 | 启动并保持 | 关闭 |

### 已回答的问题

- `WiredAccessoryManager` 接收内核耳机开关事件，Android AudioPolicy 增加有线耳机设备；
- “HiFi 属性为 true”只是允许条件，耳机插入本身不会打开 PCM、DAC 路由或 I²S 时钟；
- Spotify client PID 对应的 AudioTrack 为 44.1 kHz、16-bit、双声道；
- Spotify 当前使用 MultiMedia1 的 deep-buffer mixer 路径，不是 compressed offload；
- AudioFlinger/HAL 将流转换为 48 kHz、16-bit，再通过配置为 48 kHz、24-bit 的
  QUAT_MI2S 后端发送；24-bit 总线容器不会增加 16-bit 音源的信息量；
- HAL 明确选择 `hifi-headphones`，并打开 `QUAT_MI2S_RX Audio Mixer MultiMedia1`；
- 播放暂停后约 3 秒进入 standby，PCM、mixer、MBHC 供电和 Quaternary MI2S 时钟均关闭。

因此这次实验确认了真实 HiFi 路由，也确认播放后的关断没有卡住。此前观察到的播放发热
不能简单归因于“暂停后 DAC 一直上电”。

### 新发现的优化候选

1. **重采样**：Spotify 44.1 kHz 被固定的 48 kHz HAL 输出重采样；
2. **DiracSound**：AudioFlinger 中存在活动的插入式 Dirac effect；
3. **无 compressed offload**：策略声明支持该输出，但本次 Spotify 流没有使用；
4. **后台负担**：播放期间仍有 MIUI、Google 和 Spotify UI/网络活动，需要以后单独测量；
5. **日志异常**：HiFi 启动时出现 device 34 缺少 ACDB ID，停止时出现 sound-device
   引用计数已经为 0。实际播放和关断均正常，但要结合 HAL 源码判断它们是预期旁路还是
   潜在缺陷。

这些目前只是“值得做独立 A/B 测试的候选”，不是立即修改系统的理由。尤其不能为了
追求 44.1 kHz 或 offload，在没有音质、稳定性、温度和回滚证据时改写 HAL。

## ELF 递归闭包 v0.1

`scripts/analyze-audio-elf-deps.py` 已从 7 个明确入口和四组运行时进程映射出发，递归
分析 293 个 ELF，得到 2328 条全部成功解析的 `DT_NEEDED` 边。另有 6 个可定位、9 个
未定位的字符串候选；字符串只说明二进制包含一个可能的 `dlopen`/插件名，不代表调用
发生，也不算链接缺失。

第一版机器可校验输入清单位于
[`manifests/audio-compatibility-v0.1.tsv`](../manifests/audio-compatibility-v0.1.tsv)，17 个
文件已在原厂提取树中逐项通过 SHA-256。它是兼容性证据清单，不是最终可删除边界。

### 下一步仍要回答

- DiracSound 是否改变频响、功耗或稳定性，能否安全关闭；
- 44.1 → 48 kHz 重采样发生在何处，能否在不破坏 HiFi 路由的情况下避免；
- Spotify/Android 7/该 HAL 的组合是否可能使用 compressed offload；
- stock kernel 的精确源码提交、构建配置和工具链能否达到可重现；
- 编译 SELinux policy 中音频服务、设备节点和数据文件的完整 allow 闭包；
- 两条异常日志在内核/HAL 源码中的精确触发条件；
- 长时间播放的 CPU 驻留、温度、电流和网络活动分别占多少成本。

采集还包括 `audioserver`、`audiod`、`adsprpcd` 与 Spotify 的进程映射，用来证明
运行时实际加载了哪些动态库；同时读取所有已注册 PCM 的 `hw_params`，避免把 mixer
中的目标配置误认为已经落到硬件上的真实格式。

AudioFlinger 的 standby delay 为 3 秒，实测关断时序与之吻合。后续从 H1 回到 H0
仍应等待至少 5 秒再采集，避免把正常延迟误判为硬件常开。Spotify 的音量标准化、EQ
和测试曲目也应保持固定并记录；改变其中一项时，只改变这一个变量。

## 尚未完成

- `dlopen` 组件的运行时确认；
- init 服务与设备权限骨架已建立；属性触发和 SELinux allow 规则仍未完整映射；
- 内核驱动、设备树节点与用户空间 sound device 的一一对应；
- 最小保留集和任何可删除结论。
