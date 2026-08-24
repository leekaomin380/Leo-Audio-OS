# 长期路线图

## Phase 0 — 立项与证据封存

- [x] 确立名称、产品宣言和安全边界；
- [x] 建立独立 Git 项目；
- [ ] 引用并锁定现有 `mi-note-pro-hifi-streamer` 基线版本；
- [ ] 登记官方 ROM、stock boot/recovery、Spotify splits 和音频文件哈希；
- [ ] 将所有不可公开材料放入被 Git 忽略的私有目录。

## Phase 1 — 音频依赖闭包

- [ ] 从官方 `system.img` 和参考机提取完整音频文件集合；
- [ ] 分析 32/64 位 ELF 依赖、init 服务、属性、权限和 SELinux 域；
- [ ] 记录 AudioFlinger、AudioPolicy、Mixer、QUAT MI2S 的实时路径；
- [ ] 区分必须保留、条件保留和无关组件；
- [ ] 生成可机器校验的音频兼容清单。

## Phase 2 — 播放器 Shell 原型

- [ ] 实现唯一 HOME 界面和 Spotify 启动逻辑；
- [ ] 实现隐藏维护入口与本地认证；
- [ ] 提供 Wi-Fi、VPN、更新、诊断和临时 ADB；
- [ ] 在当前 MIUI 上以可逆方式验证，不替换 system；
- [ ] 验证重启、耳机插拔、网络中断和 Spotify 崩溃后的行为。

## Phase 3 — MIUI 原型固件构建器

- [ ] 接受用户提供的精确官方 ROM 并严格校验；
- [ ] 解包、精简并重建只读 system 镜像；
- [ ] 集成 Shell、维护组件和保守性能策略；
- [ ] 不重新分发 Xiaomi、Google 或 Spotify 文件；
- [ ] 生成构建清单、SBOM、哈希和恢复说明。

## Phase 4 — 恢复、签名与发布工程

- [ ] 建立项目 release keys 与离线保管规则；
- [ ] 构建并临时启动 recovery，实测 USB-OTG、ADB、备份与恢复；
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
