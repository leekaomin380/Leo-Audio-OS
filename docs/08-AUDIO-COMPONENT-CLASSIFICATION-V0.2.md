# 08：音频组件分类与 Phase 1 收口 v0.2

## 结论

Phase 1 已经达到“可以设计兼容构建输入”的收口条件。我们不再只有一批名称中带
`audio` 的文件，而是有一套把静态依赖、动态映射、真实播放、init、属性、权限、
SELinux、DSP、内核和关断行为连接起来的分层清单。

机器清单：

- [`audio-component-classification-v0.2.tsv`](../manifests/audio-component-classification-v0.2.tsv)：
  51 个逻辑组件的处置结论；
- [`audio-property-contract-v0.1.tsv`](../manifests/audio-property-contract-v0.1.tsv)：
  19 组属性的消费者、当前作用和第二代策略；
- [`audio-compatibility-v0.1.tsv`](../manifests/audio-compatibility-v0.1.tsv)：
  首批精确文件哈希；
- [`selinux-audio-closure-v0.1.tsv`](../manifests/selinux-audio-closure-v0.1.tsv)：
  域、对象和授权路径。

这里的“收口”是完成证据分类和构建设计边界，不是授权在当前 MIUI 上删除文件。
真正的最小集合只能在可回滚的测试构建中，通过故意移除与完整回归证明。

## 1. 分类结果

| 分类 | 数量 | 含义 |
|---|---:|---|
| `must-retain` | 19 | 已被真实播放或不可替代的启动/硬件链直接证明 |
| `support-retain` | 9 | 支撑关系明确，但尚未隔离其因果必要性；首个兼容构建保留 |
| `conditional-retain` | 14 | 只服务于可选输出、效果、录音或交付方式 |
| `removal-candidate` | 7 | 当前缺失、失效或与专用目标不符，但仍须经构建回归才移除 |
| `out-of-scope` | 2 | 产品定义明确排除的功能，不应进入第二代正常模式 |

分类和第二代动作是两个维度。例如 Dirac 是 `conditional-retain`，但第一版动作仍是
`preserve-first-build`，因为它已经在 Spotify H1 中活动；只有完成等响度 A/B 测量后，
才能决定继续保留还是从效果配置中移除。

## 2. 真正不可动的主链

当前高置信度主链为：

```text
Spotify AudioTrack
  → audioserver / AudioFlinger / AudioPolicy
  → 32-bit audio.primary.msm8994.so
  → audio_platform_info_i2s.xml + mixer_paths_i2s.xml
  → libtinyalsa / libtinycompress / libaudioroute
  → ACDB loader family + Forte headset/common calibration
  → audio_device + /dev/snd/pcmC0D0p
  → ADSP firmware / supporting RPC and RFS contracts
  → MSM8994 QUAT MI2S + ES9018 driver and DTB
  → ESS9018K2M / analog stage / headphones
```

H1 中 PCM 打开，H0-after 中同一 PCM 关闭，且两阶段没有四个音频域的 AVC denial。
这使 HAL、I²S 配置、PCM 节点、SELinux 和内核路由形成了双向状态证据，而不是只靠文件名
或日志字符串猜测。

## 3. 32/64 位边界的新判断

当前 `audioserver` 是 32 位进程，真实映射 32 位 primary HAL。U0、H0、H1、H0-after
四个状态中，它映射的 104 个 system ELF 集合完全相同；状态变化发生在 PCM、mixer、
effect active state 和时钟，而不是通过播放时临时装入一批新库。

这带来两个重要结论：

1. “库被映射”只能证明加载，不能证明某个效果在处理音频；Dirac 的 active 证据来自
   AudioFlinger effect chain，而不只是 `/proc/PID/maps`；
2. 64 位 primary HAL 虽然存在，但没有被当前音频服务加载，其可选插件集合也不完整。
   第二代不能仅因为目标平台支持 arm64，就贸然切换成 64 位 audioserver。

第一版源码系统应先复现已验证的 32 位音频服务/HAL ABI；只有补齐并验证 64 位插件、
校准和效果链后，才讨论 64 位迁移。

## 4. 动态加载候选复核

修正 ELF 分析器对 `system/lib/...` 和 `system/vendor/lib/...` 字符串路径的规范化后，
结果仍为 293 个 ELF、2328 条全部解析成功的 `DT_NEEDED` 边；15 条 seed 字符串候选中，
8 条可定位，7 条因相应架构文件不存在而保持未定位。私有 v0.2 TSV 的 SHA-256 为：

```text
62fe7eb9f78598ea06da57d3146965ccbeef385ee61c9932ff9cec89076d52e3
```

32 位 HAL 的候选可分为：

- `libacdbloader.so`、`libadm.so`：已在 `audioserver` 中实际映射；
- `libqcompostprocbundle.so`、`libqcomvisualizer.so`：路径已修正，文件存在且实际映射；
- `libdrc.so`、`libsurround_3mic_proc.so`：文件存在，但四个状态均未映射，字符串和符号
  指向环绕/多麦录音而非 Spotify 输出；
- `libcsd-client.so`：两种位数都不存在，相关字符串明确属于语音通话 CSD 接口。

64 位 HAL 的 DRC、3-mic、ADM 和显式 32 位 soundfx 路径无法形成完整同架构闭包，进一步
支持“64 位 HAL 是未使用 counterpart，不是当前已验证路径”的判断。

## 5. 属性契约

属性不能作为散落在 `build.prop` 中的神秘开关处理。v0.1 属性清单把它们分为：

- 必需播放：`persist.audio.hifi`、`persist.audio.hifi.volume`；
- 当前路径：`audio.deep_buffer.media`、`audio_hal.period_size`；
- 条件功能：`audio.offload.*`，当前 Spotify 流没有使用 offload；
- 产品排除：Fluence、voice path 和 3-mic/voice 相关能力；
- 遗留候选：Dolby 标记、`qcom.audio.init`、`sys.audio.init`。

其中 Dolby 是典型的“声明不等于实现”：属性为 true，`audio_effects.conf` 也声明
`libswdap.so`/`libhwdap.so`，但二进制不存在，运行时没有 Dolby 映射。它可以进入候选
删除表，但仍应通过配置解析、开机和 Spotify 回归，而不是直接从当前系统强删。

## 6. 效果、录音与输出功能

### Dirac

Dirac 两个 32 位库在 `audioserver` 中加载，H1 effect chain 明确 active。它不是“看到
文件名就保留”，也不是“Spotify 本身需要”；它是当前原厂声音的一部分。第二代第一版
保留，之后以等响度频响、失真、温度和主观双盲对照决定。

### 其他 soundfx

通用 bundle、reverb、visualizer、downmix、loudness 及 Qualcomm post-processing 库
被统一加载，但测试曲目的 effect chain 没有证明它们活动。它们属于条件保留，未来应
先生成精简 `audio_effects.conf`，再以单变量方式测试，而不是只删 `.so`。

### 录音、电话和多输出

DRC、3-mic surround、CSD voice、A2DP、USB audio、remote submix 和 sound trigger 都
不在当前有线 Spotify 输出链中。第二代产品可以不提供它们，但首个兼容构建仍保留其中
可能影响框架启动的部分；产品功能决策与系统依赖移除必须分两步完成。

## 7. 七个候选删除项

当前候选包括：

1. Dolby 的失效库声明和属性；
2. 两个缺失的 DTS daemon 声明；
3. 不存在的 `/data/misc/audio_pp` 合约；
4. 缺失的 CSD client 语音插件引用；
5. dedicated player 不需要的 remote submix；
6. 当前不存在且未授予 audioserver 实质访问的 `/dev/avtimer` 路径；
7. 未发现 init 调用者的旧 Qualcomm Bluetooth UCM 初始化脚本/完成属性。

“候选删除”的精确定义是：允许在未来的构建配方中做一次可回滚的省略实验。它绝不等于
允许在当前 MIUI 的 `/system` 上直接删除。

## 8. 第一代和第二代如何使用这份清单

第一代 MIUI 构建器：

- 完整保留 `must-retain` 与 `support-retain`；
- 默认保留 `conditional-retain`，只对单个功能做 A/B；
- 候选删除也必须通过镜像构建和重启验证；
- 不改变现有 32 位音频 ABI、SELinux Enforcing 或恢复路径。

第二代源码系统：

- `extract-stock` 只用于 HAL、校准、DSP 等不可重建专有输入；
- Android framework、tinyalsa、内核和 init 尽量从锁定源码重建；
- SELinux、file/service/property contexts 和 ueventd 权限由项目生成；
- 正常产品模式不包含 out-of-scope 应用和功能入口；
- 每个删减动作都要保留 failure mode 与 next gate，不能凭“看起来无关”决定。

## 9. Phase 1 之后

Phase 1 的静态/动态分类已经收口。以下问题继续保留，但它们转入后续阶段，不再阻塞
播放器 Shell 原型：

- Dirac 等响度 A/B 与音频分析仪测量；
- 44.1 → 48 kHz 重采样和 offload 可行性；
- 长时间播放的温度、电流、CPU 驻留和网络成本；
- `audiod`、`adsprpcd`、`rfs_access` 的故障注入必要性；
- 64 位音频服务迁移是否值得。

下一项工程工作应进入 Phase 2：先在 MIUI 上实现完全可逆的专用播放器 Shell，验证
“唯一 HOME + Spotify + 隐藏维护模式”的产品行为，不替换 system。
