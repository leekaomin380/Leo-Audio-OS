# Phase 4：正式 release-set 离线冻结审计

日期：2026-08-26

## 裁决

**正式 release-set 的离线构建门通过；设备写入尚未授权。**

`leo-verity-v1` 与 `leo-boot-v1` 使用独立 RSA-2048 身份，加密私钥口令只保存在 macOS 登录
钥匙串。两份加密备份位于两块具有不同卷 UUID 的独立外置物理介质。两块介质分别断开、重连后，
全部 9 个 manifest 成员均完成逐文件 SHA-256 读回，两把私钥均从钥匙串成功恢复解密。

## 正式身份

- verity mincrypt 公钥 SHA-256：
  `3cf27ca96948c44721e34eb5732c992a073cdda71ae20df4a5c6065a9c6454b3`；
- boot certificate DER SHA-256：
  `6ff446b8f360f6970632ad9d3c7aecff12d8a001f428f54e59daf806b44f7d72`；
- key manifest SHA-256：
  `11e5c78f151e8d2854f810d2bb88e3739e7bbc562d9e60cc012d3a0f9b57eab6`；
- remount evidence SHA-256：
  `72235b92e23377b2d9982b178e33440355db8ca099b5458392be333481388e22`。

私钥、钥匙串口令、包含本机路径的私有报告和镜像均不进入 Git。

## 双构建结果

| 成员 | SHA-256 | 结果 |
| --- | --- | --- |
| Gate 3 ext4 | `10857ee55fd85f485febd15407b58b4da6dc95ba2ef932826ef505d38342574c` | 冻结输入 |
| verified system raw | `e18a6fc83c59e09415d4a802a052c66fccf46e420b1f25f752e85546f8affad4` | A/B 逐字节一致 |
| Android sparse | `afa12b23e4570f96cc5e4ee70cf754779c75cf834a9d61f481f08d1a96e21eb1` | A/B 一致、raw 回环一致 |
| project boot | `dfca241d75d494e0d85502d1368a3475f0e2576dd69b28274fcf4532a2779685` | A/B 逐字节一致、BootSignature 有效 |

system 继续使用冻结 salt，Merkle root 为
`d3fa2c8d1393dabfb6ca1cf0b995bb3b93cecd884459d3f8af0a5aaf5877cd7a`。project boot 的原厂
kernel SHA-256 仍为 `86e4e2af5441c95992219eb556ec839bfb7ce4aad8f34dc1bea9fcf99dcf0976`；
DTB、cmdline、地址和 cpio 长度不变，只替换唯一的 524-byte `verity_key` payload。

## 回滚闭环

- exact stock boot：`bc64d15c26c53644e0d66e8dd3dc9e9c52bf2d4e4267d3c9f71ee90455e567d5`；
- exact stock recovery：`4aafc56e0feb5be5213a58e9bc770730d9cf3746a9b4ee31bc79d6484af461e0`；
- stock system sparse：`03960aeded4f6b3c7802109ff74aedec67c5de15841bf175ace66a89cde36003`；
- stock system raw：`ec6edfd79adb1f6053adcc6fcb1927fabd93fe3756d9e7c7af8a7abd0dcd3e7d`。

总 verifier 在临时目录中将 exact stock sparse 展开，所得 raw 与上述原厂 raw 逐字节一致；原厂
dm-verity metadata 签名、Merkle tree 和 FEC 证据也被正式 manifest 绑定。

## Fail-closed 结果

- 8 项内容故障全部拒绝：ext4、tree、metadata、FEC、错 verity key、boot signed region、footer、
  target；
- 7 项 release-set 故障全部拒绝：缺 system、换 stock boot、错 key、错 certificate、缺 stock
  recovery、缺 fault report、manifest hash mismatch；
- 正式总 verifier 返回：`artifact_integrity_valid=true`、`pair_cryptographically_valid=true`、
  `rollback_artifacts_present=true`、`release_key_gate=true`、`formal_evidence_valid=true`；
- 同时保持：`device_write_ready=false`、`device_write_authorized_by_verifier=false`。

公开正式 manifest 为 `manifests/phase4-release-set-v1.json`，SHA-256：
`ec1f23178e7825b28ac1dbb6f348a7eed97b7f3776e69b1a58d63ab4d8123e5a`。

## 剩余人工门禁

1. 在 fastboot 中只读核验设备代号、解锁状态、电量、连接稳定性与分区几何；
2. 临时启动 exact stock recovery，实测显示、输入与返回 fastboot 的救援路径；
3. 展示唯一目标 `system`、正式 sparse hash、预计耗时和回滚命令；
4. 在写入前单独取得用户当场明确确认。

任一项异常即停止。首次写入不得触碰 userdata、boot、recovery、persist、modem、tz、aboot 或
其他分区；project boot 只允许在 system 写入后临时启动，持久化 boot 是第二次独立决定。
