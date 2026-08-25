# Phase 3 Gate 3：Leo Shell app key 密钥仪式

日期：2026-08-25

## 结论

长期 Leo Shell app key v1 已生成并完成一次外部恢复验证。它只用于签署
`io.github.leoaudio.shell`，不是 Xiaomi platform key、Android shared UID key、OTA key 或
dm-verity key。

- alias：`leo-shell-app-v1`；
- RSA 3072-bit / SHA256withRSA；
- 有效期：2026-08-25 至 2056-08-17；
- 证书 SHA-256：
  `4f81ed58df81e8d51b18f396bfe53ce09ba92396494afdc980e3f6746eccc7db`；
- 私钥主副本：Git 忽略的 `keys/`；
- 加密外部副本：独立外置介质的专用目录；
- 密码：macOS login Keychain 的独立 generic-password item；未写入 Git、日志或文档。

公开证书与机器可读 identity 位于 `manifests/`，可用于 verifier allowlist。私有 PKCS#12、密码、
签名 APK 与外部介质路径均不进入 Git。

## 恢复验证

外部 PKCS#12 与主副本 SHA-256 相同。重新挂载外置介质后，从 macOS Keychain 取回密码，直接
打开外部副本并确认 alias 为 `leo-shell-app-v1`、entry type 为 `PrivateKeyEntry`、证书
fingerprint 与公开 manifest 相同。

因此本次证明的是“当前主机 + 当前外部副本可以恢复”。用户仍需把密码另存到独立密码管理器或
纸质记录；否则主机与 login Keychain 同时丢失时，外部 PKCS#12 仍不可解密。

## 介质异常记录

外置 exFAT 介质在首次挂载和首次写入后各出现过一次目录读取超时。两次安全重挂载后，
`fsck_exfat -n` 均为 exit 0，文件系统报告 OK，最终小文件读取、SHA-256 和 keytool 解密验证
均通过。这说明当前副本真实可读，但介质响应稳定性不够理想。

在获得第二个可靠介质前，不应把该 U 盘称为唯一灾备。建议尽快把同一加密 PKCS#12 再复制到
第二只质量可靠的离线介质，并再次做独立回读；这不改变 app identity。

## 签名结果

Gate 3 release APK 已用该 key 同时生成 v1 和 v2 签名。Android 7 / API 24 验证选择 v2 并通过；
强制 API 18 的兼容性检查选择 v1 并通过。最终 verifier 同时检查 APK identity、Manifest、单 dex、
无 Kotlin/native/嵌入载荷、唯一 signer 和登记 fingerprint。
