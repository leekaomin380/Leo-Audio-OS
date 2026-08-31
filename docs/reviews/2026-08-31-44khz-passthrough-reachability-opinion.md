# 44.1 kHz 直通可达性：静态裁决与架构师意见

日期：2026-08-31（Asia/Shanghai）
轮值架构师：Claude（接管编号 `LEO-HO-20260830-223623-CODEX-TO-CLAUDE`）
性质：**证据 + 意见**。用户已明确指示**暂不修改** `docs/ROADMAP.md` Phase 5B 的
44.1 kHz 目标措辞，本文件仅记录意见与理由备查，不构成路线图变更。

## 1. 结论

在当前 MoKee Android 10 + msm8994 HAL 架构下，普通 Android 应用（如 Apple Music）
播放 44.1 kHz 内容时，**没有任何配置层可达的路径能获得未经 AudioFlinger 重采样的
44.1 kHz 输出**。

裁决为 **(b) 不可行 —— 且不可行的原因在 HAL 源码，不在配置**。

## 2. 证据链

证据来源：本地 `build-private/sources/mokee-qcom-audio-msm8994/hal/`，
`research-cache/m3-api-work/configs/msm8994/`。全部结论均可用下列命令复现。

### 2.1 策略层确实声明了 44100

`audio_policy_configuration.xml` 中 `primary`、`deep_buffer`、`direct_pcm`、
`compressed_offload` 四个 output profile 均在 `samplingRates` 中声明了 `44100`。
`direct_pcm` 更声明了 8000–192000 的完整速率族并带 `AUDIO_OUTPUT_FLAG_DIRECT`。

**这正是最容易误导的地方**：策略层声明 ≠ HAL 会按该速率开流。

### 2.2 HAL 的直通分支要求一个不可达的 flag

`hal/audio_hw.c:3105-3106`：

```c
} else if ((out->flags & AUDIO_OUTPUT_FLAG_COMPRESS_OFFLOAD) ||
           (out->flags & AUDIO_OUTPUT_FLAG_DIRECT_PCM)) {
```

AudioPolicy 对 `direct_pcm` profile 只传 `AUDIO_OUTPUT_FLAG_DIRECT`（0x1），
而这里要求的是 `AUDIO_OUTPUT_FLAG_DIRECT_PCM`（0x2000）。条件不成立。

### 2.3 落入 fallback 后采样率被强制写死

`hal/audio_hw.c:3295-3300`：

```c
} else {
    /* primary path is the default path selected if no other outputs are available/suitable */
    format = AUDIO_FORMAT_PCM_16_BIT;
    out->usecase = USECASE_AUDIO_PLAYBACK_PRIMARY;
    out->config = PCM_CONFIG_AUDIO_PLAYBACK_PRIMARY;
    out->sample_rate = out->config.rate;
```

`out->sample_rate` 直接取自预设 config 的 `.rate`（48000），
应用请求的 44100 在此被丢弃。

### 2.4 该 flag 无法由配置注入

`hal/audio_extn/utils.c` 的 `s_flag_name_to_enum_table` 共收录 9 个 flag：

```
COMPRESS_OFFLOAD  COMPRESS_PASSTHROUGH  DEEP_BUFFER  DIRECT
FAST  HW_AV_SYNC  INCALL_MUSIC  NON_BLOCKING  PRIMARY
```

**不含 `DIRECT_PCM`。** 在 `audio_output_policy.conf` 里写 `AUDIO_OUTPUT_FLAG_DIRECT_PCM`
会被解析器当作未知 flag 丢弃。

### 2.5 最强的一条：该 flag 在整个 HAL 源码树中是死符号

```
$ grep -rn "AUDIO_OUTPUT_FLAG_DIRECT_PCM" hal/
hal/audio_hw.c:3106:               (out->flags & AUDIO_OUTPUT_FLAG_DIRECT_PCM)) {
```

**全树仅出现 1 次，就是那个判断本身。** 没有任何代码路径会置位它。
这不是「难以触发」，是**结构上不可触发**。

（本条为本班在复核 agy J104 交付时补充，J104 原报告未做全树检索。）

## 3. 架构师意见

### 3.1 对现有 ROADMAP 措辞的意见

Phase 5B 末条现写：

> 建立采样率策略：对 44.1 kHz 家族**优先验证端到端 44.1 kHz 输出**，消除当前
> `44.1 → 48 kHz` 的非必要 SRC；对无法直通的混音、系统音或 48 kHz 内容明确记录
> SRC 原因与实际输出率，不作「全局 bit-perfect」承诺。

我认为「优先验证端到端 44.1 kHz 输出」这一措辞，在当前证据下会**误导后续执行者
去做配置层实验**，而配置层已被证明是死路。更贴合证据的表述应是：

> 44.1 kHz 直通在当前 HAL 下无应用可达入口（`AUDIO_OUTPUT_FLAG_DIRECT_PCM` 为死符号）。
> 若要追求端到端 44.1，前置条件是修改 HAL 的 flag 处理与 `out->sample_rate` 赋值逻辑，
> 属源码改动而非配置改动，应作为独立里程碑单独立项与授权。
> 在此之前，交付目标为可解释、可报告的 SRC，不作 bit-perfect 承诺。

**用户已裁定暂不修改，本意见仅备查。** 本文件在 ROADMAP 该条目下留有指针。

### 3.2 为什么这条意见值得记录而不是等到改时再说

三个理由：

1. **防止重复劳动。** 项目已有一次「Apple Music 走 offload」的判断被撤回（实为
   `checkOutputsForDevice()` 的 profile 探测）。策略层声明 44100 是同一类陷阱：
   看起来支持，实际不可达。不记录，下一轮很可能再花一次成本重新发现。

2. **盲改有实际危害，不只是无效。** 若继续在 XML/conf 里声明 44.1：
   - 好的情况：HAL 仍按 48000 返回，AudioFlinger 察觉后重新插入重采样器，
     SRC 原地不动，纯浪费；
   - 坏的情况：若某处 hack 或 APM 漏洞让 AudioFlinger 误以为底层真接受了 44100，
     而 ALSA 流实际开在 48000，则前后端速率错配，出现变调（「花栗鼠音」）与断流爆音。
   第二种情况会在用户耳边发生，且发生在一个已获授权的实验窗口里。

3. **它改变 M3.5 的性质。** M3 裁决书已把 SRC 列为 M3.5 独立里程碑，并写明
   「若答案为否，M3.5 的 44.1 直通可能没有应用可达入口，应明确判不可行，
   而不是继续盲改」。本文件就是那个「否」的答案。M3.5 因此从「验证性任务」
   变成「HAL 源码改造任务」，工作量与授权级别都不同。

### 3.3 一条不得混淆的区分

「硬件支持 44.1 kHz 时钟家族」与「应用可达 44.1 kHz 输出」是两件事。
本文件只否定后者，不否定前者。ES9018/QUAT_MI2S 的时钟能力未在本文件范围内。

## 4. 未闭合项

- 本裁决基于**静态源码与配置**，未做实机 DIRECT 流实验（也无必要——flag 不可达，
  实验无法构造）。
- AudioPolicyManager 侧（frameworks/av）的源码不在本机，因此「APM 只传 DIRECT
  不传 DIRECT_PCM」这一环取自 HAL 侧的接收逻辑与配置解析表反推，
  未直接读 APM 源码。若日后取得 frameworks/av 源码，应正面核验一次。
- 2026-08-31 P1 首窗口另实机证实：QUAT 后端采样率**没有 teardown 复位点**
  （恢复后 `QUAT_MI2S SampleRate` 仍停在 `KHZ_48`）。这与 44.1 目标直接相关——
  任何未来的速率切换都必须显式写入并读回，不能依赖遗留状态。
