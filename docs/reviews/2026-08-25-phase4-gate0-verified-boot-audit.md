# Phase 4 Gate 0 verified-boot 审计

日期：2026-08-25

## 裁决

**Gate 0 通过；设备写入仍未授权。**

我们已经从 exact stock ROM 独立验证 system 的完整 Merkle tree、metadata RSA signature、FEC
footer/payload hash，以及 boot/recovery 的 Android BootSignature v1。exact stock recovery 已回收到
项目忽略区并重新核对 SHA-256。这足以进入离线工具链复现，不足以进入手机写入。

## 核心证据

- stock system raw：`ec6edfd79adb1f6053adcc6fcb1927fabd93fe3756d9e7c7af8a7abd0dcd3e7d`；
- 重算 Merkle tree 与原厂 13533184 bytes 全字节一致；
- metadata signature 对 boot ramdisk `verity_key` 验证有效；
- FEC 两份 footer header 相同，payload hash、input size 和分区边界闭合；
- stock boot BootSignature v1 有效：`/boot`、SHA256withRSA；
- stock recovery `4aafc56e0feb5be5213a58e9bc770730d9cf3746a9b4ee31bc79d6484af461e0`，
  BootSignature v1 有效：`/recovery`、SHA256withRSA；
- 已成功启动的 Magisk boot footer 声明 SHA1，实际只以 SHA256 验证，按 AOSP 语义无效；因此
  只能作为解锁设备开发 fallback，不能成为项目签名模板。

私有完整报告位于 `resources/private/phase4-gate0/`，未进入 Git。

## 新增 verifier

- `inspect-legacy-system-verity.py`：从 ext4 superblock 推导几何，重算 tree/root，重建 mincrypt
  RSA public key，验证 metadata signature 与 FEC footer/hash；
- `inspect-legacy-boot-signature.py`：严格解析 legacy boot boundary 和 BootSignature DER，验证
  target、authenticated length、certificate 和 signature algorithm，并能将无效 development
  footer 仅作为 inspection 结果输出。

## 停止条件

- 不能用锁定 Android 7 工具复现原厂 tree 或 FEC；
- boot 重打包改变 kernel/DTB/cmdline 或未声明 ramdisk 文件；
- project key 只有一个副本、没有离线恢复读取测试或混入 Git；
- release-set 允许混配 system 与 boot；
- stock recovery 无法临时启动，或 fastboot 救援路径不稳定；
- 任何计划要求在工具链复现前写入设备。
