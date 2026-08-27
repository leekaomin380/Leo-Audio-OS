# 16：Phase 5B MoKee 兼容性桥梁全局路书

> 状态：M0/M1 已于 2026-08-27 通过静态审计；当前停在 M2 设备写入门。本文不授权向设备写入
> 任何分区，也不授权删除当前 MIUI 黄金参照、回滚材料或私有证据。

## 1. 目标与裁决

Phase 5B 使用 Xiaomi Mi Note Pro（`leo`）的 MoKee Android 10 社区系统作为
**MIUI 衍生原型与 Leo Audio OS 源码系统之间的兼容性桥梁**。它不是最终产品，也不是把
MIUI 音频目录整体复制进新 ROM 的“厨房式换包”。本阶段要依次解决：

1. 证明锁定的原版 MoKee 可以在 `leo` 上稳定启动并具备基本硬件能力；
2. 以当前 MIUI 黄金参照为基准，逐层恢复或证明 ESS9018K2M 有线 HiFi 路径；
3. 在音频等价之后，以源码白名单产品而非运行期冻结的方式移除无关组件。

顺序固定为：**原版基准 → 音频等价 → 最小化 → 发布工程**。音频移植与大规模删减不得在
同一候选中首次发生。

## 2. 硬边界

- 当前参考机继续作为声音、路由、功耗和恢复黄金参照；
- Gate M0–M1 不需要连接手机；
- 未经当场明确确认，不刷分区、不进 recovery 安装、不 wipe；
- 不把 Xiaomi、Google、Spotify 或其他不可再分发二进制提交到公开 Git；
- 专有文件只从设备所有者合法持有的 ROM 或参考机本地提取；
- 第一轮不拉取完整平台源码，不在空间不足时展开完整 system；
- 不以“耳机有声音”作为 ESS HiFi 路径成立的证据；
- 正式候选必须 SELinux Enforcing、系统只读、ADB 默认关闭且不依赖 Magisk。

## 3. 当前资源约束

2026-08-26 检查显示：Mac 数据卷约剩 11 GiB；项目约 42 GiB，其中私有资源约 40 GiB；
没有可用外置数据卷，小米笔记本也尚未成为文件服务器。因此第一轮：

- 只下载一个锁定的 `leo` MoKee ROM；
- ZIP 保存在 Git 忽略的私有输入目录；
- 优先读取 ZIP 目录并按分析目标选择性提取；
- 下载前至少保留 8 GiB，后续操作不得使可用空间低于 6 GiB；
- 预计展开量超过 3 GiB 时停止，等待外置存储或文件服务器；
- 大型临时文件登记路径、大小、可再生性和清理条件。

单盘文件服务器未来只能作为工作资产库，不能替代第二份独立备份。

## 4. 智能等级约定

| 等级 | 用途 | 使用原则 |
| --- | --- | --- |
| **SH（Sol High）** | 架构、启动链、ABI、音频、SELinux、删减边界、刷写与回滚 | 用于错误代价高或需要跨层推理的门禁；结论立即固化 |
| **TM（Terra Medium）** | 下载、哈希、解包、机械差异、脚本、文档同步和既定测试 | 只执行已有契约；遇到未定义差异上提 SH |

五小时 usage 窗口下，每个执行块必须有独立输入、输出、验证和停止条件；最后预留至少
20–30 分钟校验、记录、提交和交接。长下载、哈希或构建由机器运行，智能额度用于契约和裁决。

## 5. 模块、智能等级与交付物

| 模块 | 主要工作 | 主等级 | 交付物 | 完成门 |
| --- | --- | --- | --- | --- |
| A. 规划与证据模型 | 固定阶段、候选命名、风险和回滚 | SH | 本路书、路线图 | 每一动作归入唯一 Gate |
| B. 输入溯源 | 锁定 ROM、发布信息、大小、哈希和许可边界 | TM；冲突用 SH | 输入锁、来源记录 | 发布方证据与本地文件闭环 |
| C. 存储与下载 | 空间预检、断点下载、原始哈希和冻结 | TM | 私有 ZIP、SHA-256、日志 | 容器完整且空间过门 |
| D. ROM 容器审计 | ZIP、镜像、分区、签名、属性、安装脚本 | TM；异常用 SH | 结构与身份报告 | 确认为 `leo` 且尺寸兼容 |
| E. 启动链审计 | boot、kernel、DTB、ramdisk、fstab、verity、recovery | SH | 启动链差异报告 | 无未知分区写入，回滚明确 |
| F. MoKee 音频基线 | HAL、AudioPolicy、mixer、ACDB、ADSP、init、权限 | SH | MoKee 音频闭包 v0.1 | 每个部件有来源和依赖 |
| G. MIUI→MoKee 差量 | 判定保留、替代、shim 或禁止移植 | SH | 音频差量矩阵 | 不再采用整体覆盖 |
| H. 原版实机基准 | 启动、Wi-Fi、外放、耳机、Spotify、温度、恢复 | SH 设计；TM 采集 | MoKee 验收记录 | 临写确认且回滚闭合 |
| I. 音频等价候选 | kernel→HAL→配置/ACDB→init/SELinux 单层迭代 | SH | 独立候选和可逆补丁 | ESS/QUAT MI2S 有运行证据 |
| J. 组件最小化 | `leo_audio.mk` 白名单和分批删减 | SH 划界；TM 实现 | 包图、删除批次 | 每批冷启动和音频回归通过 |
| K. 构建与重打包 | 可复现脚本、签名、SBOM、哈希 | TM；发布审计用 SH | 候选与 manifest | 双构建一致，专有输入未入 Git |
| L. 发布与演练 | Enforcing、只读、回滚、启动保护、第二设备 | SH | 发布契约和报告 | 故障演练闭合后才发布 |

## 6. Gate M0：可信输入

来源优先级：MoKee 发布基础设施或发布方公告 → 发布方公布的哈希 → 已锁定源码仓库 →
社区镜像。搜索结果、转载网盘和相同文件名不构成可信来源。

锁定记录至少包括文件名、`leo` 代号、版本、构建日期、发布类型、URL、获取时间、HTTP 元数据、
大小、发布方哈希、本地 SHA-256、ZIP 测试、内部 build identity 和对应源码提交。

下载使用可恢复临时名；完成后计算 SHA-256、测试 ZIP，再原子改名进入 `verified`。身份不符的
文件隔离并登记，不覆盖可信输入。

**M0 通过条件**：来源与文件闭环、身份为 `leo`、容器完整、空间门槛满足。

## 7. Gate M1：只读静态审计

M1 不制造可刷候选，按需提取：

1. OTA 脚本、metadata 和 build properties；
2. boot/recovery 与 fstab；
3. system/vendor 音频路径；
4. 系统应用、服务、权限和共享库；
5. SELinux policy、file contexts 与 init rc；
6. kernel/DTB 中 ESS9018、I2C、QUAT MI2S、clock 和 pinctrl 证据。

输出三张矩阵：`mokee-rom-inventory`、`mokee-vs-miui-audio-delta` 和
`mokee-component-disposition`。

**M1 通过条件**：能解释原版 MoKee 如何启动、如何出声、已有何种 ESS 支持，以及首个实机
候选为何不会触碰未知分区。

2026-08-27 裁决：上述条件已由 `manifests/mokee-rom-inventory-v0.1.tsv`、
`manifests/mokee-audio-delta-v0.1.tsv`、`manifests/mokee-component-disposition-v0.1.tsv` 和
`docs/reviews/2026-08-27-phase5b-m0-m1-static-audit.md` 闭合。M1 通过不等于授权 M2；当前必须
停在设备写入门。

## 8. Gate M2：原版实机基准

M1 通过、回滚材料双份可读、救援入口实测并获临场确认之前停止。第一台候选必须是未经音频覆盖、
未经删包的锁定 MoKee，以分离社区 bring-up 与本项目改造。

验收包括冷启动、显示/触摸/Wi-Fi、外放、耳机、Spotify 播放/下载/息屏、温度、deep sleep、
crash/denial 和 recovery/fastboot。音频采集 AudioFlinger、AudioPolicy、mixer、kernel、属性与
设备节点证据。

## 9. Gate M3：音频等价

候选依次独立推进：

1. 社区 kernel/DTB 与 stock ESS 路径对齐；
2. 先评估 MoKee HAL，只有缺失能力时才引入 stock 32 位 HAL 或最小 shim；
3. 差量引入 I2S mixer/platform 配置；
4. 对齐 Forte ACDB、ACDB loader 和 ADSP；
5. 对齐 init、属性、设备权限和 SELinux；
6. 在 HAL 内实现 Leo HiFi Controller：控制 ESS/QUAT 状态，并以读回证据进入 `HIFI_ACTIVE`；
7. 先以结构化 `dumpsys`/日志验证状态机，再发布只读状态服务给 Leo Home 与维护页；
8. 固定曲目进行 MIUI/MoKee 路由、稳定性、温度和主观对照。

禁止把 Android 7 的 `audioserver` 或 framework 库整体覆盖到 Android 10。任何 HAL 先通过 ELF、
依赖、符号、位数、命名空间和 SELinux 审计。

状态机、证据门、权限边界与界面要求由
[`17：Leo HiFi 控制与状态显示契约`](17-LEO-AUDIO-STATE-CONTRACT.md) 固定。普通 UI 不得直接
写 mixer、sysfs、DAC I2C 或 property；耳机有声不是 `HIFI_ACTIVE` 的充分证据。

## 10. Gate M4：源码白名单最小化

音频等价后建立 `leo_audio` 产品，不继承完整电话产品和 MoKee full-phone 包。初始白名单仅覆盖
启动、显示、触摸、Wi-Fi、存储、有线音频、Spotify 运行条件、Leo Home、维护、更新与恢复。

删除分批进行：用户表面应用 → 电话/短信/蜂窝 → 相机/录音 → 可选硬件 → MoKee 附加服务 →
framework/权限/共享库。每批进行包图闭包、双构建、冷启动、Wi-Fi、Spotify、有线 HiFi、息屏和
恢复回归。删除数量不是进度指标；后台唤醒、温度、攻击面和可恢复性才是。

## 11. Gate M5：发布候选

必须为 `user` 构建、SELinux Enforcing、系统只读、无 Magisk/常驻 root、ADB 默认关闭；普通状态
只显示 Leo Home；ESS HiFi、稳定性和功耗不低于黄金参照；回滚、启动失败保护、签名、SBOM、
哈希和验收报告齐全；至少在第二台设备完成破坏性故障演练后才面向他人发布。

## 12. 五小时窗口执行节奏

每个窗口最多一个 SH 裁决模块和一个 TM 实现模块：

1. 0–30 分钟：重读路书、核对输入和工作树；
2. 30–180 分钟：完成唯一主模块；
3. 180–240 分钟：验证、负向测试和差异复核；
4. 240–270 分钟：文档、manifest、工作日志和提交；
5. 最后 30 分钟：不得开启新方向，只收口和交接。

跨窗口下载或计算必须保存任务状态和可验证输出；不得仅凭终端仍在运行宣布进度。恢复时先检查
真实文件、进程、哈希、Git 状态和剩余空间。

## 13. 最近三个执行块

### 执行块 1：路书与输入锁（SH → TM）

- 冻结本文并更新路线图；
- 检索发布方 ROM、公告和哈希；
- 生成输入锁；
- 只在空间门通过时下载一个 ROM。

### 执行块 2：ROM 身份与结构（TM）

- ZIP 完整性和清单；
- updater、分区、fingerprint 和目标代号；
- 按需提取 boot、配置和音频文件；
- 产出 M0/M1 初始报告。

### 执行块 3：音频差量裁决（SH）

- 连接 Phase 1 黄金音频闭包；
- 判定已实现、可复用、需 shim、需 stock 提取和禁止覆盖的组件；
- 定义原版实机候选与回滚前置条件；
- 到达设备写入门后停止并请求确认。

## 14. 立即停止条件

- 来源无法验证或发布哈希冲突；
- 可用空间将低于 6 GiB；
- 代号、分区尺寸、bootloader 前提与 `leo` 不符；
- 必须删除黄金/回滚资产才能继续；
- 安装脚本会写入未审计分区；
- 音频方案要求整体替换 framework 或关闭 SELinux；
- 设备身份、救援路径、线缆或供电不稳定；
- usage 窗口不足以完成验证和交接。
