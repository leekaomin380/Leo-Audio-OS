# Scripts

## `analyze-audio-elf-deps.py`

Recursively maps `DT_NEEDED` dependencies for the stock audio HAL and its supporting
services. It also records library names embedded in the explicit seed binaries as strings
(possible `dlopen` or plugin edges), and libraries observed in captured process maps. A
string reference is deliberately labelled as a candidate rather than a confirmed runtime
dependency; each runtime edge retains the process name that supplied the observation.
Embedded `/system/...`, `system/...` and `system/vendor/...` paths are normalized before
architecture-aware resolution, so an absolute string path is not misreported as missing.

The expanded stock system tree and the detailed TSV output belong under
`resources/private/`, which is excluded from Git. Example:

```sh
python3 scripts/analyze-audio-elf-deps.py \
  --system-root resources/private/stock-system-tree \
  --runtime-maps resources/private/runtime-states/20260824-152246-U0-v2/process-maps.txt \
  --runtime-maps resources/private/runtime-states/20260824-153316-H1/process-maps.txt \
  --output resources/private/analysis/audio-elf-dependencies.tsv
```

## `verify-audio-compat-manifest.py`

Checks every exact file hash in the public compatibility manifest against a user-extracted
stock system tree. It does not copy or publish the proprietary inputs:

```sh
python3 scripts/verify-audio-compat-manifest.py \
  --manifest manifests/audio-compatibility-v0.1.tsv \
  --system-root resources/private/stock-system-tree
```

## `unpack-android-boot.py`

Read-only extractor for the legacy Android boot format used by stock `leo`. It validates
all section bounds, separates the compressed kernel payload from a concatenated DTB chain,
decompresses gzip kernel and ramdisk payloads, and records hashes and offsets in
`metadata.json`.
The input image and extracted output must remain under `resources/private/`:

```sh
python3 scripts/unpack-android-boot.py \
  --boot resources/private/stock-rom/.../images/boot.img \
  --output resources/private/stock-boot-analysis
```

## `collect-kernel-config-evidence.sh`

Collects a privacy-limited, read-only snapshot of runtime facts that can confirm selected
kernel options when the stock kernel does not expose IKCONFIG. It requires exactly one
authorized, rooted `leo` and writes only to the ignored private evidence directory:

```sh
scripts/collect-kernel-config-evidence.sh
```

## SELinux audio audit

Build the local Linux analysis image once, then decode the private stock policy and collect
the corresponding live labels. The container receives the policy through a read-only bind
mount; neither script changes device policy or SELinux mode:

```sh
docker build -t leo-audio-os-selinux-audit:bookworm tools/selinux-audit
scripts/analyze-selinux-audio-policy.sh
scripts/collect-selinux-audio-runtime.sh
```

The live collector also records any currently open ALSA PCM parameters and filters retained
kernel AVC messages to the four audio-support source domains. An empty
`audio-domain-avc.txt` means no matching denial was present in the retained kernel log; it
does not prove that older, rotated-out messages never existed.

## `verify-audio-classification.py`

Validates the v0.2 public component manifest: exact columns, unique component IDs, approved
classification/action vocabulary, required evidence fields, and basic safety invariants.

```sh
python3 scripts/verify-audio-classification.py
```

本目录将保存只读采集、依赖分析、构建、校验、签名和恢复工具。任何执行分区写入的
工具都必须默认拒绝运行，直到型号、构建、哈希、目标分区和恢复材料全部通过检查。

## Phase 3 Gate 0

- `inspect-stock-fastboot-rom.py`：只读校验锁定 ROM 的文件名、SHA-256、tar 路径、必需
  成员、Android sparse header、system 物理容量和 persist 不写边界；
- `roundtrip-stock-system.py`：执行 sparse → raw → sparse → raw，并要求两个 raw 镜像
  逐字节哈希相等。它不进行 ext4 文件级重建，也不调用 fastboot。
- `extract-stock-system-raw.py`：从已核验 ROM 提取 system sparse 并展开为私有 raw ext4
  输入；展开完成即删除临时 sparse 文件；
- `audit-ext4-primary.sh`：在缓存的、无网络、只读 Linux 容器中运行 `e2fsck -f -n`、
  `dumpe2fs` 与 `debugfs`。它不挂载镜像，产出 Gate 1 主证据；
- `verify-stock-ext4-source.py`：只对 profile 锁定的原厂 raw 接受已裁定的 Android 7
  inode bitmap padding 偏差。raw hash、geometry、完整 fsck 输出或 padding 任一不符即失败，
  且该例外不得用于 Gate 2 产物。
- `collect-ext4-semantic.py`：不挂载镜像，直接解析 ext4 inode、extent、目录项和 xattr，
  写入内容哈希与原始安全元数据清单；遇到未实现的 ext4 结构会失败，不会静默漏项。
- `verify-ext4-semantic-manifest.py`：校验私有语义清单的路径编码、顺序、类型、摘要统计，
  并逐项对照公开音频兼容性 manifest 的原厂文件哈希。
- `audit-ext4-kernel-view.sh`：仅在隔离 Linux 容器中临时以 `ro,noload` 挂载 raw image，
  用内核 `lstat`/xattr 视图生成第二份清单，并要求与主清单逐字节一致后才通过。
- `derive-android-metadata.py`：从原始语义清单导出可审阅的 `fs_config` 候选与实际
  SELinux 标签表；它不替代原始 `file_contexts` 策略来源。

## Phase 3 Gate 2

- `generate-gate2-android-metadata.py`：从 Gate 1 私有语义清单生成完整 canned `fs_config`
  与封闭世界 `file_contexts`；root 使用 canned parser 所要求的空路径记录；
- `verify-gate2-selinux-lookups.sh`：以构建器内相同 libselinux 对全部路径、类型和标签做
  3923 条逐项 lookup 验证；
- `extract-gate2-system-staging.sh`：直接通过 ext4 inode 只读提取内容树，避免 Android 文件
  权限妨碍内核挂载读取；不复制 xattr/ACL，后续由 Gate 1 清单重建；
- `verify-gate2-staging.py`：逐一验证 staging 文件内容 SHA-256、符号链接目标、类型和路径；
- `materialize-gate2-staging-times.py`：在已验证 staging 上精确写入 Gate 1 mtime；
- `build-gate2-ext4-candidate.sh`：从已验证 staging 和 metadata 构建一份
  `development-unverified` raw ext4 候选；通过 builder 内受限 libext2fs helper 精确建立
  6552-block internal journal；不生成 sparse、不调用设备接口；
- `normalize-gate2-ext4.sh`：对候选 raw ext4 执行已验证的 post-build 归一化并运行 `e2fsck`。
- `build-gate2-development-container.py`：将已验证 Gate 2 raw ext4 置于精确 system 分区
  起点、物化零填充的开发态尾部，再执行 `raw → Android sparse → raw` 全字节回环验证；明确
  不读取或复用原厂 dm-verity/FEC 尾部，也不调用设备接口。

`tools/gate2-builder/` 是锁定的 Linux 构建器定义。Gate 2 的所有脚本只处理私有镜像和
staging，禁止调用 ADB、fastboot 或任何设备写入接口。

## Phase 3 Gate 3

- `verify-gate3-shell-apk.py`：拒绝不满足 Gate 3 package/version、最小 Manifest、单 dex、
  零 Kotlin/native/嵌入式载荷与独立 v1/v2 signer 的 release APK；
- `create-gate3-shell-overlay.py`：仅在上述签名验证通过后，生成包含
  `/app/LeoShell` 与 `LeoShell.apk` 的私有二路径 overlay；
- `generate-gate3-semantic-input.py`：将已验证 overlay 加到冻结 Gate 2 语义清单，拒绝任意
  第三路径、原有路径碰撞、错误 DAC/SELinux metadata 或 APK hash。
- `verify-gate3-staging.py`：逐项检查 Gate 3 staging 的路径、类型、内容、链接和 mtime；
- `compare-gate3-semantic.py`：只接受二路径新增，原厂属性必须精确不变，并把 inode allocator
  地址与 `/app` link count 的可解释变化单独登记；
- `verify-gate3-apk-provenance.py`：证明签名前后所有非签名 APK 成员名称和解压字节相同。
- `verify-gate3-static-evidence.py`：冻结前总门禁；重新哈希两份 ext4、完整分区与 sparse，核对
  APK 来源、metadata、音频闭包、MIUI Launcher、superblock 差异和 Git 私有材料边界。

这些工具不创建密钥、不改 boot/verity/FEC、不调用 ADB、fastboot 或 recovery。它们只为 Gate 3
的后续 ext4 重建提供经签名验证的私有输入。

## Phase 4 Gate 0–2

- `inspect-legacy-system-verity.py`：只读解析 raw system 的 ext4 几何、legacy dm-verity tree/
  metadata 与 FEC；默认重算完整 Merkle tree，从 boot ramdisk 的 524-byte mincrypt 公钥重建
  RSA SPKI，验证 table signature、root hash、tree 全字节和 FEC payload hash；
- `inspect-legacy-boot-signature.py`：严格计算 legacy boot/recovery 的签名边界，解析 Android
  BootSignature v1 DER footer，并用嵌入证书验证 target、authenticated length 与声明算法。默认
  拒绝无效签名；`--allow-invalid-signature` 只用于记录历史 development boot，不构成验收。
- `generate-legacy-verity-probe-key.py` 与 `generate-legacy-boot-probe-key.py`：只生成被 Git 忽略的
  一次性开发身份；输出明确禁止发布，不能替代正式离线密钥仪式；
- `build-legacy-verified-system.py`：用锁定 builder 生成 tree、metadata 与 FEC，组装完整 raw
  system 并立即调用独立 verifier；
- `build-legacy-project-boot.py`：只在原厂 cpio 的唯一 524-byte `verity_key` payload 中等长替换，
  保持 kernel/DTB/cmdline/地址不变，并生成可独立验证的 BootSignature v1；
- `verify-phase4-sparse-pair.py`：双构建 sparse 并执行 sparse→raw 全字节回环；
- `fault-inject-phase4-pair.py`：对 system/boot 的 8 个内容与密钥边界做 fail-closed 测试；
- `verify-phase4-release-set.py` 与 `fault-inject-phase4-release-set.py`：把 system、boot、公钥、证书、
  stock recovery 和 fallback 绑定成不可混配 tuple，并验证缺文件、换 boot、错 key/cert 与 hash
  mismatch 均被拒绝。verifier 永不代表用户授权写入。
- `generate-phase4-release-keys.py`：在两块独立外置物理介质上建立正式、分域且加密的 verity/boot
  密钥副本；口令只进入 macOS 登录钥匙串，脚本拒绝覆盖既有备份成员；
- `verify-phase4-release-key-backups.py`：在两块介质分别断开重连后，只读核验卷 UUID、物理盘独立性、
  manifest 全成员 hash 与钥匙串解密恢复，并产生不含口令和私钥内容的本地证据；
- 两个 legacy builder 的 `--formal-release` 模式必须同时验证正式 key manifest、重挂载报告和仅由
  环境变量传入的解密口令；缺任一门禁即在创建输出前失败。正式 builder 与总 verifier 仍固定输出
  `device_write_authorized=false`，不能替代用户临写确认。
- `backup-phase4-current-system.py`：在首次写入前，从唯一一台已授权、已启动且可获得 Root 的
  `leo` 只读流出完整 system block device；一次流同时写入两块 UUID 锁定且物理独立的外置介质，
  fsync 后再分别完整读回并核对预期大小与 SHA-256。脚本拒绝覆盖既有目录，不向手机写入，也不把
  ADB 枚举序列号写入 manifest。失败的 partial 文件保留供人工审计。

除明确标注的只读设备备份脚本外，上述构建与校验工具均不含 ADB/fastboot 调用。公开 profile 固定
AOSP `android-7.0.0_r1` 源码提交和文件 hash；probe 私钥与所有构建镜像均在 Git 忽略区。

## 当前工具

- `collect-audio-baseline.sh`：仅接受一台已授权、代号为 `leo` 且可获得 Root 的设备，
  采集系统身份、分区、音频文件索引与哈希、init 引用、服务、ALSA 和 AudioFlinger
  空闲基线。结果默认写入被 Git 忽略的 `resources/private/device-baselines/`，不采集
  设备序列号、账号或用户文件。
- `capture-audio-state.sh LABEL`：采集一次短时运行状态，用于比较未插耳机、插入耳机
  和 Spotify 播放三个状态。只读取属性、AudioPolicy、AudioFlinger、ALSA、mixer 与
  音频相关内核日志。
