# leo-hifi-standalone —— Stage 1 验证应用

**这是一个普通应用。**非特权、非平台签名、用一次性 debug key 签，`adb install` 装、`adb uninstall` 卸。
它不写 system 分区、不写 boot 分区、不需要 root。

## 为什么普通应用就够

schema3 的写入路径是 `AudioManager.setParameters()` / `getParameters()`——公开 SDK API，
底层与 `AudioSystem` 同一条 AudioFlinger 路径。AudioFlinger 对该路径的鉴权是
`settingsAllowed()` → `MODIFY_AUDIO_SETTINGS`，本 ROM 实测 `prot=normal`，声明即得。

HAL 侧（`leo_hifi.c` / `leo_hifi.h` / `platform.c:2910-2920`）不做任何调用方身份校验，
闸门纯粹是 session/gen。因此驱动 schema3 不需要任何特权。

**唯一需要特权的是顶部状态栏图标**（`STATUS_BAR`，`prot=signature|privileged`），
那是 Stage 3，不在本应用范围内。

## 构成

| 文件 | 来源 | 移植程度 |
|---|---|---|
| `LeoHifiState.java` | SystemUI 原件 | 逐字，仅改 package |
| `LeoHifiRequestGate.java` | SystemUI 原件 | 逐字，仅改 package |
| `LeoHifiVolumeSelection.java` | SystemUI 原件 | 逐字，仅改 package |
| `LeoHifiController.java` | SystemUI 原件 | 4 处改动，逐条写在类注释里 |
| `LeoHifiTileService.java` | 新写 | 替代 `LeoHifiTile`（`QSTileImpl` 是 SystemUI 内部类） |
| `LeoHifiVolumeActivity.java` | 新写 | 替代 `LeoHifiVolumeDialog`（`SystemUIDialog` 是内部类） |

移植后的三个纯逻辑文件通过原始 host 测试 **40 + 23 + 14 = 77 条断言，0 失败**。

## 构建

```sh
sh build.sh          # aapt2 + javac + d8 + apksigner，全离线，无 Gradle 无网络
# 产物 build/leo-hifi-stage1.apk
```

## 已知前提：当前设备尚未部署 schema3 HAL

设备跑的是原版 `audio.primary.msm8994.so`（`701019bd…`），**不含 leo_hifi 支持**。
因此 Stage 1 只能验证 negative path：`getParameters("leo_hifi_status")` 返回空，
状态落到 `unavailable`，磁贴显示"不可用"。这仍然有价值——它证明 API 可达、解析正确、
UI 状态机在真机上行为正确，且全程零风险。

正向链路必须先部署 HAL，那是 Stage 2，需要 system 分区写入授权。
