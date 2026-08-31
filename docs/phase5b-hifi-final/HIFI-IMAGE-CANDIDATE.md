# MoKee 单 HAL 离线镜像副本工具

此工具在本地生成诊断副本，不 mount 手机、不安装、不刷机。原 raw 只读，冻结 SHA256 为 7238ee916246f6ac4564d7386639494323bae01b67eb8bed6b0168b2d47689c3。

唯一内容修改路径：`/system/vendor/lib/hw/audio.primary.msm8994.so`。无 payload 或 payload 与原 HAL 相同则不运行 debugfs 写入，副本必须与源逐字节相同，结论 NO_OP_ONLY。

CLI：`python3 tools/hifi_image_candidate.py --source SOURCE.raw --source-sha256 HASH --collector collect-ext4-semantic.py --output NEW_DIR --builder-image sha256:LOCAL_IMAGE_ID [--payload HAL.so --payload-sha256 HASH]`。仅适用于已冻结的 MoKee 镜像；collector 必须使用本项目审计版本，SHA256 d8ee575c630683ef90d203bdf4d0825f4c1db7cf49d0ef9ccd3617c58cb5d117。

已验证缓存镜像 ID：sha256:e4c6224db7874deb9743a936101988a86d0daedb3d48cd94c6b640aac3bffb14。它提供 /opt/e2fsprogs/sbin/debugfs 和 e2fsck（1.46.6，链接 libext2fs 1.47.0）。容器显式指定入口、禁网、禁止自动拉取、只读根、drop ALL、512MiB 内存和64MiB临时空间；仅挂载输入快照只读、此轮新输出可写。它不是对整个宿主机的安全隔离证明。

拒绝输入符号链接/设备节点、已有输出、来源哈希或 payload 哈希不符；按输出文件系统预算完整拷贝加10GiB余量。先 APFS CoW，失败才普通拷贝；失败目录保留。

替换后恢复 uid/gid（含高位）、mode、nlink、flags、generation、extra_isize、atime/ctime/mtime/crtime 及 extra、逐字节 xattr。通过只读 collector 对比4570个路径的内容、元数据、符号链接，补充完整 inode 时间与高位身份字段；只允许目标的内容/size/inode编号变化。不豁免父目录时间；不声称验证了其他文件的全部物理块布局。

验证 raw 长度、UUID、label、block size/count、inode size/count、features、hash seed 不变；源哈希前后不变、payload 回读一致、e2fsck -f -n=0。结果与命令、日志位于 report/。ARTIFACT_VALIDATED_NOT_DEPLOYED 仅代表离线文件系统检查通过，不等于 HAL 能加载，不是完整系统包、verified-boot发布包或设备操作许可。
