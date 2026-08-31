# 长期路线图

> **状态** 2026-08-31 08:31 · 复选框计数 **43/73** · 轮值架构师 Claude（接管编号
> `LEO-HO-20260830-223623-CODEX-TO-CLAUDE`，确认书带 3 条异议）· 设备处于基线状态：
> 2026-08-31 P1 首窗口已完整恢复并经用户确认，两 XML 原哈希、零覆盖挂载、Volume 205。
> 本轮进展记录在下方 Phase 5B 各条目的缩进注中；**未闭合的复选框一律不勾**。

## Phase 0 — 立项与证据封存

- [x] 确立名称、产品宣言和安全边界；
- [x] 建立独立 Git 项目；
- [x] 引用并锁定现有 `mi-note-pro-hifi-streamer` 基线版本；
- [x] 登记官方 ROM、stock boot/recovery、Spotify splits 和音频文件哈希；
- [x] 建立工程实施、同步讲解和并行研究的协作协议；
- [x] 将当前所有不可公开材料放入被 Git 忽略的私有目录。

## Phase 1 — 音频依赖闭包

- [x] 从官方 `system.img` 和参考机提取完整音频文件集合；
- [x] 分析 32/64 位 ELF 依赖、init 服务、属性、权限和 SELinux 域；
- [x] 记录 Spotify 的 AudioFlinger、AudioPolicy、Mixer、QUAT MI2S 实时路径；
- [x] 解包 stock boot，确定实机 DTB/硬件修订并对照官方源码；
- [x] 建立首批 stock kernel 配置证据子集（v0.1，非完整 `.config`）；
- [x] 建立 stock SELinux 音频有效授权闭包 v0.1（尚不是最终最小权限集）；
- [x] 区分必须保留、支撑保留、条件保留、候选删除和无关组件（v0.2）；
- [x] 生成可机器校验的音频兼容清单 v0.1（尚不是最终最小保留集）。

## Phase 2 — 播放器 Shell 原型

- [x] 固化阶段目标、状态模型、安全门、回退路径和验收矩阵；
- [x] 实现唯一 HOME 界面和 Spotify 启动逻辑；
- [x] 实现隐藏维护入口与本地认证；
- [ ] 提供 Wi-Fi、VPN、更新、诊断和临时 ADB；
- [x] 在当前 MIUI 上以可逆方式验证，不替换 system；
- [ ] 验证重启、耳机插拔、网络中断和 Spotify 崩溃后的行为。

## Phase 3 — MIUI 原型固件构建器

- [x] 接受用户提供的精确官方 ROM 并严格校验；
- [x] 证明 sparse/raw 容器往返与原厂 ext4 双证据语义基线；
- [x] 锁定无修改重建的 builder、Android metadata 与 verified-boot 架构；
- [x] 完成两次本地无修改 ext4 重建、语义同一性、journal 对齐与 `e2fsck = 0`；
- [x] 完成开发态零尾分区与 Android sparse 容器回环，验证完整 raw 字节不变；
- [ ] 解包、精简并重建只读 system 镜像；
- [x] 以二路径差异集成独立签名的最小 Shell，并保留 MIUI Launcher；
- [ ] 集成完整维护组件和保守性能策略；
- [x] 不重新分发 Xiaomi、Google 或 Spotify 文件；
- [x] 为 Gate 3 生成构建清单、SBOM、哈希和恢复边界。

## Phase 4 — 恢复、签名与发布工程

- [x] 独立验证原厂 dm-verity tree、metadata signature、FEC 与 boot/recovery BootSignature；
- [x] 固定 Android 7 legacy verified-boot 源码版本、system/boot 配对契约和首次写入安全顺序；
- [x] 逐字节复现原厂 verity tree/FEC，并双构建 development system/boot/sparse 配对；
- [x] 完成项目配对与 release-set 的故障注入和 fail-closed 校验；
- [x] 建立项目 release keys 与双介质离线保管、断开重连回读规则；
- [x] 用正式密钥重建并冻结首个 release-set；
- [x] 实测 stock recovery/fastboot 救援入口、ADB sideload 与双介质当前 system 备份；
- [x] 在参考设备完成正式 system/boot 首次受控写入、持久启动与 Spotify/HiFi 验收；
- [ ] 实测 USB-OTG 回滚；`system` 的 fastboot 回滚已于 2026-08-28 首次实测，两层材料均已使用；
- [ ] 修复第一代配对无法在干净 `userdata` 上完成 provisioning 的阻断缺陷；
- [ ] 实现启动计数、安全模式和 recovery 入口；
- [ ] 生成签名的完整与增量更新；
- [ ] 在第二台测试设备上完成破坏性故障演练。

## Phase 5A — MIUI 黄金参照

- [x] 保留 Phase 4 已验收的 MIUI 衍生系统作为声音、路由、功耗和恢复参照；
- [x] 冻结原厂音频闭包、boot/DTB、SELinux、运行时路径和回滚材料；
- [ ] 完成 USB-OTG 回滚与长时功耗补充验收。

## Phase 5B — MoKee Compatibility Bridge

- [x] 确立“原版基准 → 音频等价 → 最小化”的中间路线；
- [x] 建立全局路书、证据门、智能等级与五小时窗口执行协议；
- [x] 锁定并验证一个 `leo` MoKee Android 10 ROM；
- [x] 完成 ROM 启动链、分区、音频栈、组件和 SELinux 静态审计；
- [x] 双重重建并回环验证未经修改的 M2 system/boot 离线候选，冻结实机写入路书；
- [x] 在回滚闭合并取得临场授权后验证未经修改的 MoKee 实机基准；
- [x] 持久化 MoKee `system/boot`，实机闭合 ESS 临时路由、R6 与 R7-A；M3 当前已通过
  patch 契约、host mock、feature-OFF 等价、严格 ARM32 语法和 object 生成，详细裁决见
  `docs/reviews/2026-08-29-m3-hifi-controller-progress-ruling.md`；
- [ ] 完成 R7-B（`Volume 205 → 225 → 205`）与真实 Android HAL 模块链接；在两者完成前
  M3 保持 NO-GO DEVICE；
  - R7-B 本身已于 2026-08-30 在机闭合，且覆盖范围超出原定：实测阶梯
    `213 → 229 → 241 → 247 → 205`，每档写入后读回校验、左右声道一致，
    结束时由 `audio_route` 自动复位至 205。
  - 2026-08-31 真实 HAL 模块链接**已完成**：以 `7f4cac74` + 5 个 M3 补丁为输入，
    11/11 源文件用真实 AOSP 头文件与设备实际内核（3.10.108，与设备 `/proc/version`
    吻合）的 uapi 头编译通过，surrogate 头文件依赖已消除；`ld.lld` 链接出
    `ELF 32-bit ARM EABI5 shared object`，SONAME 与 `DT_NEEDED` 同出厂模块一致，
    导出 `HMI`，**122 个未解析符号 100% 由设备自身 12 个运行库满足，缺失 0**，
    并首次导出 `leo_hifi_*` 8 个控制器符号。
    `use_case_table` 悬案同时闭合：实测 10 个编译单元 → 9 个重复定义（此前记录的
    「×11」不准），`-fcommon` 零源码改动即复现出厂语义。
    详见 `docs/reviews/2026-08-31-gate2-real-hal-module-link.md`。
  - **本条仍不勾**，两项条件（R7-B、真实链接）虽均已完成，但产物与出厂模块存在
    确凿结构差异（缺 `.fini_array`，未加 `-D_FORTIFY_SOURCE=2`），且从未被 `dlopen`
    或由 audioserver 加载验证。**链接成功 ≠ 可加载 ≠ 可播放。**是否勾选待用户裁决。
- [ ] 差量恢复 ESS9018、Forte ACDB 和 QUAT MI2S 音频等价性；实机已证明缺口仅在 HAL 的输出设备选择。
  - 2026-08-30 在机验证：纯 XML 改动即可完成 ESS 路由。日志
    `out_snd_device(7: hifi-headphones)`、`apply mixer and update path:
    deep-buffer-playback hifi-headphones`，后端 `S24_LE / KHZ_48`，
    `HPHL DAC Switch=Off`。用 `mount --bind` 实现零分区写入、可逆。
  - ACDB 问题已关闭：MIUI 的 `acdb_device_table[34] = -1` 是毒化哨兵，
    两侧 `enable_snd_device` 均拒负值且不 apply route；MIUI 走 HiFi 时
    snd_device 仍是 `HEADPHONES`（ACDB **10**）。**不要改 ACDB。**
  - 仍未闭合：`compress-offload-playback2` 无 hifi 路径；开机持久化需分区
    写入（未授权）；主观音质与 WCD 的差距未在等响条件下证伪。
  - 2026-08-31 P1 首窗口（Apple Music / MM1 / deep-buffer）实机通过：基线读数首次
    正面证实 `SLIMBUS_0_RX MM1=On` 而 QUAT 全关；A 版挂载后转为 `QUAT_MI2S_RX MM1=On`、
    `HPHL DAC Switch=Off`、`RX1 MIX1 INP*=ZERO`（排除双通路假阳性）、后端 `S24_LE/KHZ_48`，
    hw_ptr 逐帧吻合，用户确认双声道连续无失真，完整恢复且看门狗自然退出。**本条仍不勾**：
    只覆盖一个应用一个 usecase，MM7、插拔、待机、重启、等响音质均未验收。
    结果见 Codex 会话 `outputs/p1-window1-20260831-0750/RESULT.md`。
  - 同窗口实机证实 QUAT 后端**无 teardown 复位点**（恢复后 `SampleRate` 仍停 `KHZ_48`），
    与 M3 裁决书 §4.5 的静态结论一致。
- [ ] 在 HAL 建立可读回验证的 Leo HiFi Controller，并向 Leo Home 提供只读状态显示。
  - 只读状态显示已作为可独立运行的 APK 交付（带桌面图标，34 项单测通过），
    但它不经由 HAL，走的是 USB 状态桥这一过渡实现。**HAL 侧的 Controller
    未开始**，故本条不勾。
- [ ] 建立采样率策略：对 44.1 kHz 家族优先验证端到端 44.1 kHz 输出，消除当前
  `44.1 → 48 kHz` 的非必要 SRC；对无法直通的混音、系统音或 48 kHz 内容明确记录
  SRC 原因与实际输出率，不作“全局 bit-perfect”承诺。
  - 2026-08-31 静态裁决：**44.1 直通在当前 HAL 下无应用可达入口。**
    `AUDIO_OUTPUT_FLAG_DIRECT_PCM` 在整个 HAL 源码树中只出现 1 次（`audio_hw.c:3106`
    的判断本身），无任何代码路径置位它；`utils.c` 的 flag 解析表亦不收录该枚举，
    配置层无法注入。策略层 profile 声明 44100 属误导性证据。
    **目标措辞按用户 2026-08-31 裁定暂不修改**；轮值架构师的修改意见、理由与
    盲改危害分析见 `docs/reviews/2026-08-31-44khz-passthrough-reachability-opinion.md`。

## Phase 5C — `leo_audio` 源码产品

- [ ] 准备 Linux 构建主机和充足的高速存储；
- [ ] 锁定 Android 平台、MSM8994 common、`leo` device/vendor 和内核提交；
- [ ] 建立不继承 full-phone 套件的 `leo_audio` 白名单产品；
- [ ] 首次源码构建只追求启动、显示、触摸、Wi-Fi和有线音频；
- [ ] 去除遗留的 SELinux Permissive 与禁止深度休眠参数；
- [ ] 将专有文件改为用户本地提取，不进入公开源码仓库。

## Phase 6 — 音频与功耗晋级

- [ ] 验证耳机插入、阻抗识别、ESS上电和QUAT MI2S路由；
- [ ] 确认 Spotify 使用的混音、deep-buffer 或 PCM offload 路径；
- [ ] 完成固定曲目的温度、电流、CPU驻留和欠载对照；
- [ ] 使用音频分析仪比较MIUI基线与源码系统；
- [ ] 只有声音、稳定性和恢复均不退化时，宣布第二代可用。

## Phase 7 — Leo Audio OS 1.0

- [ ] 正式 `user` 构建，SELinux Enforcing；
- [ ] 系统只读、ADB默认关闭、无Magisk依赖；
- [ ] 正常状态只呈现播放器；
- [ ] 发布构建器、源代码、补丁、哈希和验收报告；
- [ ] 维护长期兼容性与退役策略。
