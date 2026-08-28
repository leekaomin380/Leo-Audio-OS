# Phase 5B M2：写入前硬门预检记录

日期：2026-08-28
范围：`docs/18-PHASE-5B-M2-UNMODIFIED-MOKEE-BASELINE-RUNBOOK.md` §4 十条硬门
结果：**①②③④⑤⑥⑦⑧ 全部关闭；⑨⑩ 待用户临场确认。本轮零分区写入。**

## 0. 裁定

M2 的全部技术门已闭合。设备身份、几何、固件基线、恢复入口和双介质回滚材料
均由本轮实测证据支撑，不引用历史记录。仍未授权任何分区写入。

## 1. 门 ①：双模式同一设备

| 模式 | 证据 |
| --- | --- |
| Android | `adb devices -l` → `product:leo  model:MI_NOTE_Pro  device:leo`，序列号不记入公开记录 |
| fastboot | `fastboot devices` 与 `getvar serialno` 返回同一序列号，与 Android 侧一致 |

两次独立进入 fastboot（B1 与 B3 前）序列号一致。

## 2. 门 ②：解锁、电量、枚举

- `ro.secureboot.lockstate=unlocked`，`ro.boot.verifiedbootstate=orange`
- 电量 99→100%，4345 mV，32.0–32.5 °C，USB 供电
- bootloader `LA.BF64.1.2.3-01210-8x94.0-391-g45ea85c`，`variant:MTP eMMC`，`soc_id:207`

fastboot 侧不暴露 unlock 变量（仅 `secure:yes` / `sec_boot:TRUE`，指硬件熔丝）。
解锁证据取自 Android 侧属性与 Phase 4 实际写入成功的历史事实。

**未闭合的连接风险**：设备经由 USB 2.1 hub 连接，与外置介质共用总线。
`max-download-size=0x20000000`（512 MiB），MoKee 候选 sparse 1,564,010,920 B
需要 **3 轮独立 download+flash**。写入前应将外置介质从 hub 移除。

## 3. 门 ③：分区几何

```
partition-size:system    0x68000000  = 1,744,830,464 B   与冻结基线精确匹配
partition-size:userdata  0xdef7fbe00 =    59,852,701,184 B (55.74 GiB)
partition-size:cache     0x18000000  =       402,653,184 B
```

`boot`/`recovery`/`persist`/`modem`/`tz`/`aboot` 的 `partition-size` 本机 aboot
一律返回空。boot 几何无法从 fastboot 读取，记为残余项；影响有限（boot 镜像
23.9 MB，且 Phase 4 已成功写入一次）。

## 4. 门 ④：TrustZone 基线

MoKee updater 的断言为硬失败：

```
ifelse(!(msm8994.verify_trustzone("TZ.BF.3.0.R1-00226") == "1"),
  ui_print("!!!!! Wrong base firmware !!!!!"), abort())
```

M2 走 fastboot 离线路径绕过该检查，因此自行验证。读取路径为 Qualcomm socinfo
的 SMEM 镜像版本表 `/sys/devices/soc0/{select_image,image_crm_version,
image_variant,image_version}`；`select_image` 为 `root` 所有，需 root 写入。

实测完整固件表：

| idx | 镜像 | 版本 |
| ---: | --- | --- |
| 0 | SBL | `BOOT.BF.2.3.1-00079` |
| 1 | **TZ** | **`TZ.BF.3.0.R1-00226`** |
| 3 | RPM | `RPM.BF.1.4-00230` |
| 10 | APPS | `10:NRD90M:V9.2.3.0.NXHCNEK`（`leo-user`, `REL`） |
| 11 | MPSS | `MPSS.BO.2.6.C1.2-00040` |
| 12 | ADSP | `ADSP.BF.2.6-00518` |
| 14 | VIDEO | `VIDEO.VE.1.8-00144` |

**索引 1 与 MoKee 要求精确匹配，门 ④ 关闭。**
索引 11 与 Android 侧 `gsm.version.baseband=BO.2.6.c1.2-0905_1948_606b74a` 一致。
索引 12 的 ADSP 版本是 Phase 5B/5C 音频工作的新增基线证据。

读取后 `select_image` 已复位为 10。该 sysfs 仅选择 SMEM 表返回行，不触碰硬件、
不写存储、断电失效。

## 5. 门 ⑤：stock recovery

主菜单实测：`重启手机` / `清除数据` / `连接小米助手`，音量键选择、电源键确认。
导航实测有效。**返回 fastboot 走的是硬件路径**（长按电源关机 → 音量下+电源），
不依赖 Android——这正是 Android 不可用时的紧急路径。测试全程未选择清除数据。

MIUI 原厂 recovery 主菜单不启动 adbd，`adb`/`fastboot` 均无枚举，属预期行为。

## 6. 门 ⑥：本机回滚材料完整性

七份产物全量哈希，与冻结 manifest 逐字节一致；双构建 run-a / run-b 互相一致：

| 产物 | SHA-256 |
| --- | --- |
| golden system sparse (a=b) | `afa12b23e4570f96cc5e4ee70cf754779c75cf834a9d61f481f08d1a96e21eb1` |
| golden project boot (a=b) | `dfca241d75d494e0d85502d1368a3475f0e2576dd69b28274fcf4532a2779685` |
| stock system sparse | `03960aeded4f6b3c7802109ff74aedec67c5de15841bf175ace66a89cde36003` |
| stock boot | `bc64d15c26c53644e0d66e8dd3dc9e9c52bf2d4e4267d3c9f71ee90455e567d5` |
| stock recovery | `4aafc56e0feb5be5213a58e9bc770730d9cf3746a9b4ee31bc79d6484af461e0` |

完整 `verify-phase4-release-set.py` 未能运行：其必需参数 `--gate3-ext4`
（1,717,571,584 B）与 `--development-boot-fallback` 已随空间清理迁至文件服务器，
本机不存在。记为残余项。

## 7. 门 ⑦：主机之外的回滚副本

按 `docs/18` §7 的两层顺序打包最小回滚集（2.59 GiB，5 个产物），落到两处独立
介质，各自独立回读：

| 副本 | 介质 | 工具 | 结果 |
| --- | --- | --- | --- |
| 工程主机 | 内置 NVMe | `shasum -a 256` | 5/5 通过 |
| 本地 Debian 文件服务器 | 独立机器 NVMe | `sha256sum -c` | 5/5 通过 |
| 外置卷 B | 独立物理盘（卷名与 UUID 记于私有证据） | `shasum -a 256 -c` | 5/5 通过 |

公开绑定：`manifests/m2-rollback-set-v1.json`。依 `docs/reviews/2026-08-26-phase4-first-controlled-write.md`
的既定规则，公开记录不保存设备序列号、介质 UUID 或卷名。

**同时确认两块 Phase 4 保管盘均在线且回读通过**：`current-system.partition.raw`
在 primary 与 secondary 两块盘（卷名与 UUID 记于私有证据）
上均读回 `f54d6199e5becb90a8d9c7187bc1b675d28ab82244aa2c0e18cb9cff84778482`。
该备份为 Phase 4 写入前的 MIUI system，**只含 system 不含 boot**，不构成 M2 的
可用回滚层，故另行建立上述最小回滚集。

## 8. 门 ⑧：Spotify 只读导出

`/data/app` 为 0771，`adb pull` 不可用，改用 `adb exec-out cat` 流式导出。
四份 APK 落地大小与设备端完全一致：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| base.apk | 39,711,638 | `448ba8e6716dc8c55b0234f4dbc551adaa7992c1aabddf19aa790917cd37fce6` |
| split_config.arm64_v8a.apk | 26,182,810 | `5193cbc0c57bc96005d3e0d3700f8104c6712dc8c4b3ccabd30206f83273f555` |
| split_config.xhdpi.apk | 399,087 | `46a13d7801ab060af441a9cedb9601a73bdd20933ef360acbbf47910bab5a087` |
| split_config.zh.apk | 1,622,425 | `33d1352ae6edc38632d0d492b51ccb88283fd779d5a174b0a9f67ea8b1e431af` |

版本 `9.1.50.1906` / versionCode `141833246`。未导出登录态，未复制账号数据库。

## 9. B3：临时诊断启动的镜像审计与执行

### 9.1 来源链

`development_boot_fallback`（已登记于 `manifests/phase4-release-set-v1.json`）
实为第一代实践期的 Magisk 补丁 boot：

```
magisk_patched-30700_h2FHv.img
24,384,810 B   SHA-256 1d3f7a3792e4eb704ee5a8f947e762d6a5b7076a2bdd3e36499188d068cc708f
```

其 `.backup/.magisk` 声明 `SHA1=0500908e29ad2007922f177ded1148422c009f5e`，
与本机 exact stock `boot.img` 的 SHA1 **精确匹配**。来源链闭合。

### 9.2 与 stock 的完整差异

kernel section（`86e4e2af…`）、36 份 DTB、cmdline 三份 boot 完全一致。
ramdisk 内差异穷尽为三处：

1. `fstab.qcom`：`/system` 行 `ro,barrier=1 wait,verify` → `ro,barrier=1 wait`；
2. `init` 替换为 magiskinit（199,960 B），原件备份；
3. `verity_key` 删除，原件备份。

新增 `.backup/`（三个原件的 xz 备份，解压后与 stock 逐字节一致）与
`overlay.d/sbin/{magisk,init-ld,stub}.xz`。`default.prop` 与 stock 完全相同。
`.magisk` 配置：`KEEPVERITY=false`、`KEEPFORCEENCRYPT=false`、`PREINITDEVICE=userdata`。

对照：Phase 4 project boot 的 `fstab.qcom` 与 stock **无差异**，只替换了
`verity_key` 内容为项目 key `3cf27ca96948c44721e34eb5732c992a073cdda71ae20df4a5c6065a9c6454b3`。

### 9.3 为何不自造诊断 ramdisk

自造方案（改 `default.prop` 的 `ro.secure`/`ro.debuggable`）只能取得 root uid。
目标 `/sys/devices/soc0/select_image` 的写入还需通过 MIUI 的 Enforcing sepolicy，
而 adb shell 位于 `shell` 域。Android 7 `user` 构建的 init 忽略
`androidboot.selinux=permissive`（该开关仅对 userdebug/eng 编译生效），改 cmdline 无效。
绕过需要自行补 sepolicy，等同于重新实现 magiskpolicy。**故采用已验证工具而非自研实现。**

### 9.4 执行与实测

```
fastboot boot magisk_patched-30700_h2FHv.img   → Sending OKAY / Booting OKAY
```

临时启动期间实测：

- `/system` 从 `/dev/block/bootdevice/by-name/system` 裸块设备挂载（**非 `dm-0`**），
  验证了 fstab 分析：dm-verity 被绕过，Phase 4 的 ext4 正常挂载，尾部 verity/FEC 数据
  位于文件系统范围外被忽略；
- `getenforce` 仍为 `Enforcing`，但 `su -c id` 返回 `uid=0 context=u:r:magisk:s0`，
  即 magiskinit 注入的无约束域——验证了 9.3 的推断；
- `su` 无需交互授权即放行，因 `com.topjohnwu.magisk` 与 `/data/adb` 为第一代残留
  且被 Phase 4 保留（Phase 4 只写 system/boot）。

### 9.5 恢复验证

`adb reboot` 后回到持久 project boot：

```
/dev/block/dm-0 on /system type ext4 (ro,seclabel,relatime,data=ordered)   verity 恢复
/sbin/su: Permission denied ; su: not found                                root 消失
getenforce=Enforcing  ro.secure=1  ro.debuggable=0  verifiedbootstate=orange
```

**本轮全程零分区写入。** `fastboot boot` 仅将镜像送入 RAM 执行。

### 9.6 残留

Magisk 在临时启动期间可能写入 `/data/adb/`。该目录与 Magisk 应用本就存在于
`/data`（第一代残留），非本轮新增污染。M2 将清除 `/data`。
`/data/adb/modules/` 内容未能读取，第一代模块若自动加载，其影响限于临时启动期间
且 `/system` 为只读。

## 10. 附带取得的证据

- Phase 4 配对在两次 fastboot 往返与一次临时启动后完成 **3 次完整冷启动**，
  每次 `/system` 均以 `dm-0` 只读挂载、verity 生效。为 `docs/ROADMAP.md`
  Phase 4「重复冷启动」提供数据点，但样本量仍不足以宣告该项完成。
- 设备上并存三个 Leo Shell 包：`/system/app` 的正式 `io.github.leoaudio.shell`，
  以及 `/data/app` 中 Phase 2 遗留的 `.debug` 与 `.preview.debug`。M2 清除 `/data`
  后仅余正式包。
- `ro.crypto.state=unencrypted`；`/data` 55.74 GiB 中已用 15 GiB。

## 11. 尚未闭合

1. 门 ⑨⑩：用户知悉清除 userdata、以及对第一次破坏性动作的临场确认；
2. USB 连接经 hub，写入前须移除外置介质并接受 3 轮分块传输的风险；
3. `boot`/`recovery` 分区几何无法从本机 aboot 读取；
4. 完整 `verify-phase4-release-set.py` 因两个输入已离机而未运行；
5. 本记录不构成写入授权。`manifests/mokee-m2-baseline-candidate-v0.1.json` 的
   `device_write_authorized` 保持 `false`。
