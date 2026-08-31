# schema4 与音量恢复补丁

应用在 `phase5b-m3/0001..0005`、`phase5b-hifi-ui/0006..0007` 之后；上游锚点仍为 `7f4cac748b6f62897294cdaece9d1aec27e1e927`。冻结历史包不改动。

## schema4 固定契约

仅查询/返回一个 Android 参数：`leo_hifi_status=<payload>`。内层以逗号分字段、冒号分键值；不接受旧 schema3 的自动替换、拆平或兼容猜测。

- 内层键：`[a-z][a-z0-9_]*`；值：`[A-Za-z0-9_./-]+`，再进行字段类型/枚举/范围检查。禁止空白、控制字符、`;=,:` 混入值。
- 必需且唯一的 21 个字段：schema, session, gen, supported, requested, effective, live, flow, vol_ctl_l, vol_ctl_r, vol_db, vol_user, backend, fail, permanent_fail, probes, ev, bypass, vol_applied, restore_pending, acdb。未知字段也拒绝，扩展须另行修订契约。
- session 是正 uint63，generation 非负且 Java 可解析；音量控制回读范围 -1..255，-1 表示不可读。vol_db 必须与左声道回读一致；它不是模拟输出测量。
- `leo_hifi_status_string` 返回 0 才能封装输出。缓冲区截断返回错误并清空，不发布部分状态。
- 写请求仍是 mode 或 volume，加 session/gen。它们防陈旧请求，不是调用者身份认证；MODIFY_AUDIO_SETTINGS 是普通权限。

## 音量变化

新 HAL 会话不重放保存的用户增益；成功探测后确认/恢复 205/205。关闭、退出、普通路由及故障回退均包含必要的恢复。失败保留 `vol_restore_pending`，只在两个声道回读均为 205 时清除；恢复未确认时禁止新的增益请求和 HiFi 选路。状态查询只读，不触发恢复。

用户值 0 仍映射 213，仍不是静音。主机验证不能证明模拟增益、Android 软件音量叠加或听力安全；真实音量测试必须在安全负载和明确条件下进行。

## 验证入口

`python3 tests/hifi-daily-v1/run.py <打好补丁的 HAL 根目录> --output <证据目录>`

它编译真实控制器（模拟 mixer/property）和锁定的真实 MoKee libcutils（仅日志被桩替代），再经过依据源码的 AudioParameter/HIDL 键值传输模型与真实应用 Java 解析器。不是实际 Binder/HIDL、Android HAL 目标构建或模拟输出测试。

代码重放和主机通过不解除目标构建/设备验收门禁。
