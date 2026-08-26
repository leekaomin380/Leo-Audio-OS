# 长期路线图

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
- [ ] 实测 USB-OTG 与完整 boot/system 回滚；
- [ ] 实现启动计数、安全模式和 recovery 入口；
- [ ] 生成签名的完整与增量更新；
- [ ] 在第二台测试设备上完成破坏性故障演练。

## Phase 5 — 源码系统 Bring-up

- [ ] 准备 Linux 构建主机和充足的高速存储；
- [ ] 锁定 Android 平台、MSM8994 common、`leo` device/vendor 和内核提交；
- [ ] 首次构建只追求启动、显示、触摸、Wi-Fi和有线音频；
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
