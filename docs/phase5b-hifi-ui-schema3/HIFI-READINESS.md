# HIFI 分阶段证据检查器

`python3 tools/hifi_readiness.py --evidence evidence.json --output new-result.json`

本工具只检查人工审定证据的结构、SHA256 与相对文件路径，不运行构建、签名或设备操作，也不能凭一份 JSON 授予安装权限。即使某份伪造文件的哈希正确，也不意味着其主张真实；证据内容仍须架构师审查。

三道顺序门：
- `host_diagnostic`：source_frozen、host_tests、elf_closure、feature_off_equal、repeatable。
- `target_build`：再要求 full_target_manifest、baseline_build、resources_compatible、toolchain_provenance、target_artifact；systemui_full 额外要求 legal_matching_signing_path。
- `device_window`：再要求 offline_fs_audit、rollback_verified、device_preflight_fresh、current_device_authorization。

artifact_scope 为 host_diagnostic / hal_only / systemui_full；host_diagnostic 范围不可请求目标或设备门。hal_only 省略 APK 签名要求，但不省略 HAL 工具链、ABI、真实目标产物等审定。

每个项目采用 `{ "passed": true, "file_path": "relative-proof.log", "sha256": "..." }`；只接受布尔 true，不接受字符串、数字、null；拒绝绝对路径、`..`、证据目录内的符号链接和哈希不符。签名证据 proof_type 必须为 authorized_matching_signer_attestation 或 reproducible_matching_signed_build，且内容需要人工核实。公开证书相同不等于存在授权签名能力；本工具不读取私钥。

退出码：0 为请求门通过；2 为证据不足 NO_GO；1 为输入/使用错误。已有输出不得覆盖。所有测试中的正面证据均为明确标记的合成夹具，不能用于真实放行。
