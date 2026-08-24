# 01：Leo Audio OS 可利用资源地图

状态：`Phase 0 / resource discovery`

基线日期：`2026-08-24`

适用设备：Xiaomi Mi Note Pro，代号 `leo`

## 1. 结论

Leo Audio OS 已经具备启动工程所需的四类核心资源：

1. 一台完成实机验证的参考设备；
2. 与参考系统精确匹配的原厂格式 Fastboot ROM 和恢复材料；
3. Xiaomi 官方公开的 `leo` 内核基线，以及社区维护的设备树、Vendor 清单和
   Android 平台树；
4. 已验证的 Spotify、原厂音频配置、32/64 位 Audio HAL 与第一代改造工程。

因此，“从原厂系统提取音频兼容层，再集成到专用系统”是可以进入实施阶段的工程
路线。当前还不能直接构建正式固件：音频二进制依赖闭包、播放中的实时路由、可靠
Recovery、Linux构建环境和第二台破坏性测试设备尚未齐备。

## 2. 地图总览

```text
                           Leo Audio OS
                                 |
             +-------------------+-------------------+
             |                                       |
     MIUI 衍生原型线                           源码正式线
             |                                       |
  原厂 system/boot/audio                Android/MoKee 平台源码
  第一代实机结论与补丁                  Xiaomi 官方 leo 内核
  原厂签名的专有二进制                  leo + msm8994-common 设备树
             |                           用户自提 Vendor/Audio blobs
             +-------------------+-------------------+
                                 |
                   Player Shell / Maintenance UI
                                 |
                      实机测量、恢复与发布工程
```

## 3. 可信度分层

| 等级 | 含义 | 使用规则 |
| --- | --- | --- |
| A | 参考机实测、小米官方源码、精确原厂镜像 | 可以作为基线，但写入前仍核对哈希 |
| B | 社区设备树、Vendor树、Recovery树 | 可用于Bring-up，不能假定等同原厂实现 |
| C | 相邻设备或新版民间移植 | 只作为思路和补丁来源，必须逐项移植 |
| D | 论坛包、网盘镜像、无源码调参 | 不进入正式供应链 |

任何单一来源都不能证明系统可用。只有“源代码/镜像匹配 + 实时路径证据 + 重启测试 +
恢复测试”同时成立，才能晋级为 Leo Audio OS 的发布资源。

## 4. 参考设备：最高价值的运行证据

| 项目 | 已确认状态 | 对项目的价值 |
| --- | --- | --- |
| 设备 | Xiaomi Mi Note Pro / `leo` | 唯一黄金参考机 |
| 系统 | Android 7.0 / MIUI `V9.2.3.0.NXHCNEK` | 原厂音频ABI与行为基线 |
| Fingerprint | `Xiaomi/leo/leo:7.0/NRD90M/V9.2.3.0.NXHCNEK:user/release-keys` | 拒绝错版输入 |
| 内核 | `3.10.84-gfcc38b5-04628-gf2509a2` | 对照公开内核与实际boot |
| Root | Magisk 30.7，仅修改匹配的boot | 便于只读采集和原型验证 |
| 音频 | 耳机插入后触发HiFi；扬声器不触发 | 定义真实产品路径 |
| 性能 | A57 CPU4-7 上限1440 MHz；热保护保留 | 第一代保守功耗基线 |
| Spotify | `9.1.50.1906`，播放/切歌/下载已验收 | 应用兼容黄金版本 |

已经保存的只读证据包括 `getprop`、`uname`、AudioFlinger、AudioPolicy、Tinymix、
包状态、热区、音频配置和框架文件。U0/H0/H1/H0-after 对照已经确认 Spotify 由
44.1 kHz PCM16 经 deep-buffer 转为 48 kHz，HAL 选择 `hifi-headphones` 并打开
QUAT_MI2S MultiMedia1；暂停后约 3 秒完整关闭 PCM、mixer、MBHC VDDIO 和 QUAT 时钟。
详见 [`03-AUDIO-DEPENDENCY-CLOSURE.md`](03-AUDIO-DEPENDENCY-CLOSURE.md)。

另一个已确认缺口是 `/proc/config.gz` 在参考系统上为空文件，stock kernel 也没有
IKCONFIG。运行内核配置必须由 stock boot、公开 defconfig 和运行中 sysfs 三方重建。
已确认 stock boot 实际选中的 MSM8994 v2.1 MTP DTB 与官方源码的音频节点
语义一致，参考机硬件为 3.2。详见
[`05-STOCK-BOOT-DTB-AUDIT.md`](05-STOCK-BOOT-DTB-AUDIT.md)。

## 5. 原厂镜像与私有恢复材料

本机私有材料库已有原厂格式 Fastboot ROM：

```text
leo_images_V9.2.3.0.NXHCNEK_20171229.0000.00_7.0_cn_4ca14075f0.tgz
SHA-256 007d3d7d9a7e3e70684498070bab03ec145a73b1de44ed7299698cc4bf5ad94f
```

压缩包包含 `system.img`、`boot.img`、`recovery.img`、`NON-HLOS.bin`、
`persist.img`、Bootloader和其他固件。它解决三个问题：

- 为MIUI衍生构建器提供确定输入；
- 为专有音频文件建立完整提取来源；
- 为故障恢复提供已知原厂材料。

### 分区事实

ROM 内 `rawprogram0.xml` 给出的物理边界为：

| 分区 | 容量 |
| --- | ---: |
| boot | 64 MiB |
| recovery | 64 MiB |
| persist | 32 MiB |
| system | 1,703,936 KiB，约1.63 GiB |
| cache | 384 MiB |

这说明把 `system` 扩大到3 GiB的现代民间设备树不能直接用于原始分区表。项目禁止为
了容纳系统而盲目重分区。

`persist` 是设备级校准和持久数据边界。ROM 虽包含 `persist.img`，原厂刷机脚本并
不写入它；Leo Audio OS 同样把参考机当前 `persist` 视为不可覆盖资产。对于第一代
和第二代，默认都不触碰 `persist`、Bootloader、基带和信任区分区。

所有镜像、固件和提取文件只能进入 `resources/private/`，不能提交Git或发布。
公开的机器可读哈希清单见
[`resources/private-inputs.lock`](../resources/private-inputs.lock)。

## 6. 厂商公开内核：第二代的关键地基

Xiaomi 官方 [`MiCode/Xiaomi_Kernel_OpenSource`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource)
的 `libra-n-oss` 分支包含一条关键提交：

```text
f4cab50d74f8e55e0a0dbbf430d163f46c6fc3a1
Kernel changes for Xiaomi 4C / Xiaomi Note Pro / Xiaomi 4S
```

提交说明明确提到 `leo_user_defconfig`，并声明基于 Qualcomm
`LA.BF64.1.2.3-01110-8x94.0`。树内已经确认存在：

- `sound/soc/codecs/es9018.c`：ESS9018上电、静音、滤波、阻抗和THD补偿；
- `sound/soc/msm/msm8994.c`：QUAT MI2S、位宽、采样率和时钟；
- `arch/arm64/configs/leo_user_defconfig`：官方目标配置；
- `drivers/thermal/msm_thermal.c`：独立热限制和热插拔保护；
- `drivers/soc/qcom/msm_performance.c`：性能策略接口。

与当前锁定的社区内核树比较，ESS9018、`msm_thermal` 和 `msm_performance` 的Git
blob完全一致；`msm8994.c`和`leo_user_defconfig`不同。后两者将成为“官方基线 →
社区演进 → 参考机实际内核”三方差异审计的中心。

厂商公开内核并不等于当前 MIUI 内核的完整可复现源码。stock DTB 音频节点和
关键驱动符号已对上；最终仍需确定精确源码提交、编译器、defconfig 和关键函数
的二进制对等性。

## 7. 社区源码：可构建框架与兼容层

机器可读锁定清单见
[`resources/public-sources.lock`](../resources/public-sources.lock)。主要资源如下：

| 资源 | 等级 | 作用 | 当前判断 |
| --- | --- | --- | --- |
| `xiaomi-classic-dev/android_kernel_xiaomi_leo` | B | Android 10/社区演进内核 | 高价值，须与官方树做差异审计 |
| `android_device_xiaomi_leo` | B | 设备配置、Mixer、产品定义 | 可用于Bring-up |
| `android_device_xiaomi_msm8994-common` | B | Audio HAL、Wi-Fi、图形、SELinux等通用层 | 当前缺失的必要依赖，可公开获取 |
| `android_vendor_xiaomi_leo` | B | `leo`专有文件清单和构建规则 | 只作清单；二进制不可默认再分发 |
| `android_vendor_xiaomi_msm8994-common` | B | MSM8994通用专有依赖 | 必需，但必须改成用户本地提取 |
| `MoKee/android` `mkq-mr1` | B | 完整Android 10平台清单 | 可恢复平台源码，尚未试编译 |
| `TeamWin/android_device_xiaomi_leo` | B | Recovery分区、fstab、USB-OTG构建参考 | 可用于重建可临时启动的Recovery |

### 已知代码债务

Android 10 社区树仍含有：

- `androidboot.selinux=permissive`；
- `lpm_levels.sleep_disabled=1`；
- 旧版HIDL、shim和专有Blob兼容逻辑。

它可以帮助系统启动，但不符合 Leo Audio OS 正式版的安全和低功耗目标。Bring-up
阶段可以暂时继承，正式版必须逐项删除，并最终达到SELinux Enforcing和正常深度休眠。

较新的民间 Lineage 21 移植只能作为C级参考：其 `leo` 配置把system分区设为约3 GiB，
仍使用Permissive和旧内核兼容措施，而且没有形成与参考机相同可信度的完整Vendor
供应链。它不是首个刷入候选。

## 8. 第一代工程：不能丢失的实践资源

公开仓库
[`mi-note-pro-hifi-streamer`](https://github.com/leekaomin380/mi-note-pro-hifi-streamer)
当前锁定提交为 `8442113`。它提供：

- 数据、Spotify splits、音频配置和系统状态的备份方法；
- exact-build Magisk boot与A57频率策略；
- MIUI应用商店、安全中心和Launcher保护机制的实机逆向；
- 两次启动fail-closed保险和Recovery回滚脚本；
- 原厂音频文件哈希与可复现源码库；
- 播放、切歌、下载、Wi-Fi和有线HiFi验收记录。

Leo Audio OS 不复制该仓库。它把第一代项目当作：

1. 黄金行为基线；
2. 只读采集工具来源；
3. 失败机制数据库；
4. MIUI衍生原型线的上游。

## 9. 硬件与器件资料

| 资料 | 权威性 | 用途 |
| --- | --- | --- |
| [Xiaomi Mi Note Pro产品页](https://www.mi.com/minote/pro) | 厂商 | 确认DAC、双时钟、供电、精密电阻和PPS电容架构 |
| [ESS SABRE DAC资料](https://www.esstech.com/products-overview/digital-to-analog-converters/sabre-audiophile-dacs/) | 芯片厂商 | 确定ES9018K2M能力边界和测量术语 |
| [Texas Instruments OPA1612 datasheet](https://www.ti.com/lit/ds/symlink/opa1612.pdf) | 芯片厂商 | 确定噪声、失真、输出和供电约束 |
| [Soomal量产机音频测试](https://old.soomal.cc/doc/10100005841.htm) | 独立测量 | 提供历史量产机对照，不替代本项目实测 |

器件数据表描述的是芯片能力，不等于整机表现。最终结论必须来自参考机在标准负载下
的实测，而不是把DAC或运放的实验室指标直接当成手机输出指标。

## 10. 音频兼容层资源

| 层 | 已有资源 | 未完成工作 |
| --- | --- | --- |
| 应用 | 已验证Spotify splits及签名版本 | 记录账号登录对GMS/WebView的真实依赖 |
| Android音频 | AudioFlinger/Policy快照 | 播放中的输出线程、flags、采样率和欠载 |
| Audio HAL | 原厂32/64位`audio.primary.msm8994.so` | 293个ELF递归依赖已解析；继续确认`dlopen`候选和符号版本 |
| 配置 | Policy、Platform、Mixer、Effects、init脚本 | 建立文件到运行路径的因果映射 |
| 校准 | Forte ACDB文件，社区Vendor清单 | 对照原厂system与设备实际加载文件 |
| DSP | 原厂ROM和当前固件分区 | 确认加载来源；默认不升级、不重刷 |
| 内核 | Xiaomi官方+社区ESS/MSM8994源码 | stock DTB 音频节点已对上官方源码；继续重建精确构建配置 |
| 模拟端 | ESS9018K2M、OPA1612、耳机阻抗读数 | 音频分析仪下的频响、THD+N、噪声与串扰基线 |

已经保存的核心文件哈希证明第一代改造没有替换音频HAL和配置。第二代应当先把这组
文件扩展为完整依赖闭包，再讨论移植。

## 11. Spotify与Google资源边界

Spotify[当前官方支持表](https://support.spotify.com/us/article/supported-devices-for-spotify/)
仍把Android 7列为最低版本，但平台支持会变化。项目已有一个实机
可用的 `9.1.50.1906` split APK集合和SHA-256；它只用于设备所有者本地恢复，不进入
GitHub或发行固件。

[Google官方GMS说明](https://www.android.com/intl/en_uk/gms/)明确指出Google Mobile
Services不是AOSP组成部分，只能通过Google许可提供。开源项目不能把GMS打进公开
镜像。Leo Audio OS将提供三个构建档位：

1. `aosp-only`：无GMS，用于底层Bring-up和音频验证；
2. `user-gms`：用户本地提供与目标Android版本匹配的原始GMS输入；
3. `spotify-ready`：用户本地同时提供Spotify splits，构建器只校验、不重新签名。

根据[Spotify使用条款](https://www.spotify.com/legal/end-user-agreement/)，项目不会
修改、重签或重新分发Spotify。自己的Shell、维护应用、OTA和平台组件使用项目
release keys；这些密钥必须离线生成和保管，绝不进入Git。

## 12. Recovery、更新与回滚资源

已有资源：

- Bootloader已解锁；
- stock boot和stock recovery已有精确哈希；
- TeamWin存在公开的`leo` Recovery设备源码；
- 物理分区表和Fastboot原厂恢复材料已保存；
- 第一代项目已有bootloop救援和两次启动保险经验。

仍缺：

- 一份由本项目构建、可`fastboot boot`临时启动的Recovery；
- USB-OTG、ADB、system/boot备份和还原的实机验收；
- 项目OTA release keys；
- 连续启动失败计数与自动进入Recovery机制；
- 第二台可承受失败的`leo`测试机。

`leo`不是A/B设备。第一阶段的“自动回滚”是进入已知Recovery并恢复签名的良好版本，
不是现代双槽无缝回滚。项目不通过高风险重分区来伪造A/B。

Android的[发布签名](https://source.android.com/docs/core/ota/sign_builds)和
[OTA工具](https://source.android.com/docs/core/ota/tools)均允许设备实现者生成自己的
release keys与更新包；它们不会赋予Xiaomi或Google身份，也不需要Xiaomi私钥。

## 13. 构建与测量基础设施

### 当前本机

基线时主机为8 GiB RAM、约19 GiB可用磁盘。它足以维护文档、分析单个镜像和开发
Shell，但不适合安全完成Android 10完整源码检出与编译，也缺少多份镜像的工作余量。

源码线需要：

- x86_64 Linux构建环境；
- 独立高速SSD；
- 足够空间容纳平台源码、两个输出树、ccache和恢复镜像；
- 更高内存或可接受的远程构建主机。

Android官方[当前构建环境要求](https://source.android.com/docs/setup/start/requirements)
对现代AOSP给出的上限型参考是400 GB空闲空间和64 GB RAM。Leo的Android 10分支
可能低于这个数字，但在首次干净构建前不能凭经验缩减预算。

### 当前测量能力缺口

| 资源 | 状态 | 获取方式 |
| --- | --- | --- |
| 第二台`leo` | 缺失 | 购买同型号测试机；先核对屏幕、耳机口和Bootloader |
| USB功率计/电池电流基线 | 未登记 | 购置或借用，固定测试线材 |
| 音频分析仪 | 缺失 | 借用专业设备，或建立高质量ADC的阶段性方案 |
| 32Ω/80Ω/300Ω标准负载 | 缺失 | 购置低误差无感负载 |
| 温度采集 | 部分可用 | 先使用内核热区，后加外部热电偶/红外测量 |

## 14. 条件是否能够取得

| 条件 | 可取得性 | 判断 |
| --- | --- | --- |
| Xiaomi官方`leo`内核源码 | 已取得 | 可作为内核权威基线 |
| Android/MoKee平台源码 | 可取得 | 需要Linux构建环境和大容量存储 |
| `leo`与MSM8994设备树 | 可取得 | 社区来源，需审计 |
| 原厂音频HAL/配置/校准 | 已取得核心部分 | 仅限用户从自有设备/ROM提取 |
| 完整音频依赖闭包 | 可取得 | 需要解包system并做ELF/服务依赖分析 |
| Qualcomm DSP源代码 | 通常不可取得 | 保留原厂签名固件和二进制接口 |
| Xiaomi平台/Bootloader私钥 | 不可取得，也不需要 | 使用项目自己的平台和OTA密钥 |
| GMS公开分发许可 | 普通开源项目不可取得 | 用户本地提供，仓库不分发 |
| Spotify APK再分发权 | 不可假定取得 | 只接受用户本地原始安装包 |
| 专用Shell和维护模式 | 完全可自行实现 | 本项目原创代码 |
| 真正A/B无缝回滚 | 原始硬件不具备 | 使用Recovery型回滚，不危险重分区 |

## 15. 下一步

资源地图之后的第一项工程任务固定为：

> 从锁定的原厂 `system.img` 建立音频兼容层的完整依赖闭包。

该任务只读，不接触手机分区。输出应包括：

1. 原厂system镜像提取和文件系统元数据；
2. 所有音频ELF的32/64位依赖图；
3. init服务、属性、SELinux、设备节点、ACDB和DSP映射；
4. “必须保留 / 条件保留 / 可删除”三类机器清单；
5. 与参考机实时播放路径的差异列表；
6. 可公开的分析脚本，以及不含专有文件的验证报告。

在这份闭包完成前，不构建、更不刷入第二代system镜像。
