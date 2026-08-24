# 初始系统架构

## 总体选择

工程采用两条相互验证的路线。

### A. MIUI 衍生的原型线

用户提供精确匹配的官方 MIUI ROM，构建器保留原厂音频组件及二进制依赖，在镜像
构建阶段移除无关应用和服务，并加入专用 Shell、维护入口与恢复保险。

这条路线用于最快建立第一份专用固件，并作为声音和兼容性的黄金参考。

### B. 源码构建的正式线

从匹配 MSM8994 的 Android/AOSP 基础开始，集成公开 ESS9018 内核驱动、Qualcomm
音频栈，以及用户从官方 ROM 提取的音频 HAL、校准和固件。所有通用手机功能从产品
配置阶段排除。

只有当 B 线通过与 A 线相同的音频、功耗和恢复验收，才能成为正式第二代版本。

## 运行时分层

```text
Leo Player Shell / Maintenance UI
                 |
              Spotify
                 |
       AudioTrack / AudioFlinger
                 |
   AudioPolicy / Qualcomm Audio HAL
                 |
        Qualcomm ADSP / ACDB
                 |
        QUAT MI2S / ESS9018
                 |
          OPA1612 / Headphones
```

## 必须保留

- Linux 内核的 MSM8994 电源、热管理、Wi-Fi 和存储驱动；
- ESS9018 codec 与 QUAT MI2S machine driver；
- Android init、Zygote、System Server、SurfaceFlinger；
- AudioFlinger、AudioPolicy、MediaCodec 和必要 DSP 服务；
- Wi-Fi、DNS、TLS、证书、账号与密钥服务；
- 最小存储、下载、包管理和更新能力；
- 可启动、可验证、可恢复的 recovery 路径。

## 默认排除

- 电话、短信、联系人和拨号框架；
- 相机、图库和录音；
- MIUI 商店、浏览器、主题、安全中心和小米账号；
- 普通 Launcher、应用抽屉、壁纸和小组件；
- NFC、红外、打印及非必要传感器服务；
- 第三方音效、全局均衡和未经测量的“音质增强”；
- 面向普通用户的 Root 与常开 ADB。

## 第三方组件边界

Spotify、GMS 和 Xiaomi 专有文件不是本项目的可再分发组成部分。构建器只接受设备
所有者提供的原始文件，核对预先登记的版本、签名和 SHA-256，再在本地生成个人固件。

项目自己的 Shell、维护应用、系统组件和 OTA 使用独立 release keys。项目不需要、
也不试图获取 Xiaomi 的私钥。

## 回滚限制

`leo` 是非 A/B 设备，不能天然提供现代设备的双槽无缝回滚。首期目标是：

- 在写入前保存 boot、system、recovery 和关键分区校验信息；
- 使用可临时启动的恢复环境验证备份与还原；
- 通过启动计数进入安全模式或 recovery；
- 为每个发布版本生成签名的已知良好恢复材料。

在没有第二台测试机和恢复验收前，不把自动整机回滚描述为已实现能力，也不通过危险
重分区伪造 A/B 结构。
