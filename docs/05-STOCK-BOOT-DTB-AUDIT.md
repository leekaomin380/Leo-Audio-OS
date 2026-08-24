# 05：Stock boot、实机与官方源码三方审计

## 结论

已对 MIUI `V9.2.3.0.NXHCNEK` 原厂 `boot.img`、当前参考机和 Xiaomi 公开内核
`libra-n-oss@f4cab50d74f8e55e0a0dbbf430d163f46c6fc3a1` 完成第一轮三方对照。

目前可以高置信度确认：

1. 参考机实际匹配 boot 内索引 25（第 26 份）DTB：MSM8994 v2.1 MTP，
   PM8994 + PMI8994，无 PM8004；
2. 该 stock DTB 与官方源码重建 DTB 的音频相关语义一致；
3. 参考机硬件版本是 3.2，不走 ES9018 驱动的 2.2 特殊常供电分支；
4. stock kernel 二进制中实际包含 ES9018、QUAT_MI2S 和对应机器驱动的符号与
   日志字符串；
5. stock ramdisk 明确启动 ADSP、`audiod`、`adsprpcd`、`rfs_access` 并建立音频
   数据目录和设备节点权限。

这些证据把“公开内核看起来像参考机”提升为了“实机硬件选择和 stock DTB
已与官方源码对上”。但它还不是 stock kernel 的逐字节可重现编译证明。

## 1. 原厂 boot 封存与结构

输入来自已封存的原厂 Fastboot ROM，不来自当前 Magisk 修改后的运行分区。
原始镜像和解包结果只保存在被 Git 忽略的 `resources/private/`。

| 对象 | 大小 | SHA-256 |
| --- | ---: | --- |
| `boot.img` | 24,188,234 | `bc64d15c26c53644e0d66e8dd3dc9e9c52bf2d4e4267d3c9f71ee90455e567d5` |
| kernel section | 22,004,895 | `86e4e2af5441c95992219eb556ec839bfb7ce4aad8f34dc1bea9fcf99dcf0976` |
| gzip kernel payload | 9,826,811 | `0478496915b5a216d85f1b700f0a069421d7fc6b0f802da87068c6bc148ffa03` |
| 解压 ARM64 kernel Image | 28,600,680 | `16eabe299644db7baaa440c3382dcca723b29024632f1676ec3cd591419d3000` |
| gzip ramdisk | 2,174,218 | `5161939c101e4cdabfb87f27d5e3e48bb26d3a3985f64b5acb8c953a5d87b1d9` |

boot header 使用 4096 字节页，头部 `dt_size=0`，但 kernel section 末尾串联了 36 份
DTB。项目工具 [`scripts/unpack-android-boot.py`](../scripts/unpack-android-boot.py) 会验证每个区段
的边界，只接受能精确填满 kernel section 尾部的 DTB 链。

内核版本字符串为：

```text
Linux version 3.10.84-gfcc38b5-04628-gf2509a2
#1 SMP PREEMPT Thu Dec 28 23:35:42 CST 2017
gcc 4.9 20150123 prerelease
```

二进制中可找到 `es9018_i2c_probe`、`es9018_hw_params`、
`es9018_set_bias_on/off`、`msm8994_quat_mi2s_snd_startup/shutdown`、
`msm_be_quat_mi2s_hw_params_fixup`、`es9018.6-0048` 和 `QUAT_MI2S BitWidth`。
这证明所审计驱动实际编入 stock kernel，但单凭符号不能证明函数体逐字节相同。

## 2. 确定实际 DTB

只读实机值：

| 维度 | 实机 | DTB 索引 25 |
| --- | --- | --- |
| SoC | `soc_id=207`, `revision=2.1` | `qcom,msm-id=<0xcf 0x20001>` |
| 平台 | `hw_platform=MTP` | `qcom,board-id=<0x8 0x0>` |
| PMIC | PM8994 + PMI8994，无 PM8004 | `qcom,pmic-id=<0x10009 0x1000a 0 0>` |
| 模型 | Mi Note Pro / `leo` | `Qualcomm Technologies, Inc. MSM8994v2.1 MTP` |

四个维度同时唯一匹配索引 25，其 SHA-256 为：

```text
cee146b6093e34d2997ca21314cd25d9a7d321429b695dff6a6bae70ad178d5e
```

索引 30 虽然同为 MSM8994 v2.1 MTP，但它额外声明 PM8004；实机没有该 PMIC，
因此可排除。

## 3. Stock DTB 与官方源码比较

从官方提交预处理并重建 `arch/arm/boot/dts/qcom/msm8994-v2.1-mtp.dts`，
再将重建 DTB 和 stock 索引 25 DTB 用同一版 `dtc` 反编译、标准化排序后比较。

二进制哈希不同，这是预期的：原厂 DTB 还包含 5 条屏幕面板编号属性：

- JDI FBC20：`qcom,mdss-dsi-panel-id=<2>`；
- JDI WQHD 两个面板节点：`panel-id=<4>`；
- Sharp WQHD 两个面板节点：`panel-id=<5>`。

标准化 DTS 的完整差异只有上述 5 行，没有任何音频节点差异。因此官方源码中
ES9018 的 I²C 地址、五路 regulator、双晶振、reset/mute/switch/OPA GPIO 和 QUAT_MI2S
引脚定义，与参考机使用的 stock DTB 语义一致。

## 4. 硬件版本解码与 OPA 分支

实机读得：

```text
/sys/bootinfo/hw_version = 0x132
ro.boot.hwversion = 1.3.2
```

官方 `bootinfo.h` 将其解码为：

```text
device = (0x132 & 0xF00) >> 8 = 1
major  = (0x132 & 0x0F0) >> 4 = 3
minor  = (0x132 & 0x00F)      = 2
```

ES9018 驱动只在 `major==2 && minor==2` 时：

- probe 时提前打开五路电源，常规 bias off 不关闭；
- 解析并请求 `ess,opa-gpio`；
- startup 跳过驱动末尾的 unmute。

参考机是 3.2，因此走正常的按播放上下电分支：五路 regulator 在 bias on 打开、
在 bias off 关闭。该机上 `opa_gpio` 不会被驱动请求，所以 `es9018_opa()` 调用是
no-op。这不否定硬件上的 OPA1612 模拟级；它只说明参考修订不使用这根 GPIO
动态控制 OPA。

## 5. Ramdisk 提供的音频启动闭包

stock ramdisk 提供了不能只靠复制 HAL 补齐的启动条件：

- `init.qcom.rc` 在 early boot 写入 `/sys/kernel/boot_adsp/boot=1`；
- `init.target.rc` 启动 `adsprpcd`（`media:media`）和 `audiod`（`system:system`）；
- `init.qcom.rc` / `init.target.rc` 启动 root 权限的 `rfs_access`；
- 创建 `/data/misc/audio`、ACDB delta、`/data/audio` 和 `/data/misc/dts` 目录，并设置
  `audio` / `media` 用户组；
- `ueventd.qcom.rc` 为 `/dev/adsprpc-smd`、`/dev/msm_audio_cal`、`/dev/msm_hweffects`、
  `/dev/msm_rtac`、`/dev/avtimer` 等节点设置所有者和权限；
- `ueventd.rc` 将 `/dev/snd/*` 交给 `system:audio`；
- Binder service contexts 为 `audio`、`media.audio_flinger`、`media.audio_policy`、
  `media.sound_trigger_hw` 等服务标注音频域。

这一层已建立“服务名—可执行文件—用户组—设备节点—数据目录”的静态骨架。
后续已经完成编译 SELinux policy 的首轮有效授权映射，见
[`07-STOCK-SELINUX-AUDIO-CLOSURE.md`](07-STOCK-SELINUX-AUDIO-CLOSURE.md)。

## 6. 低功耗直接线索

stock boot 命令行含：

```text
lpm_levels.sleep_disabled=1 boot_cpus=0-5
```

`lpm_levels.sleep_disabled=1` 要求内核在早期启动时先禁用低功耗层级，但不能由此
推断完成启动后仍一直禁用。当前实机运行值为：

```text
/sys/module/lpm_levels/parameters/sleep_disabled = N
CPU0 C1 retention usage = 157109
CPU0 C3 pc usage = 396989
A53/A57 CPU pc, L2 pc and system CCI pc idle_enabled = Y
```

因此参考机当前确实在使用 CPU power collapse，“深度休眠始终被禁用”已被实机
反证。stock ramdisk 在 charger action 中明确会写 `sleep_disabled=0`，但本次还没有
完整定位正常启动中将它恢复为 `N` 的执行者。所以该参数是需要重现时处理的
早期启动时序，不是当前空闲功耗问题的已证实根因。

`boot_cpus=0-5` 限制初始启动 CPU 集；实机的 `possible` / `present` 均为 `0-7`，
当次采集时 `online=0-4,6`，证明内核运行期仍管理全部 8 核并动态热插拔，不是
全程只能使用 6 核。

## 7. 证据边界与下一步

本次仍未证明：

- 公开提交就是 kernel 版本字符串中的 `f2509a2`；
- 可用同一 defconfig、编译器、链接器和时间戳复现 stock kernel 哈希；
- 运行内核的完整 `.config`；实机不存在 `/proc/config.gz`，kernel 也没有 IKCONFIG；
- 3.2 硬件上 OPA1612 的实际供电波形和 regulator 空闲漏电；
- 原厂 SELinux 源 `.te`、宏与 build-time `neverallow` 的精确来源；二进制有效授权闭包
  v0.1 已完成，但仍不是经功能测试证明的最小权限集。

已对锁定的社区 `mkr-mr1` 分支完整提交图进行本地检索。该历史含 444,790 个
祖先提交，且官方 `f4cab50d` 是锁定社区提交 `17a5b888` 的祖先；但历史中
不存在 `f2509a2` 或 `fcc38b5` 对应的 commit object。因此这个社区树可用于官方
基线之后的演进审计，不能填补 stock kernel 的精确私有源码提交。

下一轮应先重建运行内核配置，解析编译 sepolicy 和属性触发，再做播放/待机
regulator、CPU idle 与温度实测。在这些工作前，不对参考机写入新 boot。
