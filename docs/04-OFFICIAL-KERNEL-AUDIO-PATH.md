# 04：官方内核中的有线 HiFi 硬件路径

## 结论

本文基于 Xiaomi 官方内核 `libra-n-oss` 分支、提交
`f4cab50d74f8e55e0a0dbbf430d163f46c6fc3a1`。它解释了 U0/H0/H1 实机实验背后的
硬件控制机制，但不把公开源码自动等同于参考机正在运行的每一个内核字节。

已确认的播放链路为：

```text
MultiMedia1 / QDSP routing
  → QUAT_MI2S_RX backend (S24_LE, default 48 kHz)
  → GPIO 57/58/59/60 I²S pins
  → ES9018 at I²C bus 6, address 0x48
     ├─ codec supplies BCLK/LRCLK as master
     ├─ 49.152 MHz oscillator for the 48 kHz family
     ├─ 45.1584 MHz oscillator for the 44.1 kHz family
     ├─ impedance-dependent THD compensation
     └─ DAC → OPA enable → analog switch → headphones
```

这解释了为什么扬声器播放不触发这条路径，也解释了为什么“插入耳机”和“开始播放”
是两个独立事件。

## 1. 设备树把真实硬件资源交给驱动

`arch/arm/boot/dts/qcom/msm8994-mtp.dtsi:671-688` 把 ES9018 声明为 I²C 地址
`0x48`，并绑定：

| 资源 | 设备树名称 | GPIO / 上游 |
| --- | --- | --- |
| 数字 I/O 电源 | `dvcc` | `vreg_hifi_1p8` / GPIO 93 |
| 模拟/辅助电源 | `vcca` | `vreg_hifi_3p3` / GPIO 94 |
| 数字核心 5 V | `dvdd` | `vreg_hifi_5p0` / GPIO 106 |
| 左模拟 5 V | `avccl` | `vreg_smps_5p0` / GPIO 14 |
| 右模拟 5 V | `avccr` | `vreg_cp_5p0` / GPIO 12 |
| Reset | `ess,resetb-gpio` | GPIO 8，低有效 |
| Mute | `ess,mute-gpio` | GPIO 33 |
| 模拟输出切换 | `ess,switch-gpio` | GPIO 34 |
| OPA 使能 | `ess,opa-gpio` | GPIO 102，仅硬件版本 2.2 分支使用 |
| 45.1584 MHz 晶振 | `ess,clock-45m-gpio` | GPIO 107 |
| 49.152 MHz 晶振 | `ess,clock-49m-gpio` | GPIO 25 |

五路固定 regulator 及其启动延迟定义在同文件 `762-800`。QUAT_MI2S 的 MCLK、
BCLK/LRCLK 和数据分别使用 GPIO 57、58/59、60；active 状态驱动强度为 8 mA，sleep
状态降为 2 mA 并下拉，见 `msm8994-pinctrl.dtsi:1659-1703`。

这些节点的意义不是“文件必须原样复制进任何 Android 版本”，而是给出了第二代设备树
必须表达的真实电气资源、极性、依赖关系和时序。

## 2. ES9018 是 I²S 主设备

QUAT_MI2S RX 的 DAI 格式为：

```text
I2S | CBM_CFM | NB_NF
```

`CBM_CFM` 表示 codec 同时提供 bit clock 和 frame clock，证据在
`sound/soc/msm/msm8994.c:3956-3970`。同一文件只定义了
`MSM_QUAT_MI2S_MCLK`，没有定义 `MSM_QUAT_MI2S_MASTER`；因此实际编译进入
`2111-2162` 的从机分支：LPASS 选择外部时钟，CPU DAI 作为 slave。

ES9018 驱动把 BCLK 固定计算为 `64 × sample_rate`，再从 45.1584 MHz 和
49.152 MHz 两只晶振中选择一个，并配置 4/8/16 分频。对应关系是：

| 采样率家族 | BCLK 示例 | 晶振 | 典型分频 |
| --- | ---: | ---: | ---: |
| 44.1 kHz | 2.8224 MHz | 45.1584 MHz | 16 |
| 48 kHz | 3.072 MHz | 49.152 MHz | 16 |
| 88.2 kHz | 5.6448 MHz | 45.1584 MHz | 8 |
| 96 kHz | 6.144 MHz | 49.152 MHz | 8 |

证据为 `sound/soc/codecs/es9018.c:70-75,352-395,1197-1323`。这证明驱动具有
双时钟家族设计；但参考机本次 Spotify 实验只验证了 48 kHz 实际运行，不能把 44.1、
88.2 或 96 kHz 的代码能力写成已经实机验收。

## 3. 为什么 Spotify 的 16-bit 流仍进入 24-bit 后端

`msm8994.c:245-247` 将 QUAT_MI2S 默认设为 48 kHz / `S24_LE`；
`2229-2242` 又在 backend fixup 中无条件把格式掩码设为 `S24_LE`，采样率取当前
QUAT_MI2S kcontrol 值。

这与 H1 实测完全吻合：

- Spotify AudioTrack：44.1 kHz / PCM16；
- AudioFlinger 和前端 PCM：48 kHz / PCM16；
- QUAT_MI2S backend：48 kHz / S24_LE。

这里的 S24_LE 是传输容器和后端总线格式，不会凭空恢复 Spotify 16-bit 源中不存在的
信息。源码还暴露了可变的 `QUAT_MI2S BitWidth` 控件，但 fixup 始终强制 S24_LE；二者
存在语义不一致，正式系统不能只相信控件显示，必须再次读真实 `hw_params`。

## 4. 阻抗如何改变 DAC 参数

耳机插入后，WCD9xxx MBHC 执行阻抗检测，并把左右声道较小值写入
`curr_hs_impedance`，见 `wcd9xxx-mbhc.c:974-975,5440-5451`。ES9018 上电时读取该值，
按 12、26、50、150、600 欧姆档位选择三组 THD 补偿寄存器，再同步寄存器缓存，见
`es9018.c:78-112,671-708`。

所以阻抗检测不是一个只供 UI 显示的数字；它进入了 DAC 初始化参数。第二代若丢失
Tomtom/MBHC 测量路径，即使“有声音”，也不能宣称与原厂 HiFi 行为等价。

## 5. 播放启动与停止时序

### 首次打开 QUAT_MI2S backend

`msm8994.c:2073-2166`：

1. QUAT 资源引用从 0 增至 1；
2. 打开 Tomtom MBHC VDDIO；
3. 选择 I²S mux 并把 QUAT 引脚切到 active；
4. 把 LPASS 设为外部时钟 slave；
5. 启动 QUAT_MI2S RX 时钟接口。

### ES9018 bias on

`es9018.c:671-752`：

1. 先静音；
2. 打开五路 regulator（硬件 2.2 例外）；
3. 打开所选晶振；
4. 等待 1 ms，释放 reset，再等待 1 ms；
5. 根据阻抗写 THD 补偿，同步寄存器与滤波配置；
6. 打开 soft start，等待 150 ms；
7. 打开 OPA、模拟 switch，最后解除静音（硬件 2.2 例外）。

### 最后一个用户关闭

`es9018.c:763-788` 和 `msm8994.c:2171-2205`：

1. 静音，关闭 OPA 和模拟 switch；
2. 关闭 soft start，assert reset，关闭晶振；
3. 非硬件 2.2 关闭五路 regulator；
4. QUAT 引用回到 0 后关闭 LPASS 时钟、恢复 sleep pinctrl、关闭 MBHC VDDIO。

这与 H0-after 中约 3 秒后 PCM、mixer、MBHC VDDIO、QUAT 时钟全部关闭相互印证。

## 6. 耳机插入本身不会启动 DAC

MBHC 插入路径会测阻抗并调用 `es9018_set_headphone(true)`；该函数只在 DAPM bias
已经是 ON 时打开模拟 switch，否则反而保持 switch 关闭，见
`wcd9xxx-mbhc.c:950-998` 和 `es9018.c:1346-1355`。

因此状态机是：

```text
插耳机、未播放 → 检测与记录阻抗，DAC播放路径仍关闭
插耳机、开始播放 → QUAT_MI2S + DAC bias on + OPA/switch
暂停并等待standby → PCM/QUAT/DAC活动路径关闭，耳机检测状态保留
```

这正是实机 H0/H1/H0-after 的行为。

## 7. 必须保留为疑问的代码异常

以下现象不能未经实验就“修复”：

1. **硬件版本 2.2 特例**：probe 时提前打开电源，此后 bias on/off 不再切 regulator，
   且 startup 跳过最后一次 unmute。它可能对应 P2C 硬件布线差异，也可能是遗留代码；
   在确认参考机硬件版本和 GPIO 实际波形前不能删除。
2. **shutdown 结尾解除 mute**：DAC 已 reset/断时钟后，代码把外部 mute GPIO 恢复为
   unmute。表面反直觉，但可能用于避免 GPIO 默认态、电流或下一次启动问题；只能记录
   为审计项，不能直接定性为 bug。
3. **错误路径解除 mute**：I²C/cache 初始化失败后也恢复 mute GPIO。它值得故障注入
   验证，但量产参考机上没有观察到对应失败。
4. **QUAT 采样率控制与 slave 时钟参数**：代码公开多种采样率，但 LPASS slave 分支
   写入固定的 3.072 MHz 外部 IBIT 时钟参数。它是否只是接口占位值，还是限制非 48 kHz
   运行，必须在可回滚测试机上以真实 44.1/96 kHz backend 验证。
5. **驱动卸载资源释放不完整**：remove 路径没有像 probe 错误路径那样释放两只 clock
   GPIO 和 OPA GPIO。当前 defconfig 将驱动编入内核，正常产品生命周期不会卸载它，
   但移植或模块化时应修正。

## 8. 对第二代系统的直接约束

第二代不是“复制一个 `audio.primary.so`”即可。最小 bring-up 必须同时满足：

- 使用与硬件相符的 ES9018 codec 驱动和 `leo` 设备树资源；
- 保持 QUAT_MI2S codec-master / LPASS-slave 关系；
- 保持双晶振选择、I²C 地址、GPIO 极性、regulator 依赖和延迟；
- 保持 MBHC 阻抗测量到 `curr_hs_impedance` 再到 THD 补偿的跨驱动数据流；
- 保持 32 位 Audio HAL 所需 ABI、ACDB、mixer 和 DSP 侧依赖；
- 用运行时 PCM、mixer、时钟和听音/测量验收，而不是以“系统启动”作为完成标准。

本文解决了硬件控制层的第一轮映射。仍未解决的是 stock boot 与公开内核的逐 blob
差异、参考机硬件版本、regulator 实际 idle 状态、非 48 kHz 运行，以及原厂 HAL 的
init/SELinux/属性完整闭包。
