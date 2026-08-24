# 音频基线独立审计 — 2026-08-24

## 委派

- 工具：`agy` CLI 1.1.15；
- 请求模型：`gemini-3.1-pro`，high effort；
- 权限：plan + sandbox，只允许读取公开文档和脚本；
- 禁止范围：`resources/private/` 和任何文件修改；
- 问题：区分已证实事实与推断，检查采集是否只读，审查 U0/H0/H1 实验遗漏。

本次 print 输出没有提供服务端实际模型元数据，因此这里只登记请求模型，不把它描述为
独立确认的实际后端版本。

## 采用的意见

1. 增加经过音频关键词过滤的 Android logcat；
2. 增加 SELinux `avc: denied` 证据；
3. 采集 `audioserver`、`audiod`、`adsprpcd` 和 Spotify 的 `/proc/PID/maps`；
4. 采集所有现有 PCM substream 的 `hw_params`；
5. 保存进程表，以便把 AudioFlinger client PID 对应到应用；
6. 从 H1 停止播放后等待至少 5 秒，再采集 H0，避开已确认的 3 秒 standby delay；
7. 增加与音频相关的时钟和中断只读快照。

## 部分采用

- 审计建议遍历所有 ALSA 卡。实机 `/proc/asound/cards` 当前只显示 card 0，设备自带的
  旧版 `tinymix` 也不支持新版本常见的 card 参数。脚本已经遍历所有 card 的
  `hw_params`；若以后出现第二张卡，再引入兼容的新版 tinyalsa 工具读取其 mixer。

## 未直接采用

- 不采集完整、未过滤的 logcat 或 dmesg；它们噪声大，并可能包含与音频无关的私有
  设备或应用信息。保留经过关键词过滤的私有证据即可。
- 不把“关闭 Spotify 音量标准化和 EQ”预设为证明 offload 的必要条件。第一轮先记录
  当前固定设置；之后如需改变，每个设置单独形成对照变量。
- 不以 24-bit/192 kHz 为预期结果。Spotify 的真实源格式、解码方式和设备协商结果
  必须由 `hw_params` 证明，不能先规定一个“HiFi 数字”。

## 审计后的新证据

更新后的 U0 采集已经从 `audioserver` 进程映射中确认：

- 实际加载了 32 位 `audio.primary.msm8994.so`；
- 实际加载了 `/system/vendor/lib/libacdbloader.so`；
- 实际加载了 `libtinycompress.so`；
- 所有枚举到的 PCM substream 在 U0 均为 `closed`。

这把 `libacdbloader.so` 从“HAL 中出现的运行时加载候选”提升为“空闲音频服务已经
实际加载的依赖”。其他候选库仍需在 H1 状态继续检查。

