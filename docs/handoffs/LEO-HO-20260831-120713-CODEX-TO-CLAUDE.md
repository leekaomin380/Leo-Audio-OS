# LEO-HO-20260831-120713-CODEX-TO-CLAUDE

状态：**Codex已收尾，待Claude接管；无在途agy，无自动下一轮。**

## 1. 结论先读

HIFI开关、顶部HIFI标识、长按独立DAC音量已完成源码和离线验证，尚未成为可安装SystemUI，**手机界面未变**。schema3协议在HAL写端与UI两侧绑定session/gen，异常拒绝；本轮补足poll期间用户意图有界保留。330条主机断言+40项Python测试通过。HAL ON/OFF/重复与仅HAL raw两次离线审计通过。**NO_GO_TARGET / NO_GO_DEVICE；SRC仍48k，未突破。**

文件服务器另经用户明确授权修正持续在线策略，已经真实部署：停用“AC离线立即关机”，禁用睡眠/合盖动作，保留电池<=5且放电的延迟确认关机。SSH/SMB及服务器未重启。

## 2. 工作区、提交与文件入口

- 功能提交：`c16864f665cc52951a2d682b76320dcc49a2c348`（150文件，8959新增/1删除；包括此前HIFI实现、本次schema3、测试工具和服务器策略快照）。本交接随后以独立文档提交保存；以分支HEAD和输出git-submission.json定位交接提交。
- 分支：`codex/hifi-schema3-eight-way-20260831`；基线`61b4f6d`。**仅本地commit，未push或merge**。
- 隔离工作树：`/Users/km/Documents/Codex/leo-audio-os/worktrees/codex-hifi-20260831-1023`。不要改其他人的工作树或把主目录HEAD误认为本分支。
- 当前交付：`/Users/km/Documents/Codex/2026-08-31/users-km-documents-codex-leo-audio/outputs/hifi-eight-way-20260831`；入口`最终审定.md`、`observations-summary.json`、`readiness-*-result.json`。
- 前两轮冻结基线：`/Users/km/Documents/Codex/2026-08-31/users-km-documents-codex-leo-audio/outputs/hifi-two-rounds-20260831`，其中`两轮阶段审定.md`与私有raw。更早schema2包`HIFI-实现包-20260831.zip`保持旧SHA740099b333f96c8626d881e7684abe64663483d6e06c395fee0b955f8a942916。
- 当前工作scratch：`/Users/km/Documents/Codex/2026-08-31/users-km-documents-codex-leo-audio/work/hifi-eight-way-20260831`，上一阶段`/Users/km/Documents/Codex/2026-08-31/users-km-documents-codex-leo-audio/work/hifi-two-rounds-20260831`，最初API工具和私有接口JAR`/Users/km/Documents/Codex/2026-08-31/users-km-documents-codex-leo-audio/work/hifi-batch-20260831`。私有API/ROM不入Git/源码ZIP。

## 3. 补丁与复验

HAL固定`7f4cac748b6f62897294cdaece9d1aec27e1e927`，先原`patches/phase5b-m3/0001..0005`，再`patches/phase5b-hifi-ui/0006-hal-schema2.patch`、`0007-hal-schema3-guard.patch`。

SystemUI公开候选`f6fd72a3d22a31c3cb120cc8b564114006c606da`，应用HIFI目录的0001、0002、0003。**这是组件候选提交，不是已匹配目标ROM的完整manifest**。

最终自洽测试/工具入口`tools/phase5b-hifi-final/README.md`。主机回归：`python3 tools/phase5b-hifi-final/tests/run.py <已应用补丁的SystemUI绝对目录> <HAL绝对目录>`；Python测试：`python3 -m unittest discover -s tools/phase5b-hifi-final/tests -p 'test_*.py'`。期望330断言、40Python测试。历史schema2/schema3套件保留，不替代final套件。

ARM诊断脚本`scripts/verify-hifi-schema3-link.sh`使用冻结Gate2工作区/headers、新run目录、HIFI_UI_PATCH=0006和HIFI_SAFETY_PATCH=0007。既有Gate2输入位于`/Users/km/Documents/Codex/2026-08-30/leo-audio-os-m3-users-km-2/outputs/gate2-link-20260831`；headers位于`/Users/km/Desktop/Leo-Audio-OS-agy-gemini31pro/research-cache/headers`。工具链有本机路径及-fcommon诊断语义，不能当作Android10目标兼容闭环。

本轮API验证是7个新Java类+2个修改集成类与设备DEX派生no-code接口JAR编译、新资源aapt2检查；不是完整APK。不能打包这些接口JAR替代系统实现。

## 4. 候选与真实设备状态

- ON和ON-repeat：`bfd4c93471c78fc24cd4e9d4a862b69119bf734caec13595fcc4eeaeafa01c3d`。
- OFF与上一版OFF：`e6e3540dcb9737e722213c5db904dd6e9c0788bad66da632c2bdc108fb612500`。
- 私有HAL-only raw：`9a2c82355bfb320efcf34208e1e22427fb89f7854780f853a1cb13442bf7c762`，位于上一阶段`private-diagnostic-image/MOkee-HAL-schema3-NOT-DEPLOYABLE.raw`。
- 原raw：`7238ee916246f6ac4564d7386639494323bae01b67eb8bed6b0168b2d47689c3`，原文件未改。425984 blocks、4096 block size、106496 inodes、256 inode size、UUID4729639d-b5f2-5cc1-a120-9ac5f788683c；绝不能套旧MIUI几何/normalize脚本。
- raw两次同hash、全4570路径内容/语义和补充inode metadata比对、SELinux4570/capability6保留、e2fsck=0。最终HAL和镜像工具与已审计版本逐文件相同。

手机serial68f5f468；最新只读证据`verification/device-at-handoff.json`：boot_id `245a2267-e200-4484-81f8-1b0b7ba2f0e1`、audioserver6378、实际HAL loader **android.hardware.audio@2.0-service6379**，原32位HALhash`701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47`、XMLhash`13db0e6e5bd04e02c36a6b84e815f492d730e107866b91e605ee653364084bb4`、Volume **205205**。adbd既有root；不要假设设备存在su命令，也不要为只读检查重启adbd。

当前raw没带新SystemUI/Settings/boot，不是可刷发布包。旧资料提到collect/nc链，**本轮未处置**；下任若调查须核验当前PID/所有者，不使用killall/pkill。

## 5. 八路探索审定

J151–J158全部首次返回，0工具事件；全8路同时存活78.624s、整轮269.959s，进程树RSS峰值2302.95MiB，54样本压力全1，swap开始/结束均2711.25MiB，未降级。请求gemini-3.1-pro-high/high；供应端实际模型未独立核实。不能推导8路编译安全或声称受控加速比。

有价值发现：poll期间显式点击丢失、下游gate报告依赖链、交付校验工具。必须关注**否决记录**：J151扩大任意MM流、J152无界重试/放宽写前gen、J154否认真实ext4测试并删除metadata、J156为了bit-perfect推0dB，都没有采用。原始agy交付是不可信建议，以最终源码/测试/审定文档为准。

## 6. 服务器持续在线变更

内网构建/文件服务器（地址、账号与硬件规格见本地私有记录，不入公开库）。已验证旧`power-loss-shutdown.service`执行AC离线即shutdown；现disabled/inactive。5个sleep目标masked，logind的lid/externalpower/idle为ignore。新`leo-critical-battery-guard.service`enabled/active，脚本`/usr/local/sbin/leo-critical-battery-guard.py`，只在AC0、BAT0 Discharging、capacity<=5连续3次10秒采样才正常关机。8项本地测试、unit语法/运行回读通过；未实际断电/合盖测试，不能保证硬件/网络/电池耗尽时持续在线。

备份、安装前状态和**唯一采用的回退脚本**：`/var/backups/leo-always-online-20260831-1148/rollback.py`。执行前强制AC在线并检查安装文件hash；它将恢复断电立即关机，不要未经任务要求运行。原SSH PID763、SMB894、logind692保持不变，服务器boot_id `257c32fb-1372-478a-ba3c-18d63e1af6c6`。最新证据`verification/server/at-handoff.json`。

没有上传/迁移ROM到NAS，没有更改共享、网络、代理。服务器在线仅解除了连通性问题，尚未发现可直接用的完整Android构建环境。

## 7. 下一任优先顺序与权限

1. 只读核验分支/commit/工作树、手机基线、服务器电源设置和证据hash；登记接管及异议。
2. 先解决SystemUI完整manifest/资源依赖、授权匹配签名能力，再建立未修改目标基线和候选。目标sharedUID实测android.uid.systemui，原证书SHA`ee423e29141c3cecadce6952aad03dfc57417806c01d558fb2f982d73dbbadca`；公开证书不是授权签名证明。不要搜索、读取或转移私钥。具体顺序见`docs/phase5b-hifi-final/J155-SYSTEMUI-NEXT.md`。
3. 闭合HAL Android10 CRT/runtime/provider/ABI及实际loader门；准备整套回退。**没有当前手机写入授权**，必须获得新设备窗口后才安装/挂载/重启服务/改音量/刷机。先205基线，再受控功能与截图/试听，不把历史授权当新许可。
4. M3.5先做只读/离线采样率链路调查；不许为bit-perfect越过237上限，不用DIRECT标签或试听冒充SRC证明。见J156文档。

本次“提交”仅本地commit；没有push/merge授权。本轮额外8路已用完，无计划中的自动下一轮、后台监控或向Claude自动发送消息。用户将自行交接；Codex完成封存后停止。
