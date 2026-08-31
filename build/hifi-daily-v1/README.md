# 日用候选的正式 HAL 构建输入

本目录只有构建准备材料，**没有正式目标构建产物**。

`manifest.xml` 展开原 manifest 的 654 项、include 的 124 项，以及 leo 的 5 个设备依赖，共 783 个声明；每项固定 40 位 SHA，并保留 copyfile/linkfile/groups。`source-lock.json` 记录公开来源、上游 ref 与验证状态。782 项经过 `git ls-remote` 解析；LeanbackIME 的预先固定 SHA 经 Gitiles 对象查询核实。所有源码对象仍需在同步后逐仓 `git rev-parse HEAD` 检查。

这是公开 mkq-mr1 源码候选的冻结，不是 2022 年出厂构建完整 manifest 的恢复。HAL 锚点保持 `7f4cac748b6f62897294cdaece9d1aec27e1e927`，frameworks/base 保持 `f6fd72a3d22a31c3cb120cc8b564114006c606da`。

## 可执行顺序

1. 在独立 Linux x86_64 主机上同步本清单，保留约 350GB 可用磁盘；建议 16 vCPU、64GB RAM。这是资源规划值，不是已完成的资源测量或必需下限。
2. 记录 Linux 镜像、repo 工具版本、全部源 HEAD、产品变量和工具链。产品来自设备树的 `mokee_leo`，使用 `mokee_leo-userdebug`。先构建未打补丁的 `audio.primary.msm8994` 并保存完整命令与日志。
3. 使用 `prepare-hal.py <Android 源码根目录>` 应用 8 个补丁。它拒绝非固定 HEAD 或已有改动的 HAL 工作区，绝不自动 reset/clean。
4. 分别使用独立 OUT_DIR 构建 OFF 与 ON 单模块。ON 的产品变量为 `AUDIO_FEATURE_ENABLED_LEO_HIFI=true`，OFF 为 false；必须从生成的 ninja/编译命令中核实变量实际生效，不能仅凭命令行赋值。不要构建 SystemUI 或整套 ROM。
5. 核对 baseline/OFF/ON 的源码、编译参数、CRT、compiler-runtime、目标 ARM 属性、SONAME、DT_NEEDED、动态符号与符号版本、BIND_NOW、SOUND_TRIGGER_ENABLED/功能依赖及实际产物路径。至少核对 32 位运行模块；不能删去未在一次现场观察中映射的 lib64 模块。
6. 通过上述检查后再形成绑定本次产物 SHA 的安装计划。`scripts/stage2` 仍默认引用历史 schema3 诊断模块；其脚本安全修复不是新产物的准入许可，也不能直接拿它部署日用版本。

## 构建环境的当前缺口

现有文件服务器约 4GB RAM，Android 源码站直连探测超时；Mac 本地剩余空间不足以容纳完整源码与构建输出。未部署代理、未改服务器配置、未购买云资源。本机 gcloud 没有已登录账号。

建议临时云构建的**预算上限为人民币 100 元，尚未获得金额确认**；这不是成交报价。购买前必须核对实例、系统盘/数据盘、网络和公网 IP 的总价与库存，并绑定运行时间上限与退出策略。仅关机可能继续收磁盘/IP 费用；完成后先回收并校验产物和必要日志，再释放本次新建资源。不启用自动续费，不删除用户原有资源。

网络不可只看“入站免费”。腾讯云的[带宽说明](https://cloud.tencent.com/document/product/213/43793)与[网络价格](https://cloud.tencent.com/document/product/213/113026)需结合所选实例核实；不采用“免费即不限速”的旧估算。100GB 在 10Mbps 下理想传输下限约 22.2 小时，不能按短时构建估价。
