# M3.5：SRC分层验证计划（Codex审定版，未执行）

当前仍固定48kHz；本批流动证据仅覆盖MM1/deep-buffer/S16 PCM。后端S24_LE不证明音源24位，也不证明无SRC。HIFI表示经确认的ESS活动通路，不能作为“bit-perfect”指示灯。

## 必须分开的四项证明

- **Android层是否重采样**：核对实际活动track、处理线程、输入/输出率、effect与增益路径；DIRECT只是线索，不是无SRC的充分条件，也不是逻辑上的唯一方式。
- **HAL/ALSA参数是否一致**：核对活动流的实际配置和节点映射，不以请求参数或一个backend枚举代替最终配置。
- **backend/时钟是否真实跟随**：枚举44.1能力、写后回读、实际时钟证据是不同层级。仅固定48k后端不能定位究竟在哪一层进行了SRC。
- **数字样本是否一致**：必须定义比对端点、容器格式、padding、通道顺序与测试向量。应用到DAC输入I2S，与DAC内部数字音量之后，是不同端点；不能把DAC内部衰减等同于上游I2S已改变。

Android可能在多个位置执行重采样，详见[AOSP SRC说明](https://source.android.com/docs/core/audio/src)。本项目下一步仍需对固定MoKee源码和设备逐层取证。

## 先离线，后申请窗口

1. 整理目标AudioPolicy profile、HAL open_output_stream/usecase映射、PCM rate/format和驱动支持的实际枚举，闭合既定N2（DIRECT PCM是否映射offload族）及P1–P7前置项。不要直接扩大当前MM1有效流证据到任意MM前端。
2. 从设备现有只读状态确定测试播放器、活动thread、PCM节点、backend实际名称和可观测时钟来源。不能预先假定存在名为QUAT_MI2S_RX SampleRate的控件、KHZ_44P1枚举或某个debugfs时钟文件。
3. 静态证据允许后，设计最小候选：44.1与48k两类已知测试流、每次仅改变一层、固定已有安全音量和明确回退。没有新设备窗口授权不写HAL、策略、mixer、kernel或时钟。
4. 受控测试记录应用track→AudioFlinger→HAL→ALSA→backend→实际时钟证据。任一层出现不匹配、额外DSP路径、错误重路由、服务异常或音量漂移，立即停止并按窗口回退方案恢复。
5. 只有存在可信数字采集点才做样本比对；不要杜撰高通数字签名回环工具。模拟试听或频谱不能单独证明bit-perfect，缺乏采集点则结论保留为未证明。

## 音量与安全约束

**禁止为追求bit-perfect把DAC推到0dB/255。** 当前允许上限237，现场基线205；这轮不更改上限，不测试高音量。应把SRC验证与音量功能验收分开。未来如需验证单位增益下的数据一致性，必须另行设计不经过耳机的安全测量路径并明确授权；不能把源码中的音量property强制设为0dB作为操作步骤。

未证明之前，不承诺44.1原生、192k、全APP免SRC或端到端bit-perfect。原agy建议中的错误控件名、强制0dB和“直接线程即免SRC”已撤销。
