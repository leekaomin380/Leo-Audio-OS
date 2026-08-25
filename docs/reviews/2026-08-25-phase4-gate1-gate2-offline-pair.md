# Phase 4 Gate 1/2：离线构建与配对审计

日期：2026-08-25

## 裁决

**Gate 1 与 development Gate 2 通过；正式密钥门禁未通过，设备写入仍被拒绝。**

锁定的 Android 7 legacy verified-boot builder 已两次逐字节复现原厂 Merkle tree 和 FEC。随后用
两把一次性、未加密、明确禁止发布的 probe key，完成 verified system、stock-derived project
boot 和 Android sparse 的双构建。独立 verifier、回环测试和负向测试全部通过。

## 锁定工具链

- builder image：
  `sha256:1dcbf603cec7f3546fb3edc3712142f1bb498cdc950404f76fa9edcdfdbdf935`；
- AOSP system/extras：`aa3f820033cfaf3a61d1e3cc617309ae652f0c4f`；
- AOSP system/core：`88f64719d75620d144af5bba39a00a3f178ae60a`；
- AOSP external/fec：`791afbe58ff9f55145c4adf632ab8cc9ca6e5686`。

提交冻结前又从原始 AOSP checkout 重新应用公开 compatibility patch 并重建镜像，得到
`sha256:9a9915a02f0ae92a870063d0cecbe28bbc9edcc9a296a001f56c5af7d9979845`。镜像层 hash 因 patch
文件本身的上下文和构建层 metadata 而变化，但三个实际执行文件与参考镜像逐字节一致：

- `build_verity_tree`：`913fc8064e5a26760832db7e731f5efc63718e78f96eb3b1bcfc2dfcd4d46725`；
- `fec`：`73de38bc4cbd5b4655c4b261e5937278bb6fd53b5bd0f8a015362b33caad74f6`；
- `gzip`：`d3afaebcb97bf6fa214a813d89b108f48955665ea596228340ec80580ee55a0e`。

原厂 tree SHA-256 `90bf3e38b94b6fa18e22a57a622d2ff5f43d1ae20f6090ee2794e4cf0c289e50`
和完整 FEC SHA-256 `515b2357a8b423326f6f3ee1baddf4990ef142411d39744890cc7011751d8e47`
均由两次构建逐字节复现。

## Development pair

| 成员 | SHA-256 | 结果 |
| --- | --- | --- |
| Gate 3 ext4 | `10857ee55fd85f485febd15407b58b4da6dc95ba2ef932826ef505d38342574c` | 两份相同 |
| verified system raw | `51f9cfb8bc54342256a596658ef17c50aea65ef567a60dc053168b720159ae24` | 两份相同、独立验签通过 |
| system sparse | `49e9c2cdc5217e2e94f6a02e4f7bc176988ffdcd06ecd5ac54999bcda0e11493` | 两份相同、raw 回环相同 |
| project boot | `772c5be02dc47780912c4c6c79dd4f982766483516947f7a663ab30643a616aa` | 两份相同、BootSignature 有效 |
| verity public key | `edc308ba5cfb572c34393fd75da95a5e31d06194f8a9d7c16d82edee70986fa2` | system 与 boot 直接绑定 |
| boot certificate | `4041e2804879ab300053973ddc9ba75591ca5dee60abd3e3d5267f39c575eba0` | SHA256withRSA `/boot` |

project boot 的原厂 kernel section hash 仍为
`86e4e2af5441c95992219eb556ec839bfb7ce4aad8f34dc1bea9fcf99dcf0976`。36 份 appended DTB、cmdline、
地址和 OS version/patch level 均未改变；原始 cpio 只在 `verity_key` 的 524-byte payload 内改变。

## Fail-closed 证据

内容层 8 项故障全部拒绝：ext4、tree、metadata、FEC、错误 verity key、boot signed region、footer、
target。release-set 层 7 项故障全部拒绝：缺 system、换成 stock boot、错 key、错 certificate、缺
stock recovery、缺 fault report、manifest hash mismatch。

完整 tuple verifier 返回：artifact integrity、system/boot cryptographic pair 和 rollback artifacts
均有效；同时明确返回 `release_key_gate=false`、`device_write_ready=false` 和
`device_write_authorized_by_verifier=false`。

## U 盘边界

用户要求不删除 U 盘现有内容。测试只新建
`Leo-Audio-OS-Phase4-Workspace-20260825-2042`，未删除、移动或覆盖其他目录。该 exFAT 介质较慢，
且此前有过间歇读取超时记录，因此只承担大体积 development sparse/roundtrip 工作区，不能成为
正式私钥的唯一灾备。工作区中的大文件仍是私有构建物，不进入 Git。

## 剩余硬门禁

1. 准备第二个独立且可靠的离线介质；
2. 生成正式、分域的 `leo-verity-v1` 和 `leo-boot-v1`，完成两个加密副本与恢复回读；
3. 用正式密钥重新双构建并冻结 release-set；
4. 用户在场时进行设备身份、电量、解锁状态与当前分区的只读预检；
5. 临时启动 exact stock recovery，验证救援路径；
6. 在首次 `system` 写入前再次取得用户明确确认。
