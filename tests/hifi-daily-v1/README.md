# 日用候选的主机边界验证

运行：`python3 tests/hifi-daily-v1/run.py <patched HAL root> --output <evidence dir>`。

必须使用 JDK 与支持 ASan/UBSan 的 clang/clang++；脚本不调用 adb、不下载依赖、不修改输入 HAL。

- `legacy_controller.c` 保留既有控制器逻辑用例，仅将序列化期望从 schema3 改成 schema4。
- `safety.c` 增加关闭、路由退出、失败恢复、保留硬件状态的重启、声道不一致和序列化截断检查；导出真实控制器状态供 Java 测试。
- `transport/` 为锁定提交的 MoKee libcutils 原始源码（版权头保留，来源与哈希见 sources.json）。仅日志使用无操作桩。它实际执行 str_parms 的封装和解析。
- `run.py` 中的 AudioParameter/HIDL 传输段是依据 Android 10 源码写出的模型，不是 Android 实际 Binder；保留首个等号分隔、分号拆分、按键排序和后值覆盖行为。
- `ProtocolTest.java` 编译应用真实解析器与请求门，不使用另写的解析器代替产品代码。

测试通过只证明这些边界，不证明目标模块链接、设备路由、模拟增益或长期稳定性。
