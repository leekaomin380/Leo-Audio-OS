# Scripts

本目录将保存只读采集、依赖分析、构建、校验、签名和恢复工具。任何执行分区写入的
工具都必须默认拒绝运行，直到型号、构建、哈希、目标分区和恢复材料全部通过检查。

## 当前工具

- `collect-audio-baseline.sh`：仅接受一台已授权、代号为 `leo` 且可获得 Root 的设备，
  采集系统身份、分区、音频文件索引与哈希、init 引用、服务、ALSA 和 AudioFlinger
  空闲基线。结果默认写入被 Git 忽略的 `resources/private/device-baselines/`，不采集
  设备序列号、账号或用户文件。
- `capture-audio-state.sh LABEL`：采集一次短时运行状态，用于比较未插耳机、插入耳机
  和 Spotify 播放三个状态。只读取属性、AudioPolicy、AudioFlinger、ALSA、mixer 与
  音频相关内核日志。
