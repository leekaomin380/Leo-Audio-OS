# 2026-08-28：M2 之后的回滚实测、故障处置与新发现缺陷

日期：2026-08-28
范围：M2 运行时基准采集完成之后，从 MoKee 回滚到第一代系统的全过程
结果：**回滚成功，但只在 exact stock 层成功。Phase 4 配对在干净 `/data` 上启动失败。**

## 0. 裁定

1. `docs/ROADMAP.md` Phase 4「完整 boot/system 回滚」的 **system 半边首次实测**，
   两层回滚材料都被实际使用过；
2. **新发现阻断级缺陷**：Phase 4 项目配对无法在干净 `/data` 上完成启动；
3. 过程中暴露五条此前任何文档都未记录的操作陷阱，全部列于 §3，
   其中两条应升级为禁令。

## 1. 回滚序列实录

设备起点：`system` = 未修改 MoKee（`695eba5e…fe7b`），`boot` 分区仍为
Phase 4 project boot（M2 全程只做 `fastboot boot` 临时启动，从未持久写入 MoKee boot）。
因此回滚只需写 `system` 一个分区。

| # | 动作 | 结果 |
| --- | --- | --- |
| 1 | `fastboot flash system` ← Phase 4 黄金 sparse `afa12b23…e21eb1` | 3 轮 OKAY，66 s |
| 2 | `fastboot reboot` | **未进系统**，落入原厂 recovery |
| 3 | 主机 `fastboot format userdata` | 成功建立 ext4，但引发新问题（见 §3.2） |
| 4 | 重启 | 「密码正确，但数据已损坏」——vold 解密 UI |
| 5 | `fastboot boot` 原厂 recovery `4aafc56e…f461e0` | 起来了，但 UI 残缺不可操作（见 §3.5） |
| 6 | `fastboot erase misc` | 解除 BCB 劫持（见 §3.3） |
| 7 | `fastboot reboot` | 到达「数据已损坏」界面，出现「重置手机」按钮 |
| 8 | 点击重置 → 系统写 BCB → recovery（**UI 正常**）→ 清除数据 | 成功 |
| 9 | 重启 | **卡在 MIUI 开机动画，长时间无进展**（见 §4） |
| 10 | `fastboot flash system` ← exact stock `03960aed…d36003` | 3 轮 OKAY，48 s |
| 11 | `fastboot flash boot` ← exact stock `bc64d15c…e567d5` | OKAY |
| 12 | `fastboot erase bk1`、`fastboot erase misc` | OKAY |
| 13 | `fastboot reboot` | **正常进入 MIUI 9.2.3.0** |

全程未写 `recovery`、`persist`、`modem`、`tz`、`aboot` 与 Bootloader。

## 2. 最终设备状态

| 分区 | 内容 |
| --- | --- |
| `system` | exact stock `03960aeded4f6b3c7802109ff74aedec67c5de15841bf175ace66a89cde36003` |
| `boot` | exact stock `bc64d15c26c53644e0d66e8dd3dc9e9c52bf2d4e4267d3c9f71ee90455e567d5` |
| `recovery` | 原厂，全程未写 |
| `userdata` | 由 MIUI recovery 以设备原生参数清空的空 ext4 |
| `bk1` / `misc` | 已擦除 |

Bootloader 仍 unlocked。设备无 Leo Shell、无 root、无 Spotify，为干净出厂态。

## 3. 五条此前未记录的陷阱

### 3.1 跨 Android 大版本回滚必须清 `userdata`（应升级为禁令）

`docs/18` §7 只写了「回滚仍只写确有必要的 `system`/`boot`」。这在同版本内成立，
**跨大版本不成立**。MoKee（Android 10）用过的 `/data` 含 apex、新 quota 与目录布局，
Android 7 的 fs_mgr 处理不了，直接导致 §1 第 2 步启动失败。

7 → 10 要清数据是已知的；**10 → 7 同样要清**，此前无任何文档提及。

### 3.2 禁止用主机 `fastboot format` 格式化老设备的 `userdata`（应升级为禁令）

主机 e2fsprogs（本次为 1.47.2）建立的 ext4 默认启用 `metadata_csum`、`64bit` 等
特性，MSM8994 的 3.10 内核未必支持。更关键的是它**只处理 `userdata`，不触碰 `bk1`**，
造成文件系统与加密页脚状态不一致（见 §3.4）。

正确做法：用设备自己的 recovery 执行「清除数据」，或 `fastboot erase` 只擦不建，
再由设备侧格式化。

### 3.3 BCB 劫持：`/data` 故障会导致无法自愈的 recovery 循环

Android 挂载 `/data` 失败时会向 `misc` 分区的 BCB 写入 `boot-recovery` 请求并重启。
若 recovery 本身不可操作（见 §3.5），它既执行不了清除、也**永远不会清掉 BCB**，
于是每次重启都回到 recovery。`fastboot reboot` 也无法绕过——它走的正是这条流程。

**破解方法：`fastboot erase misc`。** `misc` 是 bootloader 控制块分区，
专用于此类一次性启动命令，不含用户数据、固件或密钥，擦除是标准处置。

### 3.4 `/data` 的加密页脚存放在独立的 `bk1` 分区

Phase 4 boot ramdisk 的 fstab：

```
/dev/block/bootdevice/by-name/userdata /data ext4 nosuid,nodev,barrier=1,noauto_da_alloc,discard
    wait,check,reservedsize=128M,encryptable=/dev/block/bootdevice/by-name/bk1
```

页脚不在 userdata 尾部，而在 `bk1`。只清 userdata 会留下声称「本机已加密」的陈旧页脚，
vold 随即索要密码，解密成功后发现底下是明文文件系统，报「密码正确，但数据已损坏」。

`fastboot erase bk1` 可清除。该分区此前从未被本项目审计，但 fstab 已明确其用途。

### 3.5 MIUI 原厂 recovery 只有经 BCB 进入才有可用 UI

同一份 `4aafc56e…f461e0` 镜像：

- 经 `adb reboot recovery`（写 BCB）进入 → 菜单完整可用，可导航；
- 经 `fastboot boot` 直接启动 → 只画出「MI recovery 3.0 / 主菜单 / 音量键选择，
  电源键进入」的页眉页脚，**菜单项不渲染，音量键无响应**；
- 由系统「重置手机」按钮触发（写 BCB）进入 → UI 正常。

因此 `fastboot boot recovery.img` **不能作为救援手段**。BCB 才是可靠入口。
该 UI 缺陷的具体成因未定位，症状与 MoKee 的显示缺陷同类（按更高分辨率资源绘制、
内容落在可视区外），但两者是否同源未验证。

## 4. 新发现缺陷：Phase 4 配对无法在干净 `/data` 上启动

### 4.1 现象

`system` = `afa12b23…e21eb1`（Phase 4 黄金 sparse），`boot` = `dfca241d…2779685`
（分区内原有，未重写），`/data` = MIUI recovery 刚清空的空 ext4。

重启后停在 MIUI 开机动画，动画持续运行（表明系统进程存活，很可能在 dexopt），
但长时间不进入系统。该阶段 USB 调试默认关闭，**无 adb，无法取 logcat**。

### 4.2 对照

**同一块 `/data`**，换成 exact stock system + stock boot 后正常启动。
因此 `/data`、`bk1`、`misc`、硬件与 bootloader 均可排除，
差异变量只有 **Phase 4 配对本身**。

### 4.3 意义

`docs/reviews/2026-08-26-phase4-first-controlled-write.md` §111 记着
「尚未证明恢复出厂后的 HOME provisioning、Spotify/GMS 重新安装与登录流程」。
本次把该未知项变成了**已确认的阻断级缺陷**：

**第一代 Leo Audio OS 只能在已有 userdata 的设备上运行，无法从出厂状态 provisioning。**

同一份 review §67-68 已经预警过机理方向：

> HOME preference 的行为说明「把 Shell 放入 `/system/app`」不等于替换既有 userdata
> 中的默认桌面选择。后续首次开机/恢复出厂后的 provisioning 必须显式设计，
> 不能依赖人工 ADB 命令。

`docs/13-PHASE-3-GATE3-MINIMAL-SHELL-CONTRACT.md` §72 亦预告：

> 在无既有默认项的干净数据分区上出现 HOME 选择器属于预期风险，
> 必须在未来实机 Gate 明确观察。

两处预警都指向同一区域。但**桌面选择器本身不会阻塞开机动画**，因此当前解释仍不完整。

### 4.4 候选假设（均未验证）

1. `/system/app/LeoShell` 由项目密钥签名，PackageManager 在干净 `/data` 上做全量
   首次扫描时，对该签名或其 HOME 声明的处理与增量扫描不同；
2. Gate 3 写入 LeoShell 时的 Android metadata / SELinux 标签在首次全量扫描下暴露问题；
3. 与 Shell 无关，是 Phase 4 verity system 在首次 dexopt 全量写入下的其他退化；
4. 并非卡死，只是本次等待时长不足——但同一硬件上 stock 明显更快完成，
   该假设优先级最低。

### 4.5 诊断障碍

卡在开机动画时 USB 调试关闭，取不到 logcat。下次复现前需要先准备**可在无 adb
条件下取日志的手段**，例如：

- 用带 `ro.debuggable=1` / `ro.adb.secure=0` 的诊断 boot 做 `fastboot boot`
  （本轮 B3 已验证该手法可行且不写分区）；
- 或在候选 system 中预置 `persist.sys.usb.config=adb`。

不解决取证手段，就只能反复猜测。

## 5. 应补入既有文档的条目

| 目标文档 | 应补内容 |
| --- | --- |
| `docs/18` §7 | 跨 Android 大版本回滚必须同时清 `userdata`（§3.1） |
| `docs/18` §7 | 禁止主机 `fastboot format userdata`（§3.2） |
| `docs/18` §6 | `/data` 故障 → BCB 劫持的识别与 `fastboot erase misc` 处置（§3.3） |
| `docs/14` / `docs/18` | `bk1` 为加密页脚分区，清 `/data` 时必须一并处理（§3.4） |
| `docs/18` §3 | `fastboot boot recovery.img` 不是可靠救援入口（§3.5） |
| `docs/ROADMAP.md` Phase 4 | provisioning 缺陷应作为发布阻断项显式登记 |

本记录不修改上述冻结文档；按项目惯例，冻结点之后的新变化进入新 Gate。

## 6. 尚未闭合

1. Phase 4 provisioning 缺陷的根因与修复；
2. USB-OTG 回滚仍未实测（本次只做了 fastboot 路径）；
3. `bk1` 分区的完整语义未审计——本次擦除依据是 fstab 声明，不是内容分析；
4. 原厂 recovery UI 在非 BCB 路径下残缺的成因未定位；
5. 第二台测试设备的破坏性故障演练仍未开始。
