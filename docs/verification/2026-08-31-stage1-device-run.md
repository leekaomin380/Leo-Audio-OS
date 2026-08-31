# Stage 1 真机验证记录 —— 2026-08-31 13:40–13:44

设备 `68f5f468`（`mokee_leo`，MK100.0-leo-221019-RELEASE，Android 10 / SDK 29，msm8994）。
授权范围：`adb install` 独立验证应用 + 临时加 QS 磁贴 + 截图 + 还原卸载。

## 开工基线

```
boot_id     = 245a2267-e200-4484-81f8-1b0b7ba2f0e1
audioserver = 6378
hal_svc     = 6379
hal_sha     = 701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47
volume      = Volume: 205 205 (dsrange 0->255)
sysui_qs_tiles = wifi,bt,dnd,flashlight,rotation,battery,cell,airplane,screenshot
```

## 实测结果

| 检查项 | 结果 |
|---|---|
| 安装 | `Success`；uid 10129；`/data/app/com.leoaudio.hifi-z7_Lne-VAdWcgcOXBDOehw==` |
| 权限 | `MODIFY_AUDIO_SETTINGS: granted=true` —— 普通权限自动授予，**无需任何特权** |
| 进程 | pid 6971 正常启动；无 crash，logcat 无 `AndroidRuntime` 异常 |
| 磁贴注册 | `pm query-services -a android.service.quicksettings.action.QS_TILE` 命中，`enabled=true exported=true` |
| 磁贴渲染 | 显示 `HIFI` / 副标题「后端不可用」/ 置灰 —— `STATE_UNAVAILABLE` + `leo_hifi_unavailable` |
| 音量界面 | 标题、警告文案、状态「通过 HiFi 播放后可调节」、回读 `0 / 0`、滑块与 Apply **双双置灰** |

## Negative path 判定

设备运行的是**未打补丁的 HAL**（`701019bd…`，无 `leo_hifi` 支持），因此：

`AudioManager.getParameters("leo_hifi_status")` 返回空 → `LeoHifiState.parse()` 落 `unavailable`
→ `LeoHifiRequestGate.canStart()` 全程不放行 → `halWrite()` **一次都没有被调用**
→ UI 两个控制面（磁贴、音量对话框）均正确锁死。

这与主机 mock 的行为一致，且是无 HAL 时唯一正确的行为。

## 本次证明与未证明

**已证明**
- `AudioManager` 公开 API 路径在真机可达；普通应用即可持有 `MODIFY_AUDIO_SETTINGS`
- `LeoHifiState.parse()` 对空响应的处理与主机 mock 一致
- UI 状态机在真机行为正确，不可用态锁死生效
- `TileService` 被系统识别并正确渲染
- 全流程零设备状态变更

**未证明**
- schema3 正向链路（开关真正生效、音量真正写入、状态栏点亮）。需先部署 HAL，即 Stage 2。

## 收尾核验

```
sysui_qs_tiles 写回原值        逐字符一致 ✅
pm uninstall                  Success；pm path 空；/data/app 与 /data/data 均无残留 ✅
audioserver / hal_svc / hal_sha / volume / boot_id   与开工基线逐字符一致 ✅
```

设备完全回到 Stage 1 开始前的状态。`NO_GO_DEVICE` 维持不变；205 音量基线未动。

截图与原始输出存于本地 `Leo-Audio-OS-snapshots/20260831-stage1-evidence/`，
未纳入本仓库——远端为公开仓库，截图含桌面应用列表等无关个人信息。
