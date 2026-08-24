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

## 当前工具

- `collect-audio-baseline.sh`：仅接受一台已授权、代号为 `leo` 且可获得 Root 的设备，
  采集系统身份、分区、音频文件索引与哈希、init 引用、服务、ALSA 和 AudioFlinger
  空闲基线。结果默认写入被 Git 忽略的 `resources/private/device-baselines/`，不采集
  设备序列号、账号或用户文件。
- `capture-audio-state.sh LABEL`：采集一次短时运行状态，用于比较未插耳机、插入耳机
  和 Spotify 播放三个状态。只读取属性、AudioPolicy、AudioFlinger、ALSA、mixer 与
  音频相关内核日志。
