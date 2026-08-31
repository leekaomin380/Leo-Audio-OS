# P1 首窗口结果：A 版临时 XML 路由 — 通过

执行时间：2026-08-31 08:27:37 – 08:31（Asia/Shanghai）。执行者：Claude（轮值架构师，
接管编号 `LEO-HO-20260830-223623-CODEX-TO-CLAUDE`）。用户在旁负责播放与听感。

本文件是结果记录，不是任何后续动作的授权。持久化、分区写入、B 版、HAL 替换、
音量变更、44.1 实验均未获授权，本窗口也未执行。

## 1. 窗口时间线

| 时刻 | 动作 | 结果 |
|---|---|---|
| 07:46:53 | `capture --stage baseline` | 原版基线 PASS |
| 08:1x | staging：建目录、推 3 文件、核对哈希 | 通过 |
| 08:27:37 | `arm` | `ARMED: 600s lease`，看门狗 PID 1774，租约至 uptime 129364 |
| 08:27:52 | `enter` | `AUDIO_RESTART 3589 -> 2354`；`CANDIDATE_ACTIVE` |
| 08:28:25 | `capture --stage candidate` | 见 §3 |
| 08:30:05 | `rollback` | `AUDIO_RESTART 2354 -> 6378`；`MACHINE_RESTORED` |
| 08:30:20 | `capture --stage restored` | 见 §4 |
| 08:31 | 用户确认原版声音正常 | 窗口闭合 |

实际占用约 2.5 分钟，远早于计划的第 7 分钟主动恢复与第 10 分钟看门狗兜底。
看门狗 PID 1774 在 `DONE` 写入后自然退出，`watch.log` 全空，无错误路径被触发。

## 2. 原版基线（08:27 之前，evidence/capture-baseline-20260831-074653）

- 播放器 `com.apple.android.music`，`PlaybackState state=3`
- `/proc/asound/card0/pcm0p/sub0`：`RUNNING`、owner_pid 3762、`S16_LE`、48000 Hz、2ch
- hw_ptr `1427520 → 1536000` = 108480 帧；tstamp 差 2.259883 s；108480/48000 = 2.26 s，逐帧吻合
- **活跃路由：`SLIMBUS_0_RX Audio Mixer MultiMedia1 = On`；`QUAT_MI2S_RX` 全关**

最后一条是此前从未取得的正面读数。它证实基线状态下 MM1 完全未经 ESS。

用户使用 Apple Music 而非 FIRST-WINDOW 首选的 Spotify。按「出现其他路径另记，
不强迫切换」处理，如实登记应用身份。

## 3. 候选态（evidence/capture-candidate-20260831-082825）

### 3.1 机器证据（全部通过）

| 项 | 基线 | 候选态 |
|---|---|---|
| 活跃后端 | `SLIMBUS_0_RX MM1 = On` | **`QUAT_MI2S_RX MM1 = On`** |
| `HPHL DAC Switch` | On | **Off** |
| `RX1 MIX1 INP1/2/3` | — | **全 ZERO** |
| `QUAT_MI2S BitWidth` | — | `S24_LE` |
| `QUAT_MI2S SampleRate` | — | `KHZ_48` |
| `QUAT_MI2S_RX Volume` | — | `8192`（最大值，非本轮所改） |
| ES9018 `Volume` | 205 205 | **205 205，全程未动** |

PCM 推进：pcm0p hw_ptr `851520 → 967680` = 116160 帧；tstamp 差 2.419993 s；
116160/48000 = 2.42 s，逐帧吻合。同一 PCM、同一 boot、同一流生命周期。

HAL 日志三行闭合链：

```
select_devices: out_snd_device(7: hifi-headphones) in_snd_device(0: )
enable_snd_device: snd_device(7: hifi-headphones)
enable_audio_route: apply mixer and update path: deep-buffer-playback hifi-headphones
```

`HPHL DAC Switch=Off` 与 `RX1 MIX1 INP*=ZERO` 共同排除了「QUAT 与 SLIMBUS 双通路
同时出声」这一假阳性——这是 Gate 4 明确要求防的误判。

### 3.2 用户主观确认（独立验收项）

| 问题 | 回答 |
|---|---|
| 双声道均有声 | 是 |
| 连续无断续/爆音 | 是 |
| 失真 | 无 |
| 相对原版响度 | **差不多** |

**响度一项不得作因果结论。** ESS `Volume` 全程固定 205，Android 音量未动，
但本窗口未做等响对照，也未使用声压计，为单人单次主观判断。
「差不多」只登记为观察，不能据此推断 WCD 与 ESS 的音质或增益关系。

## 4. 恢复态（evidence/capture-restored-20260831-083020）

| 项 | 终态 | 判定 |
|---|---|---|
| `audio_platform_info.xml` | `8fa54477…e523` | 与基线逐字节一致 |
| `mixer_paths.xml` | `13db0e6e…4bb4` | 与基线逐字节一致 |
| 两目标覆盖挂载 | 0 | 通过 |
| ES9018 `Volume` | 205 205 | 通过 |
| audioserver | PID 6378，`comm`/`exe`/namespace 正确 | 通过 |
| 看门狗 PID 1774 | 自然退出 | 通过 |
| `DONE` | 写入正确 boot_id | 通过 |
| 用户播放原版 | 声音正常 | 通过 |

### 4.1 遗留观察（无害，但证实一条静态结论）

恢复后 `QUAT_MI2S BitWidth=S24_LE`、`SampleRate=KHZ_48` 仍停在实验值，未复位。
这实机证实了 M3 裁决书 §4.5 的静态结论：**QUAT 后端采样率没有 teardown 复位点**。
当前 QUAT 未被任何 usecase 路由，故不影响播放；但它说明「一次 44.1 offload 可能把
控件遗留给后续 deep-buffer 流」这一风险是真实的，M3 控制器进入 HiFi 时必须
显式写入并读回 `KHZ_48/S24_LE`，不能依赖遗留状态。

## 5. 本窗口修复的脚本缺陷

`arm` 于 08:27 之前曾失败一次（07:48），根因与修复见
`../architect-handoffs/LEO-HO-20260830-223623-CODEX-TO-CLAUDE-ACCEPTANCE.md` 异议 1。
本窗口实际执行的脚本 SHA256 = `f999a91e041e7c60976d72ba57604b9858d92a92d7e55a9cb4698b294297f3ab`，
相对 P0 冻结版共三处改动，九个常量（`RUN/BOOT/NS/A/B/HA/HB/CA/CB`）逐行未变：

1. `locked()`：`flock -n 9` → `flock -n 8 8>&9`。mksh 对 `exec N>` 开的 fd 设
   `FD_CLOEXEC`，外部 toybox `flock` 必然 `EBADF`；dup2 到另一 fd 号清除该标志，
   锁仍挂在同一 open file description 上。
2. `probe_lock()`：同上改法，并把判据由 `[ "$?" = 1 ]` 改为哨兵字符串比较。
   原判据无法区分「锁被占用」与「fd 无效」（toybox flock 两者均返回 1），
   探针可能在毫无真锁的情况下假通过。真机验证三情形输出 `OPEN` / `OPENLOCK` / 空串，
   仅 `OPEN` 放行。
3. `watch_alive()`：`deadline` 参与算术前补数值校验，与 `watch()` 已有校验对称。
   真机实测 `deadline="*"` 会使 mksh 直接终止 shell，从而跳过 `enter()` 的 trap，
   可能留下一个已 bind 的 XML 且看门狗同样拒绝回滚。概率极低（root-only 0700 目录），
   修法一行。

第 3 项由 agy J103 发现，第 2 项由 J103 提出诊断但其建议修法经真机证伪（mksh 遇
`exec` 重定向失败立即退出，`|| exit 2` 是死代码），实际修法由本班重写。

## 6. 本窗口证明了什么、没有证明什么

**已证明**：在这一台设备、这一个 boot、这一个应用（Apple Music）、
这一个 usecase（MM1 / deep-buffer）下，纯 XML 改动可把输出路由到 QUAT_MI2S → ESS9018，
WCD 模拟输出级完全关闭，指针连续推进，用户确认双声道连续无失真，且可完整恢复。

**未证明**（不得由本窗口推导）：

- 第二个应用、耳机插拔、焦点切换、待机恢复、通知音/并发流、重启后行为
- 真实 compress-offload（MM7）——本窗口全程 MM1，A 版新增的 offload2 hifi 路径未被触发
- 音质优于或等于 WCD——无等响对照、无声压计、单人单次
- 205 对任意耳机安全——它只是当前对照基线
- 持久化可行性——`mount --bind` 重启即失效，持久化需分区写入且未获授权
