# Leo Audio OS 全量工程交接：Phase 5B MoKee 兼容性桥梁

日期：2026-08-26

用途：让新的 AI agent 在**不依赖聊天记录**的情况下，理解项目过去做过什么、为什么这样做、
当前有哪些已验证事实、哪些只是推断、下一步从哪里开始，以及哪些动作绝对不能擅自执行。

---

## 0. 接手者先读：一分钟结论

1. 设备是 Xiaomi Mi Note Pro，代号 `leo`，MSM8994 / Snapdragon 810，核心价值是
   ESS9018K2M + OPA1612 有线 HiFi 路径。
2. 第一代系统已经完成：它仍以 MIUI 9.2.3.0 / Android 7 为底座，但项目已经重建、签名并在
   单台参考机上持久写入了配对的 `system` 和 `boot`；Spotify 登录、外放、耳机、HiFi、只读
   dm-verity system 与 Leo Home 均通过首轮实机验收。
3. 当前要做的不是继续切 MIUI，而是进入 Phase 5B：以 MoKee Android 10 为兼容性桥梁，先证明
   社区系统已有的 ESS/I2S 能力，再以小补丁补回专用 HiFi 控制，最后才做源码级白名单精简。
4. MoKee M0 已经实际完成并已同步路线图：官方 SourceForge ROM 已下载、发布方 MD5、
   本地 SHA-256、大小与 ZIP CRC 全部通过；`system` 和 `boot` 已只读解包。
5. 最重要的新发现：MoKee **已经带有 ESS 内核驱动、QUAT MI2S、I2S mixer/platform 配置、七份
   Forte ACDB 和 Dirac**。真正明显缺失的是 MIUI HAL 中的专用 HiFi property、HiFi 输出设备、
   bit-width/sample-rate 和 volume 控制逻辑。不要把 Android 7 HAL/framework 整体覆盖进 Android 10。
6. 当前没有任何 MoKee 设备写入授权。下一位 agent 只能继续 M1 静态审计、写报告和补丁设计；
   到 M2 实机候选门必须停止，并重新向用户展示目标、哈希、分区、回滚与风险，取得临场确认。
7. 本机数据卷只剩约 `8.4 GiB`。Google Drive 大文件上传因速度不可用，用户已经明确要求越过；
   不要恢复该上传流程，也不要为了腾空间删除任何黄金参照、回滚镜像或私有证据。

---

## 1. 用户真正想做什么

用户并不是想得到“一个能启动的第三方 ROM”，而是把二手价格很低、但有罕见模拟音频硬件的
`leo` 变成一台具有专用设备气质的网络音频播放器：

- 普通状态只呈现 Spotify / 播放器；
- 不保留电话、短信、相机、主题、商店、普通浏览器等消费型入口；
- 保留 Wi-Fi、VPN、存储、更新、恢复和隐藏维护模式；
- 保留或提高原厂 ESS9018K2M、OPA1612、Forte ACDB、Qualcomm DSP 与 QUAT MI2S 的音频表现；
- 只读系统、可恢复、可验证、尽量无后台干扰；
- 正式版为 `user` 构建、SELinux Enforcing、ADB 默认关闭，不依赖 Magisk/常驻 Root；
- 最终公开的是源码、补丁、构建器、清单、哈希和验证报告，不重新分发 Xiaomi / Google /
  Spotify 专有二进制。

用户喜欢“RTOS 感”：不是通用手机加播放器，而是普通状态下只体现单一用途、维护状态才显露
Android 底层。这个目标决定了项目判断标准不是“删了多少 APK”，而是后台唤醒、热量、攻击面、
音频等价和可恢复性是否改善。

用户同时希望通过本项目学习 ROM、启动链、内核、设备树、HAL、DSP、SELinux、系统构建与未来
自主硬件设计。因此每个关键里程碑都应交付两条线：可复现工程产物，以及解释“它是什么、为何
这样做、如何证明”的教学文档。

---

## 2. 仓库、分支与当前工作树

- 仓库：`/Users/km/Desktop/Leo-Audio-OS`
- 当前分支：`main`
- 开始制作交接时相对 `origin/main` **ahead 4**；不要重置、rebase 或覆盖用户已有历史。
- 本次交接之前的已提交基线：`75a12a6 Record Phase 4 first controlled write`。
- 本次交接应作为一个新的本地提交精确包含：
  - `README.md` 修改；
  - `docs/ROADMAP.md` 修改；
  - `docs/16-PHASE-5B-MOKEE-COMPATIBILITY-BRIDGE-RUNBOOK.md` 新增；
  - 本交接文档新增；
  - `resources/mokee-input.lock` 新增；
  - `scripts/audit-mokee-rom.py` 新增；
  - `scripts/stream-sdat2img.py` 新增。
- `resources/private/google-drive-archive.lock` 是 Google Drive 试验产生的私有记录，包含云端对象 ID；
  它已移入 Git 忽略目录，**不要提交到公开 Git**。
- 私有输入和大型构建输出由 `.gitignore` 排除；不得使用 `git add -A`，应逐文件精确添加。
- 本次交接完成本地提交后，预期为相对远端 ahead 5、公开工作树干净；若不是，先检查差异。
- 未经用户明确要求，不推送远端。回复中必须说明 commit 与 push 状态。

接手后第一组命令：

```bash
cd /Users/km/Desktop/Leo-Audio-OS
git status --short --branch
git log -5 --oneline
df -h /System/Volumes/Data
```

---

## 3. 过去完成了什么：工程时间线

### 3.1 前置实践：MIUI 手术级精简与黄金参考机

在独立仓库 `mi-note-pro-hifi-streamer` 中，项目先对原厂 MIUI 做了 Root、频率上限、应用冻结/
框架保护绕过、Spotify 网络与音频路径测试等实践。重要经验是：直接用 Root 文件管理器删除被
MIUI 启动机制保护的系统应用，曾导致设备卡在白色 MI 标志；后续必须先审计启动声明、依赖、
PackageManager/MIUI 保护机制和恢复路径，再做最小、可逆、逐批验证。

这些实践不是第二代 ROM，但提供了三类关键资产：

- 一台真实运行且声音令人满意的黄金参考机；
- 对 MIUI 组件依赖、启动风险、Spotify 与网络行为的实机认识；
- 可靠的 stock ROM、boot、recovery、system 和恢复流程。

### 3.2 Phase 0：立项与资源封存

完成名称、愿景、仓库、许可边界、资源地图和协作方式。官方 ROM、stock 镜像、Spotify splits、
音频文件和私有恢复材料全部只放在 Git 忽略目录；公开仓库只记录来源、哈希、方法和原创代码。

关键文档：

- `docs/VISION.md`
- `docs/ARCHITECTURE.md`
- `docs/01-RESOURCE-MAP.md`
- `docs/02-ENGINEERING-LEARNING-MODE.md`

### 3.3 Phase 1：建立原厂音频依赖闭包

从官方 MIUI `system.img`、stock boot、官方内核源码和参考机运行时证据中，建立了第一版跨层
音频闭包：

```text
Spotify
  -> AudioTrack / AudioFlinger / AudioPolicy
  -> audio.primary.msm8994 HAL
  -> mixer / platform / audio policy
  -> ACDB loader + Forte calibration + ADSP firmware/services
  -> QUAT_MI2S
  -> es9018 kernel codec / I2C / clocks / regulators / GPIO
  -> ESS9018K2M + OPA1612 + headphone output
```

已完成：

- 32/64 位 ELF 依赖、动态加载候选、init 服务、属性和权限分类；
- Spotify 播放、暂停、耳机插入时 AudioFlinger、mixer、kernel 的运行路径采样；
- stock boot 解包和实际 DTB 定位：索引 25，即 MSM8994 v2.1 MTP、无 PM8004；
- 官方内核中的 `es9018.c`、I2S 主从关系、阻抗与上电/关闭时序梳理；
- 首批 stock kernel config 证据；
- stock SELinux 音频有效授权闭包；
- 音频组件分为必须、支撑、条件、候选删除和无关五类。

重要实机事实：外放不触发 HiFi；插入耳机并开始播放才进入专用有线 HiFi 路径。耳机插入本身
不等于 DAC 已上电。测试不能只问“有无声音”，必须证明 QUAT MI2S、ESS 驱动状态和路由。

关键文档：`docs/03` 到 `docs/08`。

### 3.4 Phase 2：Leo Player Shell

在不改 system 的前提下做了可逆 HOME 原型，冻结版本：

- 包：`io.github.leoaudio.shell.debug`
- versionName：`0.2.7-dev.1-home-debug`
- 默认 HOME：`io.github.leoaudio.shell.debug/.MainActivity`
- MIUI Launcher 保留并可从维护页进入。

冻结行为：

- 极简就绪页、显式启动 Spotify；
- 隐藏七次点击维护入口；
- 6 位本地 PIN、PBKDF2、五次错误锁定 30 秒；
- 五分钟维护会话，退出即锁定；
- Wi-Fi、VPN、Spotify/Leo 应用信息入口；
- HOME 根页返回键不退出、不黑屏；
- 修复旧 MIUI 的维护页布局崩溃；
- 安全预览变体不声明 HOME。

这里采用了“先安全预览、后 HOME candidate、始终保留 MIUI Launcher 回退”的方法。用户对每个
实机行为逐项验收，而不是用编译成功替代视觉/交互验收。

关键文档：`docs/09-PHASE-2-PLAYER-SHELL-RUNBOOK.md` 和
`docs/reviews/2026-08-24-phase2-baseline-freeze.md`。

### 3.5 Phase 3：MIUI system 可复现构建

Phase 3 的意义不是“继续删 MIUI”，而是把原厂 system 从一个不可解释的大包变成可解析、可重建、
可比较、可签名和可回滚的工程对象。

#### Gate 0：锁定输入和几何

- 只接受精确官方 ROM；
- 锁定 sparse/raw、分区大小、文件系统几何；
- `persist` 等非目标分区明确禁止写入。

#### Gate 1：原厂 ext4 双证据审计

- 无特权 direct ext4 parser 为主证据；
- Linux 内核只读挂载为交叉证据；
- 导出 3923 条 system 语义记录；
- 将内容、uid/gid/mode、capability、SELinux xattr、symlink、设备节点等纳入比较；
- 证明“能解包”不等于“能安全重建”，尤其不能丢 Android metadata 与 SELinux 标签。

#### Gate 2：无修改重建

- 两次完整 ext4 build 的语义和 raw SHA-256 相同；
- UUID、label、feature set、reserved GDT、6552-block internal journal 对齐；
- `e2fsck -f -n` exit 0；
- 构建 425984 × 4096 byte 的开发态完整分区；
- `raw -> Android sparse v1 -> raw` 后完整分区逐字节一致；
- 明确区分 development-unverified 容器和正式 verity/FEC 发布容器。

#### Gate 3：最小有意差异

只允许新增：

```text
/system/app/LeoShell/
/system/app/LeoShell/LeoShell.apk
```

冻结证据：

- APK SHA-256：`8a81a01f22098ba1b95be72d8fa333ad200738f16029c865f90b9669e57489ff`
- Gate 3 ext4 SHA-256：`10857ee55fd85f485febd15407b58b4da6dc95ba2ef932826ef505d38342574c`
- 双 APK 构建、双签名、双 ext4 构建均可复现；
- 3923 条原厂路径语义不变；
- 17 条音频兼容项和 MIUI Launcher 保持；
- `e2fsck`、SELinux closed-world lookup、sparse/raw 回环通过。

关键方法是**先证明无修改重建，再允许唯一差异**。没有把“解包、删包、重打包、刷机”混成一次
不可归因的尝试。

### 3.6 Phase 4：legacy verified boot、恢复和首次受控写入

Phase 4 逐字节复现 Android 7 legacy dm-verity tree/FEC，建立项目 `system`/`boot` 配对、独立
release keys、双构建、故障注入和 fail-closed verifier。私钥口令只存在 macOS 登录钥匙串，
密钥与恢复材料在两块不同物理介质断开/重连后逐文件哈希回读。

正式 tuple：

| 成员 | SHA-256 |
| --- | --- |
| verified system raw | `e18a6fc83c59e09415d4a802a052c66fccf46e420b1f25f752e85546f8affad4` |
| Android sparse system | `afa12b23e4570f96cc5e4ee70cf754779c75cf834a9d61f481f08d1a96e21eb1` |
| project boot | `dfca241d75d494e0d85502d1368a3475f0e2576dd69b28274fcf4532a2779685` |
| release-set manifest | `ec1f23178e7825b28ac1dbb6f348a7eed97b7f3776e69b1a58d63ab4d8123e5a` |

写入纪律：

1. 先核验 fastboot 身份、解锁状态、电量、线缆、分区几何；
2. 实测正常 recovery 的按键导航、MiAssistant/ADB sideload 与回 fastboot；
3. 当前 system 从设备只读流出，同时写入两块介质并完整回读；
4. 用户第一次单独确认后，只写 `system`；
5. 不立刻写 boot，先 `fastboot boot` 同 hash project boot；
6. 启动后验证 `/system=/dev/block/dm-0` 只读、dm-verity、Leo Shell、Spotify、外放、耳机、HiFi；
7. 短时连续播放和热状态通过；
8. 用户第二次单独确认后，才持久写 `boot`；
9. 正常重启后再次验证，而不是把临时启动误当持久启动。

实际写入只有 `system` 和 `boot`。未写/未清：`userdata`、`recovery`、`persist`、`modem`、`tz`、
`aboot`、Bootloader 等。参考机当前是第一代 MIUI 衍生 Leo Audio OS 黄金参照，Spotify 登录态与
userdata 保留。

尚未闭合：第二台设备、实际 boot/system 回滚、USB-OTG、多次冷启动、异常断电、低电量、长时
待机/播放、启动失败自动回退、恢复出厂后的 provisioning。

---

## 4. 我们的工作方法

### 4.1 证据等级

所有结论要标注等级，避免把推断写成事实：

1. **运行事实**：真实设备、真实命令、用户可见行为、日志、mixer、温度、挂载状态；
2. **制品事实**：文件大小、哈希、ZIP CRC、ELF 符号/字符串、镜像结构、`e2fsck`；
3. **源码事实**：锁定 commit 中明确存在的代码路径；
4. **推断**：多层证据一致但尚未实机验证；
5. **假设/待证**：下一步实验的对象。

例如：“MoKee mixer 指向 QUAT MI2S”是制品/源码事实；“MoKee 原版一定具有与 MIUI 相同 HiFi
音质”仍是待证，直到运行时路由和听测/仪器对照完成。

### 4.2 Gate 与冻结点

每一阶段都必须有：输入、允许差异、输出、验证、负向测试、停止条件、回退和冻结 commit/tag。
冻结点之后不偷偷改旧产物；新变化进入新 Gate。这样失败时能知道是哪一层导致，而不是重新刷机
后从头猜测。

### 4.3 Fail-closed

验证器遇到缺文件、错哈希、错 key、错 target、未知差异或不完整证据时必须失败；不得用 warning
继续。Phase 4 对 ext4、tree、metadata、FEC、verity key、boot signed region/footer、target 和
release-set 成员做过故障注入。

### 4.4 差量而非整体替换

- 先比较组件，判定：已有且保留 / 源码补丁 / shim / 本地专有提取 / 禁止移植；
- Android 7 HAL 不能因为“原厂音质好”就整体覆盖 Android 10；
- 不同时首次引入音频移植和大规模删包；
- 先原版基准，再音频等价，再最小化。

### 4.5 设备操作纪律

- 读屏、`adb shell`、hash、分区尺寸等只读检查可以先做；
- wipe/flash 前必须重新展示 exact target、hash、预计耗时和回滚，并取得当场确认；
- 一次只写一个逻辑阶段；`system` 和 `boot` 要分开确认；
- 从不使用 `flash_all`；
- 连接不稳、设备身份不符、recovery 输入不可靠、空间不足即停止；
- 用户的“正常”是实机验收证据，但要同时记录测试条件和尚未覆盖范围。

### 4.6 可复现和独立复核

- 关键镜像双构建；
- hash + `cmp` + 语义清单，不只比较文件名；
- ext4 用 direct parser 与 Linux/`e2fsprogs` 交叉；
- ZIP 要验证发布方 hash、本地 SHA-256 与每项 CRC；
- 公开 manifest 绑定私有输出 hash，不提交专有字节；
- 在提交前运行 `git diff --check`、目标脚本正向/负向测试和 `git status`。

### 4.7 智能档位与 usage 窗口

- **SH / Sol High**：架构、启动链、ABI、音频、SELinux、删除边界、刷写和回滚；
- **TM / Terra Medium**：按已冻结契约执行下载、hash、解包、机械 diff、脚本、文档和测试；
- 发现未定义差异时从 TM 上提 SH，不在低档位临时发明架构；
- 五小时窗口最后 20–30 分钟只做验证、记录、提交和交接，不开启新方向；
- 长下载/哈希让机器运行，模型额度用于裁决；终端仍在运行不等于任务完成。

---

## 5. Phase 5B 当前完成的真实工作

### 5.1 M0：MoKee 输入已经锁定并验证

来源：MoKee 官方 SourceForge `RELEASE/leo`：

`https://sourceforge.net/projects/mokee/files/RELEASE/leo/MK100.0-leo-221019-RELEASE.zip/download`

| 字段 | 值 |
| --- | --- |
| 文件 | `MK100.0-leo-221019-RELEASE.zip` |
| 大小 | `647032071` bytes |
| 发布方 MD5 | `1e4026ea6788f9e8adc8419602d11e46` |
| 本地 SHA-256 | `e1d32441513d49108802cc426b0891f7c3be577f2cb41d4030b4fe2ddf614390` |
| 构建时间 | 2022-10-22 |
| Android | 10 / SDK 29 |
| 安全补丁 | 2022-08-05 |
| target | `NotePro,leo` |
| fingerprint | `Xiaomi/mokee_leo/leo:10/QQ3A.200805.001/eng.buildb.20221022.184840:userdebug/dev-keys` |

发布方大小、MD5、本地 SHA-256、全部 ZIP CRC 均通过。ZIP 只有 10 个成员；主体为
`system.new.dat.br`、`boot.img`、transfer list、updater 与 backuptool。

公开锁：`resources/mokee-input.lock`

私有原件：

`resources/private/phase5b-mokee/verified/MK100.0-leo-221019-RELEASE.zip`

验证报告：

`resources/private/phase5b-mokee/audit-v0.1/rom-identity.json`

`docs/ROADMAP.md` 中 M0 输入锁定 checkbox 已同步为完成；M1 静态审计仍保持未完成。

### 5.2 安装脚本的分区边界

updater-script 已证明：

- assert `NotePro`/`leo`；
- 要求 `TZ.BF.3.0.R1-00226`；
- 写 `system`；
- 写 `boot`；
- 不写 modem、tz、aboot、recovery、userdata 等；
- 在 system 前后运行 `backuptool.sh`。

`backuptool` 可能保存并恢复现有 GApps/add-ons，所以未来“原版 MoKee 基准”要明确是否禁用该机制，
不能把从旧系统继承的 add-on 误认为 ROM 自带能力。

### 5.3 system 重建

新增 `scripts/stream-sdat2img.py`，将 ZIP 中的 Brotli 数据流直接送入重建器，避免同时落地 `.br`、
完整 `new.dat` 和 raw 三份大文件。

transfer list：

- version 4；
- declared touched blocks：`391529`；
- new：`383610` blocks；
- zero：`7919` blocks；
- erase：`34455` blocks；
- max block：`425984`；
- block size：4096。

输出：

- `resources/private/phase5b-mokee/extracted/system.partition.raw`
- 大小：`1744830464` bytes
- SHA-256：`7238ee916246f6ac4564d7386639494323bae01b67eb8bed6b0168b2d47689c3`

用 `/opt/homebrew/opt/e2fsprogs/sbin/e2fsck 1.47.4 -f -n` 检查 exit 0：

```text
/: 4579/106496 files (0.5% non-contiguous), 390506/425984 blocks
```

报告：`resources/private/phase5b-mokee/audit-v0.1/system-reconstruction.json`

这是 system-as-root 布局，`/system/vendor` 位于同一 system 分区，不存在 ZIP 中单独的 vendor image。

### 5.4 boot 静态审计

输出：

- `resources/private/phase5b-mokee/extracted/boot.img`
- SHA-256：`9470dd6a01120480289c17d0da161e73b2eb6361ece3ea72041b07da088934af`
- 报告：`resources/private/phase5b-mokee/boot-audit-v0.1/metadata.json`

事实：

- legacy-v0-compatible boot header；
- Android 10，patch level 2022-08；
- kernel section gzip，附加 36 份 DTB；
- minimal system-as-root ramdisk；
- 没有检测到 Android BootSignature footer；
- cmdline 包含：

```text
androidboot.selinux=permissive
lpm_levels.sleep_disabled=1
buildvariant=userdebug
```

`default.prop` 还包含：

```text
ro.secure=0
ro.adb.secure=0
ro.debuggable=1
persist.sys.usb.config=adb
```

裁决：这可以作为 unlocked-bootloader 的 bring-up ROM，但不能成为正式产品安全基线。后续必须移除
permissive、默认 ADB、`ro.secure=0` 和禁止深度休眠参数，并建立项目签名/恢复契约。

### 5.5 最关键的音频发现

MoKee ROM 已包含：

- kernel 中的 `es9018` / `ess,es9018` / `es9018.6-0048`；
- `QUAT_MI2S BitWidth`、`QUAT_MI2S SampleRate` 和 QUAT routing 字符串；
- 32/64 位 `audio.primary.msm8994.so`；
- `audio_platform_info_i2s.xml`、`mixer_paths_i2s.xml`；
- 七份 `Forte_*.acdb`；
- Dirac API 与 Android 10 wrapper；
- XML AudioPolicy 与 HIDL audio 2.0。

字节比较：

- 七份 Forte ACDB 与 MIUI stock **全部逐字节相同**；
- `mixer_paths.xml` 与 stock **逐字节相同**；
- `audio_platform_info_i2s.xml`、`mixer_paths_i2s.xml` 只在版权注释行不同，功能 XML 相同；
- `libDiracAPI_SHARED.so` 与 stock 相同，SHA-256：
  `e811aeaa6e86ac2e6018f74512939ce970f76a41cc4e6060aebda5fb82e15840`；
- `libdirac.so` wrapper 与 stock 不同，推测是 Android 10 兼容层，应该优先保留 MoKee 版本。

HAL SHA-256：

- MoKee 32-bit：`701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47`
- MoKee 64-bit：`6939be82ada44c5772dcfe6977443eccdc03ee2bc85199e412112ebeefe47ee0`
- MIUI stock 32-bit：`0b8e3f6290532499ac19c881fc8cbe36c8212f3dd83fe4aa3527ff6265fe038a`

三者都能看到 `Call MIXER_XML_PATH_I2S`，说明 MoKee HAL 会根据 I2S sound card 选择 I2S mixer。
但只有 MIUI stock HAL 能看到：

```text
SND_DEVICE_OUT_HIFI_HEADPHONES
persist.audio.hifi
persist.audio.hifi.volume
platform_set_hifi_property
QUAT_MI2S BitWidth
QUAT_MI2S SampleRate
```

MoKee 32/64 HAL 均缺少这些专用控制字符串；其锁定源码中也没有对应 Mi HiFi 逻辑。

当前最佳架构判断（**高可信推断，尚待实机**）：

1. 原版 MoKee 很可能已经能把普通耳机输出路由到 ESS/QUAT I2S；
2. 它缺少的是 MIUI 的专用 HiFi property、输出设备、位宽/采样率和音量控制；
3. 最安全路线是把缺失的小段逻辑移植/重写到 Android 10 的开源 Qualcomm HAL；
4. 不应把 Android 7 的 stock HAL、audioserver 或 framework 整体丢入 Android 10；
5. 先保留 MoKee 的 Android 10 wrapper、loader 与 namespace 兼容性，再逐项证明是否需要 stock blob。

仍未闭合：

- MoKee 没有 stock `audiod`，需判断 ESS/Dirac 是否实际需要；
- 社区 vendor 中部分 ACDB loader/support blobs 与 stock hash 不同，需要 ELF/ABI/runtime 审计；
- 需要对 DTB index 25 做语义 diff；
- SELinux/init/设备节点的 MoKee 音频闭包还未形成正式矩阵；
- 原版 MoKee 运行时是否真的进入 ESS HiFi 尚未验证。

### 5.6 已锁定源码树

这些目录都在 `build-private/sources/`，被 Git 忽略：

| 源码 | 分支/commit |
| --- | --- |
| MoKee Qualcomm audio msm8994 | `mkq-mr1-caf-msm8994` / `7f4cac748b6f62897294cdaece9d1aec27e1e927` |
| Xiaomi classic msm8994 common device | `ec5b87cad6a8f5326201ca4764410996b0a94133` |
| Xiaomi classic msm8994 common vendor | `4fcd70ff1fe6e1f5b6e29159c94a0760c646785b` |
| Xiaomi classic leo kernel | `mkr-mr1` / `17a5b8886d0b715df16c7b71cfcf19b5f78c3ad7` |
| Xiaomi official kernel | `libra-n-oss` / `f4cab50d74f8e55e0a0dbbf430d163f46c6fc3a1` |

MoKee audio source中的 `platform_init()` 已确认：当 sound card 匹配 I2S 条件时加载
`/vendor/etc/mixer_paths_i2s.xml`。该源码没有 MIUI 专用 HiFi property/control 实现。

---

## 6. Google Drive 试验：已明确放弃

Google Drive connector 的读写权限已经成功重授权，小文件创建、上传和元数据回读通过。但大文件
路径不可用：

- connector 单文件硬上限 512 MiB；
- 500 MB、100 MB、25 MB 分片均在 OpenAI 中转层 60 秒超时；
- 改用 Google Drive 网页直传 647 MB ROM 时，速度从预计 38 分钟恶化到约 8 小时；
- 用户于 2026-08-26 明确决定越过，不再做 Google Drive 上传。

Drive `10-Immutable-Inputs` 在停止后通过 API 回读为空，没有 ROM 云端对象。完整本地 ROM 保持
`647032071` bytes。临时分片已删除，只删除了本次生成的可再生 staging，不涉及任何项目原件。

不要再次尝试 Drive、浏览器分片或安装同步客户端，除非用户主动重启该方向。已上传的小型文档
可保留，但不作为项目恢复或发布证据。

---

## 7. 本机空间与私有资产

当前数据卷约剩 `8.4 GiB`，项目约 42 GiB。主要占用（近似）：

| 路径 | 大小 | 性质 |
| --- | ---: | --- |
| `resources/private/phase3-gate2` | 14 GiB | 历史重建候选/探针；可再生但勿直接删 |
| `resources/private/phase3-gate3` | 8.1 GiB | 冻结 Gate 3 私有证据 |
| `resources/private/phase4-release-v1` | 6.8 GiB | 正式 release-set；关键恢复/发布资产 |
| `resources/private/phase3-gate1` | 3.0 GiB | stock ext4 语义证据 |
| `resources/private/stock-rom` | 2.8 GiB | exact stock 回滚输入 |
| `resources/private/phase4-project-probe` | 2.6 GiB | Phase 4 探针，可再生 |
| `resources/private/phase5b-mokee` | 2.2 GiB | 当前活跃 MoKee 输入/输出 |
| `build-private/sources` | 2.2 GiB | 私有源码工作树，可重新 clone |

停止条件仍是：预计操作若使空间低于 6 GiB，先停止。不要展开完整 AOSP，不要复制第二份 system
raw。后续若必须释放空间，应先做“可再生性 + hash + exact target”清单，并由用户确认清理批次。
不要把 `stock-rom`、Phase 4 release/rollback 或当前黄金参照当普通缓存。

---

## 8. 接下来该怎么做

### 8.1 第一个 SH 模块：完成 M1 音频差量裁决

目标输出：

- `manifests/mokee-audio-delta-v0.1.tsv`
- `docs/reviews/2026-08-26-phase5b-m0-m1-static-audit.md`

建议矩阵字段：

```text
component
mokee_path
stock_path
mokee_sha256
stock_sha256
abi
evidence
disposition
risk
runtime_test
```

初始 disposition：

| 组件 | 初步裁决 |
| --- | --- |
| MoKee kernel ESS driver / QUAT MI2S | 保留，先做 DTB/source 语义 diff |
| I2S mixer/platform XML | 功能等价，保留 MoKee 文件 |
| 七份 Forte ACDB | 与 stock 相同，保留；公开仓库只放 hash，不放字节 |
| MoKee Android 10 32/64 HAL | 作为 ABI 基础保留 |
| MIUI HiFi control logic | 源码级最小补丁/重写，不 drop-in 整个 HAL |
| stock Android 7 HAL | 参考证据；默认禁止直接替换 |
| Dirac API | 相同 blob，本地提取边界 |
| MoKee Dirac wrapper | 优先保留 Android 10 兼容版本 |
| `audiod` | 调查是否必要，不凭 stock 存在就移植 |
| ACDB loader/support libs | 先保留 MoKee 兼容版本，做 ELF/runtime 验证 |

### 8.2 第二个 TM 模块：DTB 与组件机械审计

本机有 `build-private/tools/dtc`。黄金 stock 实机 DTB 和 MoKee 候选均为 index 25 路径：

```bash
build-private/tools/dtc -I dtb -O dts \
  -o /tmp/leo-stock-25.dts \
  resources/private/stock-boot-analysis-v2/dtbs/25.dtb

build-private/tools/dtc -I dtb -O dts \
  -o /tmp/leo-mokee-25.dts \
  resources/private/phase5b-mokee/boot-audit-v0.1/dtbs/25.dtb

diff -u /tmp/leo-stock-25.dts /tmp/leo-mokee-25.dts
```

不要把所有 diff 都解释成音频风险。先筛：`es9018`、I2C、regulator、clock、pinctrl、GPIO、
`qcom,model`、sound card、QUAT MI2S、PMIC。把无关 kernel-version/phandle/排序差异单独分类。

随后生成 system app/priv-app、init service、audio policy、SELinux、权限与设备节点清单。代表性待删
组件包括 ViaBrowser、Phonograph、Calendar、AudioFX、TeleService、Telecom、TelephonyProvider、
ContactsProvider、MmsService、qcrilmsgtunnel、MoKeeCenter、MoKeePay、SetupWizard 等；但 M1 只分类，
不删除。

### 8.3 第三个 SH 模块：HiFi HAL 补丁设计

1. 以 `build-private/sources/mokee-qcom-audio-msm8994` 为基线；
2. 从 stock HAL 字符串、官方/社区相关源码和 mixer controls 还原最小状态机；
3. 明确 property 归属、触发条件、输出设备枚举、bit width/sample rate、volume 和关闭路径；
4. 不引入 Android 7 audioserver/framework；
5. 将补丁限定在 HAL/source/product property，做 32/64 编译与静态 ABI 检查；
6. 先生成候选和运行时测试设计，不刷设备。

需要回答：

- MIUI `persist.audio.hifi` 是用户设置、插入状态还是 HAL 内部状态？
- Spotify 16-bit 流为何/如何进入 24-bit QUAT backend？
- 何时切 `SND_DEVICE_OUT_HIFI_HEADPHONES`？
- 不同阻抗、采样率和音量控制如何映射 mixer；
- 暂停/拔耳机/最后一个 stream 关闭时是否可靠下电。

### 8.4 M1 收口后停止

M1 报告必须回答：

1. 原版 MoKee 如何启动、会写哪些分区；
2. 它现有音频链到哪一层；
3. 与 MIUI 黄金音频链真正不同的最小集合；
4. 原版实机候选是否值得进入 M2；
5. M2 如何回滚、采集和判定 ESS，而不是只听到声音。

到此停止。不要因为 M1 结论乐观就执行 recovery ZIP、fastboot、wipe 或 system/boot 写入。

---

## 9. 可复现命令

### 9.1 ROM 验证

```bash
cd /Users/km/Desktop/Leo-Audio-OS
python3 scripts/audit-mokee-rom.py \
  --expected-size 647032071 \
  --expected-md5 1e4026ea6788f9e8adc8419602d11e46 \
  resources/private/phase5b-mokee/verified/MK100.0-leo-221019-RELEASE.zip \
  resources/private/phase5b-mokee/audit-v0.1
```

该命令会重写同一路径下的公开格式审计 JSON/TSV；运行前先确认目标目录只属于本次 MoKee 审计。

### 9.2 system 文件系统健康

```bash
/opt/homebrew/opt/e2fsprogs/sbin/e2fsck -f -n \
  resources/private/phase5b-mokee/extracted/system.partition.raw
```

预期 exit 0，记录应为 `4579/106496 files`、`390506/425984 blocks`。

### 9.3 音频差异快速复核

```bash
cmp -s \
  resources/private/stock-system-audio/etc/mixer_paths.xml \
  resources/private/phase5b-mokee/selected/system/vendor/etc/mixer_paths.xml

strings resources/private/stock-system-audio/lib/hw/audio.primary.msm8994.so \
  | rg 'HIFI|hifi|QUAT_MI2S'

strings resources/private/phase5b-mokee/selected/system/vendor/lib/hw/audio.primary.msm8994.so \
  | rg 'HIFI|hifi|QUAT_MI2S|MIXER_XML_PATH_I2S'
```

### 9.4 工作树收口

```bash
git diff --check
python3 -m py_compile scripts/audit-mokee-rom.py scripts/stream-sdat2img.py
git status --short
```

只精确添加公开文件，不添加 `resources/private/`、`build-private/`、ROM、镜像、APK、key 或
Google Drive ID 记录。

---

## 10. 接手者不得做的事

- 不恢复 Google Drive 大文件上传；
- 不删除或移动 Phase 4 release/rollback、stock ROM 或黄金参照；
- 不用 `git reset --hard`、`git checkout --` 或 `git add -A`；
- 不把 proprietary blobs、ROM、Spotify、GMS、私钥或设备数据提交 Git；
- 不整体覆盖 Android 10 的 HAL/audioserver/framework；
- 不把 SELinux Permissive 当最终解决方案；
- 不在同一候选首次做音频移植和大规模删包；
- 不把“耳机能响”写成“ESS HiFi 等价已通过”；
- 不把单机一次启动写成发布成熟；
- 不向手机写入任何分区，除非用户在看到 exact target/hash/回滚后当场明确确认；
- 不推送远端，除非用户明确要求。

---

## 11. 当前可信度表

| 结论 | 等级 | 状态 |
| --- | --- | --- |
| 第一代 MIUI 衍生 system/boot 已在单台参考机持久运行 | 运行事实 | 已验证 |
| Spotify 登录、外放、耳机、HiFi 首轮通过 | 运行事实 | 已验证，非长期/仪器测试 |
| MoKee ZIP 身份、大小、MD5、SHA-256、CRC | 制品事实 | 已验证 |
| MoKee updater 只写 system/boot | 制品事实 | 已验证；backuptool 需注意 |
| MoKee system raw 健康、分区几何正确 | 制品事实 | 已验证 |
| MoKee boot 为 permissive userdebug，默认 ADB | 制品事实 | 已验证 |
| MoKee kernel 含 ESS/QUAT 证据 | 制品/源码事实 | 已验证 |
| Forte ACDB、主要 mixer 与 stock 等价 | 制品事实 | 已验证 |
| MoKee HAL 缺 MIUI 专用 HiFi 控制字符串/源码 | 制品/源码事实 | 已验证 |
| 原版 MoKee 可通过 ESS 输出普通耳机音频 | 推断 | 高可信，待实机 |
| 源码补回小段 HAL 逻辑即可达到完整等价 | 架构假设 | 候选方案，待实现与实机 |
| MoKee 可作为长期最小系统底座 | 项目假设 | M1/M2 后再裁决 |

---

## 12. 本次交接收口校验

2026-08-27 在提交前已完成：

- `python3 -m py_compile scripts/audit-mokee-rom.py scripts/stream-sdat2img.py` 通过；
- `audit-mokee-rom.py` 对 647 MB ROM 全量重跑，size、MD5、ZIP CRC、10-entry inventory 和
  SHA-256 全部复现，`verification_passed=true`；
- `stream-sdat2img.py` 使用 3-block 合成 transfer list 完成 byte-placement 正向测试；
- 同一脚本面对多余 `new.dat` 字节时按预期拒绝，负向测试通过；
- `git diff --cached --check` 通过；
- Google Drive 私有 ID 记录不在 staged/public 文件中；
- 本轮没有连接设备、调用 ADB/fastboot/recovery，也没有写入任何分区。

这些校验只覆盖脚本和静态输入，不代表 M1 已完成，更不代表 MoKee 可以刷入。

---

## 13. 建议接手后的前 30 分钟

1. 读本文件、`README.md`、`docs/ROADMAP.md` 和 `docs/16-...RUNBOOK.md`；
2. 运行 `git status`、`df -h`，确认没有残留下载/上传/构建进程；
3. 读取 `rom-identity.json`、`system-reconstruction.json`、boot `metadata.json`；
4. 重新跑 `git diff --check`、Python compile 和 ROM audit 的只读验证；
5. 建立 `mokee-audio-delta-v0.1.tsv`，把本文 8.1 的初始裁决变成机器清单；
6. 用 `dtc` 完成 stock/MoKee index 25 的音频相关语义 diff；
7. 写 M0/M1 静态审计报告；
8. 在 usage 窗口末尾本地提交，不推送；
9. 明确向用户报告：完成了哪些静态事实、仍缺哪些证据、距离设备写入门还有多远。

如果接手者只能完成一件事，应完成“音频差量矩阵 + M1 报告”，而不是开始刷机或继续扩张源码树。
