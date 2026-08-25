# 14：Phase 4 旧式 Verified Boot 与恢复契约

## 1. 本阶段结论

`leo` 的原厂链不是 AVB 2.0，而是 Android 7 的两套旧式机制叠加：system 由
`dm-verity metadata + RSA-2048 mincrypt 公钥 + FEC` 保护；boot/recovery 文件末尾另带
Android BootSignature v1。我们已经能够在不连接设备的情况下独立解析并验证原厂完整链，
因此不再需要通过“刷进去看看”反推格式。

本契约只授权本机离线构建与故障注入。项目 verity key、配套 boot、FEC、恢复演练和 release-set
全部闭合前，仍禁止写入手机。

## 2. 已经用真实原厂镜像证明的结构

原厂 raw system 的 425984 个 4096-byte block 精确闭合为：

| 区域 | 起始 block | blocks | SHA-256 |
| --- | ---: | ---: | --- |
| ext4 | 0 | 419329 | `786cd054e489d135cb47ab402cbf518014b0592d1afbaad44864d92154030293` |
| dm-verity tree | 419329 | 3304 | `90bf3e38b94b6fa18e22a57a622d2ff5f43d1ae20f6090ee2794e4cf0c289e50` |
| metadata | 422633 | 8 | `3570a6cfeb020c930a56eaffea777c169188c381a0f32d9fb416e466e3c9ab64` |
| FEC payload | 422641 | 3342 | `8d781dad8f43912141fe890e997045e868dcb0d4a5fb77a31a2a6bf6611f106b` |
| FEC footer | 425983 | 1 | `493fdb8a476b943dde362a813b173ff12aaa9f7d9ed974742b0c31be14259fa1` |

独立 verifier 已经完成四项密码学或全字节证明：

1. 从 419329 个 ext4 block 重新计算 3277、26、1 block 的三层 Merkle tree；生成 tree 与
   原厂 13533184 bytes 逐字节相同，root hash 为
   `ae95fea4b1220ff6fb08f3642d4e0ca02258a258b45f64b355ae411be6c56626`；
2. 从 boot ramdisk 的 524-byte `verity_key` 重建 RSA-2048 SPKI，验证 metadata 中对精确
   236-byte table 的 `SHA256withRSA` 签名有效；
3. 验证 FEC footer 首尾两份 64-byte header 相同，`roots=2`，input/FEC size 精确闭合，且
   header 中的 payload SHA-256 与 13688832-byte FEC 数据一致；
4. 验证 stock boot 和 stock recovery 的 BootSignature v1 都有效，target 分别为 `/boot` 与
   `/recovery`，都使用 `SHA256withRSA`，并嵌入同一张原厂证书。

这也解释了原厂 ramdisk 中 `/system ... wait,verify` 的含义：fs_mgr 从 system 尾部找到 signed
table，用 ramdisk 公钥验证 table，再把 table 交给 dm-verity；libfec 同时读取末尾 FEC 纠错数据。

## 3. Magisk boot 新发现与裁决

当前设备曾成功临时启动、后来持久化的 Magisk boot 仍保留 BootSignature v1 外壳，但其 footer
声明 `sha1WithRSAEncryption`，实际签名字节却只以 `SHA256withRSA` 验证通过。因此该 footer 按
AOSP BootSignature 语义是无效的。

实机能够启动它，构成以下有限证据：解锁状态下的这台设备没有因为该签名不一致而拒绝启动。
它不证明所有 leo bootloader 都忽略签名，也不把无效签名变成可发布格式。项目 boot 必须使用
声明与实际均为 `SHA256withRSA` 的有效 BootSignature，并先通过 `fastboot boot` 临时启动验证。

## 4. 锁定的 Android 7 实现

工具行为固定到 AOSP `android-7.0.0_r1`，而不是跟随 master 漂移：

- [`build_verity_tree.cpp`](https://android.googlesource.com/platform/system/extras/+/android-7.0.0_r1/verity/build_verity_tree.cpp)
  定义 `SHA256(salt || block)`、4096-byte block 和 tree level 排列；
- [`build_verity_metadata.py`](https://android.googlesource.com/platform/system/extras/+/android-7.0.0_r1/verity/build_verity_metadata.py)
  定义 `0xb001b001`、version 0、256-byte signature 和 8-block metadata；
- [`VeritySigner.java`](https://android.googlesource.com/platform/system/extras/+/android-7.0.0_r1/verity/VeritySigner.java)
  与 [`Utils.java`](https://android.googlesource.com/platform/system/extras/+/android-7.0.0_r1/verity/Utils.java)
  定义 RSA key 对 table 使用 `SHA256withRSA`；
- [`generate_verity_key.c`](https://android.googlesource.com/platform/system/extras/+/android-7.0.0_r1/verity/generate_verity_key.c)
  定义 RSA-2048 与 524-byte Android mincrypt public-key 格式；
- [`fec`](https://android.googlesource.com/platform/system/extras/+/android-7.0.0_r1/verity/fec/)
  定义 RS(255,253)、2 roots、FEC payload 和双 header footer；
- [`BootSignature.java`](https://android.googlesource.com/platform/system/extras/+/android-7.0.0_r1/verity/BootSignature.java)
  定义 boot/recovery 签名边界、target、certificate 和 authenticated length；
- [`fs_mgr_verity.cpp`](https://android.googlesource.com/platform/system/core/+/android-7.0.0_r1/fs_mgr/fs_mgr_verity.cpp)
  定义启动时 public key、metadata、libfec 与 dm-verity 的消费路径。

源文件 hash 与三个 AOSP 仓库提交均固定在
[`phase4-legacy-verified-boot-profile-v0.1.json`](../manifests/phase4-legacy-verified-boot-profile-v0.1.json)。

## 5. 项目密钥分域

Phase 4 建立两把独立 RSA-2048 key，不复用 AOSP test key，也不声称拥有 Xiaomi 私钥：

| key ID | 私钥用途 | 公开材料 | 安全意义 |
| --- | --- | --- | --- |
| `leo-verity-v1` | 签名 system verity table | 524-byte mincrypt key、SPKI/cert 指纹 | boot 中 fs_mgr 真正用它决定 system 是否可信 |
| `leo-boot-v1` | 生成 BootSignature v1 | X.509 cert 与指纹 | 保证发布物离线可验；解锁 bootloader 下不视为硬件 root of trust |

私钥只在被 Git 忽略的签名工作区短时出现；长期主副本必须加密并离线保管。公开仓库只提交公钥、
证书、指纹、算法和 ceremony 报告。未完成两个独立离线副本及恢复读取测试前，不生成正式 key。

platform、APK、verity、boot 和将来的 OTA key 必须分域。Gate 3 的 LeoShell app key 不能用于
verity 或 boot。

## 6. system 与 boot 的原子兼容契约

“原子”指发布物不可混配，不表示 fastboot 可以原子写两块 NAND。每个 release-set 必须绑定：

- Gate 3 ext4 hash、完整 verified system raw hash、sparse hash与回环 hash；
- root hash、salt、精确 table、metadata signature、FEC hash；
- `leo-verity-v1` public-key hash；
- stock-derived project boot hash、ramdisk hash、BootSignature cert/hash；
- exact stock boot、exact stock recovery、已验证 development boot fallback；
- device/build identity、允许写入分区、写入顺序、验证命令与回滚命令。

verifier 必须拒绝以下任一组合：

- project system + stock `wait,verify` boot；
- project system + 另一版 project boot/key；
- zero-tail development system + project `wait,verify` boot；
- 修改过 kernel、DTB、cmdline 或除 `verity_key` 外未声明 ramdisk 文件的 boot；
- 缺 recovery/rollback hash、缺双构建证明或缺故障注入报告的 release-set。

## 7. boot 构建约束

正式 project boot 从 exact stock boot 派生，只允许：

1. 将 ramdisk `/verity_key` 替换为 `leo-verity-v1` 的 524-byte public key；
2. 保持 `/system` 的 `wait,verify`；
3. 保持 kernel section、36 个 appended DTB、cmdline、page size、地址、OS version/patch level不变；
4. 确定性重建 gzip-cpio ramdisk和 legacy boot header；
5. 用 `leo-boot-v1` 对 `/boot` 生成有效的 BootSignature v1 `SHA256withRSA` footer；
6. 用独立 verifier 验证 footer 后，才进入 release-set。

第一台原型不修改 recovery。项目先把 exact stock recovery 作为救援根；自建 recovery 属于后续
独立 gate，不能与第一次 system/boot 写入同时引入。

## 8. 离线门禁和故障注入

在任何设备动作前必须完成：

1. 固定 Linux builder 产出 Android 7 `build_verity_tree`、`fec`、metadata signer 与 boot signer；
2. 用原厂 system 复现 tree/FEC，至少 tree 全字节、FEC 全字节和 metadata signature verification
   通过，证明工具链与设备格式相符；
3. 对 Gate 3 ext4 独立构建两份 verified system，raw/sparse 全字节可复现；
4. 独立重建两份 project boot，除签名证书固定材料外全字节可复现；
5. 分别翻转 ext4、tree、metadata table/signature、FEC、boot `verity_key` 和 BootSignature 字节，
   verifier 必须逐项拒绝；
6. 对 release-set 做缺文件、换版本、错 key、错 target 和 hash mismatch 负向测试；
7. exact stock recovery 与 stock boot 在本机双重哈希通过，并在设备动作前临时启动 recovery，
   实测按键/触摸、ADB 或 sideload、数据不清除和返回 fastboot。

## 9. 首次写入的安全顺序（尚未授权执行）

当全部门禁通过后，第一次试验不先持久化 boot：

1. 设备身份、电量、解锁状态、当前 boot/system hash 与 USB 稳定性只读复核；
2. 临时 `fastboot boot` exact stock recovery，证明救援入口；
3. 回到 fastboot，只写 release-set 中的 verified project system；
4. 不重启到常规 boot，先 `fastboot boot project-boot.img` 临时启动；
5. 验证 dm-verity、系统、LeoShell、Wi-Fi、Spotify、有线 HiFi 与重启路径；
6. 只有临时 boot 连续通过后，才单独请求确认是否把同一 hash 的 project boot 持久写入；
7. 任一步异常：保持或恢复 development boot，或进入 stock recovery/fastboot，把 exact stock
   boot/system 恢复。不得运行全量 `flash_all`，不得触碰 userdata、persist、modem、tz 或 aboot。

这个顺序把“新 system 无法启动”和“新 boot 无法启动”拆开：boot 尚未持久化时，失败仍可由
现有 development boot 或 stock recovery 接管。

## 10. Gate 0–2 裁决与下一步

Gate 0 的结构审计已通过：原厂 chain、stock recovery、BootSignature 和独立 verifier 均已闭合。
Gate 1 的锁定 Linux builder 已两次逐字节复现原厂 verity tree 与 FEC。Gate 2 使用两把一次性、
未加密且明确禁止发布的 probe key，完成两份 verified system、两份 sparse、两份 stock-derived
project boot 的逐字节复现；raw/sparse 回环、system/boot 配对、8 项内容故障和 7 项 release-set
故障均通过 fail-closed 测试。

这些结果证明构建链可用，不把 probe tuple 变成可刷版本。下一步必须先完成正式
`leo-verity-v1`/`leo-boot-v1` 密钥仪式、两个独立离线加密副本及恢复回读，然后用正式密钥重建
同一语义内容。随后才允许在用户在场时执行 recovery 临时启动与设备只读预检。
