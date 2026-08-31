# 日用候选的正式 HAL 构建输入

本目录只有构建准备材料，**没有正式目标构建产物**。

`manifest.xml` 展开原 manifest 的 654 项、include 的 124 项，以及 leo 的 5 个设备依赖，共 783 个声明；每项固定 40 位 SHA，并保留 copyfile/linkfile/groups。`source-lock.json` 记录公开来源、上游 ref 与验证状态。782 项经过 `git ls-remote` 解析；LeanbackIME 的预先固定 SHA 经 Gitiles 对象查询核实。所有源码对象仍需在同步后逐仓 `git rev-parse HEAD` 检查。

这是公开 mkq-mr1 源码候选的冻结，不是 2022 年出厂构建完整 manifest 的恢复。HAL 锚点保持 `7f4cac748b6f62897294cdaece9d1aec27e1e927`，frameworks/base 保持 `f6fd72a3d22a31c3cb120cc8b564114006c606da`。

## 可执行顺序

1. 在独立 Linux x86_64 主机上同步本清单，保留约 350GB 可用磁盘；建议 16 vCPU、64GB RAM。这是资源规划值，不是已完成的资源测量或必需下限。
2. 先运行 `python3 build/hifi-daily-v1/audit-inputs.py <Android 源码根目录> --report <源码树外的新证据文件.json>`。该检查只读核对全部独立仓库、HEAD、工作区状态和清单来源一致性，记录主机资源；缺失、错误版本、修改或不支持的主机均返回非零。它不下载、不构建、不覆盖旧报告。随后记录 Linux 镜像、repo 工具版本、产品变量和工具链。产品来自设备树的 `mokee_leo`，使用 `mokee_leo-userdebug`。先构建未打补丁的 `audio.primary.msm8994` 并保存完整命令与日志。
3. 使用 `prepare-hal.py <Android 源码根目录>` 应用 8 个补丁。它拒绝非固定 HEAD 或已有改动的 HAL 工作区，绝不自动 reset/clean。
4. 分别使用独立 OUT_DIR 构建 OFF 与 ON 单模块。ON 的产品变量为 `AUDIO_FEATURE_ENABLED_LEO_HIFI=true`，OFF 为 false；必须从生成的 ninja/编译命令中核实变量实际生效，不能仅凭命令行赋值。不要构建 SystemUI 或整套 ROM。
5. 核对 baseline/OFF/ON 的源码、编译参数、CRT、compiler-runtime、目标 ARM 属性、SONAME、DT_NEEDED、动态符号与符号版本、BIND_NOW、SOUND_TRIGGER_ENABLED/功能依赖及实际产物路径。至少核对 32 位运行模块；不能删去未在一次现场观察中映射的 lib64 模块。
6. 通过上述检查后再形成绑定本次产物 SHA 的安装计划。`scripts/stage2` 仍默认引用历史 schema3 诊断模块；其脚本安全修复不是新产物的准入许可，也不能直接拿它部署日用版本。

`audit-inputs.py` 是打补丁前的输入记录，不用于将已打补丁的源码误报为干净基线。12 个真实临时 Git 仓库测试场景覆盖缺失、父仓库误识别、版本不符、修改、目录逃逸、来源不符和证据覆盖保护。测试命令为 `python3 tests/hifi-daily-v1/test_input_audit.py`。报告始终保留 `build_verified=false` 和 `target_module_verified=false`：没有核验生成文件、所有忽略文件、工具链可执行性或最终编译命令；功能开关和 ABI 检查仍需在真实构建后执行。

## 构建环境：现有主机受限试运行

2026-08-31 17:49 实测：现有 Linux x86_64 文件服务器有 3.7GiB RAM、3.9GiB swap、约 401GB 可用磁盘。源码站直连仍超时，但通过仅绑定服务器回环地址的临时 SSH 转发，复用 Mac 已有 HTTP 代理后返回 HTTP 200。没有修改公共代理配置或购买云资源。因此云主机不再被视为必然前置条件；先用现有主机试验，不能把建议的 64GB RAM 当成已经证实的最低要求。

已新建独立构建目录并校验集成源码 bundle，固定 repo 工具到 `b85886fa9f5b4e2189cc5b2f40bd0a80459d4c77`（2.66.1）。repo 初始化与默认发行签名检查成功，未使用 `--no-repo-verify`。用户级 systemd 受限任务已开始同步锁定源码：1 核 CPU 配额、3GiB MemoryMax、2GiB MemorySwapMax、低 CPU/IO 优先级、256 TasksMax、8 小时运行上限，并在剩余磁盘低于 128GiB 时终止本次同步。限制值已从运行中的 unit 回读核实。

此时仅确认同步任务运行，**未证明低内存主机足以完成正式构建**。先同步工具链，再同步完整 783 项并运行输入检查；不删除项目或特性来迎合资源限制。临时联网依赖 Mac 代理与 SSH 会话存活；中断先核实原任务状态再续传，不覆盖历史日志。不改公共网络配置、不全局安装工具、不为此次同步修改系统 swap。

### 21:40 运行更新

- 10 项工具链相关仓库已核实固定 HEAD 且干净。按构建系统 PATH 使用自带 Python 2 后，默认 `clang-r353983c1` 的 Clang/Clang++/LLD、Go、JDK 可执行。六项缺少的主机工具经现有 APT 索引 SHA256 校验后，仅解包到工程目录，未安装全局软件。
- `soong_ui` 已从锁定源码实际编译成功：约 9 秒，峰值内存 238MB、无 swap。这只证明主机启动工具，不是目标 HAL。
- 原同步完成 782 个仓库目录，最后一个 `prebuilts/gradle-plugin` 的活连接曾超过两小时无读写进展。确认新连接 HTTP 200、旧传输字节与文件时间不变后，停止原任务并核实相关进程退出。已完成源码与旧日志保留。
- 新同步任务使用 `--optimized-fetch` 跳过已有固定对象，并仅对本进程设置 HTTP/1.1、低于 1KiB/s 持续 120 秒退出及有界重试。2 核、3GiB RAM、2GiB swap、2 小时运行上限；其余空间和优先级限制不变。21:41 新包已约 2.6GB 且仍增长，未将目录存在误记为全量核验通过。
- 已启动绑定本次同步 InvocationID 的接续任务：等待同步终止并检查完整输入报告，然后由 baseline 入口再次核验真实源码、全部 copyfile/linkfile 和产品变量，才调用上游 `soong_ui.bash --make-mode -j1 audio.primary.msm8994`。使用独立 OUT_DIR，禁止缺失依赖放行，保留 arm64/armv8-a、32 位 armv8-a 和 Sound Trigger；结束后仍需 ABI 审核，不自动部署手机。
- 接续任务本身有 8 小时上限，失败就停止。它目前处于等待状态；正式 baseline、OFF、ON 和设备验收仍未完成。具体 unit 标识、私有路径、脚本与现场日志保存在交付证据。

## 仅在现有主机不能完成时考虑云资源

21:50 补充：完整 783 项同步及源码核验已通过。baseline 第一次尝试在 copy/link 核验时停止：原 MoKee manifest 将 `frameworks/support/README.md` 的来源错误地挂在 `sdk/current/androidx-README.md`。已核实原始输入文件也如此，正确文件存在于锁定的 `prebuilts/sdk`，Git blob 为 `b7ac07ed1ed1ffc43e12662ae419258c36d56bc7`。本清单仅将这一 linkfile 移到正确项目下，`source-lock.json` 记录修正；783 项源码记录完全不变。第一次失败证据保留，修正后使用新的 baseline 输出目录。

建议临时云构建的**预算上限为人民币 100 元，尚未获得金额确认**；这不是成交报价。购买前必须核对实例、系统盘/数据盘、网络和公网 IP 的总价与库存，并绑定运行时间上限与退出策略。仅关机可能继续收磁盘/IP 费用；完成后先回收并校验产物和必要日志，再释放本次新建资源。不启用自动续费，不删除用户原有资源。

网络不可只看“入站免费”。腾讯云的[带宽说明](https://cloud.tencent.com/document/product/213/43793)与[网络价格](https://cloud.tencent.com/document/product/213/113026)需结合所选实例核实；不采用“免费即不限速”的旧估算。100GB 在 10Mbps 下理想传输下限约 22.2 小时，不能按短时构建估价。
