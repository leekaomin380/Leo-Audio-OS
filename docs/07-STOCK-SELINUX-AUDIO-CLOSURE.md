# 07：原厂 SELinux 音频闭包 v0.1

## 结论

原厂 `leo` 的编译策略已经被成功解析，并与当前参考机的进程域、文件标签和打开文件
句柄完成首轮交叉验证。我们现在能从 `init` 的可执行文件转换一路追踪到音频服务、
设备节点、数据目录、DSP/RFS 支撑服务和应用 Binder 入口。

这建立的是“原厂有效授权闭包 v0.1”，不是最终最小权限集，也不是“删去其余规则必然
安全”的证明。任何规则的必要性还必须经耳机播放、冷启动、DSP 重启、离线下载和恢复
测试证实。

分析期间手机保持 SELinux Enforcing；未写入策略、未创建 permissive 域、未重启或刷机。
私有策略和真机采集仍只保存在被 Git 忽略的 `resources/private/`。

机器可读结论见
[`manifests/selinux-audio-closure-v0.1.tsv`](../manifests/selinux-audio-closure-v0.1.tsv)。

## 1. 我们实际在验证什么

Android 启动一个受 SELinux 约束的音频服务，至少要同时满足四层条件：

```text
init service 声明
  → 可执行文件具有 *_exec 标签
  → type_transition 进入独立进程域
  → 该域获得对对象类型的 allow
```

例如：

```text
init
  → /system/bin/audioserver [audioserver_exec]
  → u:r:audioserver:s0
  → audio_device / audio_data_file / audioserver_service / audio_prop
```

`ueventd.rc` 中的用户、用户组和模式解决传统 Unix DAC 权限；SELinux `allow` 是另一道
独立门。两者缺一都可能出现“文件存在、权限看似正确，但服务仍打不开设备”的现象。

## 2. 输入和工具边界

| 输入 | SHA-256 |
|---|---|
| stock `sepolicy` | `0b6df2c113f1b5b5dc4a91d81c385d8b837395b44dfdfe9a572692adbfe5247d` |
| `service_contexts` | `c47d68ab5abefd94af641fbe5373e598de8a2cd2858391957c76b51293e61b65` |
| `file_contexts.bin` | `b9164c070a6d9152acd8b5c2635a38ee42726f2a4c173e6cf81dc97dce7113ff` |
| `property_contexts` | `92838f65f428406c63b392220f501e58105192fc0b18a2f38b0670e2a5d01683` |
| `seapp_contexts` | `703ca099ce69af820f84146e7645c70ab6b00f961300327c346cdf712c18b66e` |

解析在锁定 Debian bookworm 基础镜像的本地容器中完成，使用 SETools 4.4.1。专有输入
以只读方式挂载，不进入镜像。`file_contexts.bin` 使用字符串提取做静态定位，再以真机
`ls -Z` 验证关键标签，避免把旧 Android 的编译格式误当成现代主机格式直接解释。

## 3. 策略总体事实

原厂策略版本为 30，启用 MLS，共有 1143 个类型、30 个属性、13,801 条 `allow`、
185 条 `allowxperm` 和 365 条 `type_transition`。结果还包括：

- 0 个布尔变量和 0 个条件表达式；
- 0 个 permissive 域；
- 未知 class 的处理方式为 deny；
- 编译策略中显示 0 条 `neverallow`。

最后一点不表示原厂源码没有安全约束。`neverallow` 主要在构建期校验，发布的二进制
策略不能用来恢复全部源码断言及宏展开来源。

## 4. 启动域转换与实时身份

| 服务 | 转换 | 实机进程域 | 状态 |
|---|---|---|---|
| `audioserver` | `init + audioserver_exec → audioserver` | `u:r:audioserver:s0` | running |
| `audiod` | `init + audiod_exec → audiod` | `u:r:audiod:s0` | running |
| `adsprpcd` | `init + adsprpcd_exec → adsprpcd` | `u:r:adsprpcd:s0` | running |
| `rfs_access` | `init + rfs_access_exec → rfs_access` | `u:r:rfs_access:s0` | running |

四个可执行文件在真机上的 `*_exec` 标签与策略转换完全一致。这排除了“服务实际借用
init 或 shell 域运行”的可能。

## 5. 已闭合的主要授权路径

### 5.1 应用到 audioserver

`audio` 服务标为 `audio_service`；这个类型同时属于 `system_server_service` 和
`app_api_service`，因此由 `system_server` 注册、应用查找。`media.audio_flinger`、
`media.audio_policy` 和 `media.sound_trigger_hw` 标为 `audioserver_service`。策略允许
`audioserver` 注册并查找这些服务，允许 `untrusted_app` 查找它们，并通过
`appdomain → binderservicedomain` 的继承规则完成 Binder call/transfer。

这说明 Spotify 不需要直接访问声卡设备；它经 Binder/AudioTrack 把流交给
`audioserver`，设备访问留在受控服务域中。

### 5.2 audioserver 到内核和数据

策略明确允许 `audioserver`：

- 对 `audio_device:chr_file` 执行 read/write/ioctl/open；
- 管理 `audio_data_file` 目录、文件和 socket；
- 读取 `system_file` 类型的原厂音频配置；
- 读取并 ioctl `ion_device`；
- 设置 `audio_prop`；
- 与 `audiod` 传递 Binder 对象。

空闲状态下，`audioserver` 已实际打开：

- `/dev/snd/controlC0`、`/dev/snd/hwC0D1000`；
- `/dev/msm_audio_cal`、`/dev/msm_rtac`；
- `/dev/ion`；
- `/system/etc/aanc_tuning_mixer.txt`。

真机还确认 `/dev/snd/pcmC0D0p`、`/dev/msm_hweffects` 与上述节点同属
`audio_device`。PCM 的活动使用已由前一轮 H1 Spotify 播放状态证实。

### 5.3 DSP 与远端文件支撑

- `adsprpcd` 可读取并 ioctl `qdsp_device`，且实机持有 `/dev/adsprpc-smd`；
- `rfs_access` 可读写/ioctl `uio_device`，且实机持有 `/dev/uio1`、`uio2`、`uio3`；
- `rfs_access` 对 `firmware_file`、`rfs_file`、`rfs_shared_hlos_file` 和
  `rfs_system_file` 分别具有相应读取或管理权限；
- 实机标签确认 `/firmware/image/adsp.mdt`、`/persist/rfs`、`/persist/hlos_rfs`
  和 `/system/rfs` 落入这些类型。

这组证据证明服务、对象类型和当前打开路径相互吻合，但尚不能单凭空闲文件句柄断言
每个服务都是 ESS 播放的不可替代组件。

## 6. 权限宽度审计

| 域 | 有效授权规则 | 直接授权规则 | 属性继承 |
|---|---:|---:|---|
| `audioserver` | 175（173 allow + 2 allowxperm） | 66 allow | `binderservicedomain`, `domain` |
| `audiod` | 150（148 allow + 2 allowxperm） | 22 allow | `domain_deprecated`, `domain` |
| `adsprpcd` | 148（146 allow + 2 allowxperm） | 20 allow | `domain_deprecated`, `domain` |
| `rfs_access` | 165（163 allow + 2 allowxperm） | 37 allow | `domain_deprecated`, `domain` |

有效规则包含属性规则展开后的结果，直接规则只统计明确以该域为 source 的规则。因此
不能把规则行数当成风险分数，但差值清楚说明：后三个厂商服务的大部分授权来自 Android
7 的宽泛 `domain_deprecated` 属性。

第二代系统不应原样复制整个 stock 二进制 policy。正确做法是保留独立域和已证实接口，
在可启动系统上用 AVC、功能测试和故障注入逐项建立最小规则；只有证据闭合后才能移除
`domain_deprecated` 继承。正式系统仍保持 Enforcing，不以 permissive 掩盖缺口。

## 7. DTS 与 avtimer 的异常边界

stock init 仍声明 `dts_configurator` 和 `dtseagleservice`，策略也保留对应域；但参考机和
官方 system 提取树都没有 `/system/bin/dts_configurator` 与
`/system/bin/dts_eagle_service`，服务未运行，`/data/misc/audio_pp` 也不存在。

这表明它们是高度可信的遗留声明候选，而非当前 HiFi 路径已证实依赖。与此同时，
`/data/misc/dts` 实际存在并由 `mediaserver`/`system_app` 规则覆盖，所以不能把“两个
daemon 缺失”误推为“所有 DTS 数据和效果都无关”。删除仍须经过构建、重启和效果回归。

`/dev/avtimer` 在 file contexts 中有独立 `avtimer_device` 类型，但本次真机未枚举到该
节点；stock 策略只显示 `init` 和 `radio` 对其有实质读取权限，没有 `audioserver` 的
直接访问。因此它列为条件项，不纳入已证实的 ESS 播放核心路径。

## 8. 对第二代系统的直接设计约束

1. 为 `audioserver`、`audiod`、`adsprpcd` 和 `rfs_access` 重建独立域和明确转换；
2. 同时重建 `file_contexts`、`service_contexts`、`property_contexts` 与 ueventd DAC，
   不能只复制 `allow`；
3. 第一版兼容构建保留原厂节点和数据标签，再用真实播放与冷启动证据逐项收紧；
4. 若闭源 HAL 允许，可把音频配置从通用 `system_file` 拆成更窄的专用类型；
5. 不复制原厂整个 policy，不把 `domain_deprecated` 当永久兼容方案；
6. 不因某服务“正在运行”就宣称必需，也不因空闲时“未打开”就删除它。

## 9. 仍未闭合的项目

- 播放 H1 状态下四个域的瞬态文件句柄和 AVC 对照；
- `audiod`、`adsprpcd`、`rfs_access` 分别对冷启动、DSP 恢复和持续播放的必要性；
- 原厂 `.te` 源文件、宏和 build-time `neverallow` 的精确来源；
- `miui_audio_device`、Dolby/Dirac、DTS 数据路径的功能归属和可删除边界；
- 在第二代源码系统中，以专用类型替代通用 `system_file` 的闭源兼容性。

下一项低风险验证应是在耳机播放 H1 时再次运行只读文件句柄采集，与本次空闲快照做差。
它不会改变设备状态，但需要用户主动插入耳机并保持 Spotify 播放。
