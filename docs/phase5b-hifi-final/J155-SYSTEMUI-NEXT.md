# 完整 SystemUI 的下一步（Codex审定版）

状态：NO_GO_TARGET；本轮未进行完整APK构建或签名。公开frameworks_base候选提交 f6fd72a3d22a31c3cb120cc8b564114006c606da 不是已证明对应目标ROM的完整manifest。

## 最短解阻顺序

1. **冻结目标身份。** 从现有ROM构建信息、设备树和公开release记录建立manifest对应关系；目标设备已知leo，具体lunch产品名须从实际源码列举，不能虚构mokee_<device>。SystemUI的sharedUID实测为android.uid.systemui。进入下一步需有源码提交/manifest、资源overlay、依赖模块清单。
2. **先确认授权签名路径是否存在。** 当前已知原SystemUI公开证书SHA256为ee423e29141c3cecadce6952aad03dfc57417806c01d558fb2f982d73dbbadca。原位更新需要满足现有包签名、sharedUID及签名权限的实际约束；framework-res/Settings证书相同是观测事实，不应把三个包误说成相同sharedUID。可由有权限的原构建方提供签名或构建证明；不能因为缺签名就检索、读取私钥。无授权路径则明确停在目标发布门前，不以自行重签绕过。
3. **评估最小完整依赖闭包。** 使用目标分支自己的build配置与prebuilts决定JDK、编译器和环境；不要凭现代AOSP文档替代Android10/MoKee历史分支。现有extracted目录是ROM提取物，不是可补一份envsetup就变完整源码。先列出需要取回的仓库、预计磁盘与峰值内存；大规模下载/新服务器环境应另有明确任务授权。
4. **确定构建主机。** 本机当时约19GiB余量，不宜直接开始未知规模repo sync。NAS已验证x86_64、约3.8GiB内存+4GiB swap、401GB余量；它是可评估的目标，不代表内存/工具链足以完成构建。先验证目标分支环境，再以保守并行度试未修改SystemUI基线，记录实际RSS、空间和依赖，不能称“module-only必然够用”。
5. **基线成功后再应用补丁。** 依序SystemUI0001、0002、0003；实际产品、构建模块名和输出路径以已核验树为准。本文件不提供未验证的lunch/make命令。先基线，后候选；保存源输入、资源、签名身份、build log及APK hash。
6. **离线目标审核。** 验证完整APK资源和manifest、目标API/privileged权限、sharedUID/签名兼容、SystemUI启动入口、HAL配对schema3，准备原APK及整套回退材料。不得重打包设备DEX派生的no-code接口JAR作为产品。
7. **新设备窗口才上机。** HAL真实加载者是android.hardware.audio@2.0-service，现有audioserver不直接映射HAL。先205基线和回退演练，再开关/截图/音量受控验收。仅有host API编译不可跳过此门。

官方参考：[AOSP构建环境](https://source.android.com/docs/setup/start/requirements)、[发布签名](https://source.android.com/docs/core/ota/sign_builds)。这些解释通用流程，不能证明当前MoKee分支的完整依赖、JDK或签名权限。原agy文档中“搬提取目录构建脚本”“必须定位私钥”“未知设备代号”等表述已撤销。
