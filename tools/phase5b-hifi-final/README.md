# 最终HIFI离线验收工具

HAL在冻结7f4cac748b6f62897294cdaece9d1aec27e1e927源码上应用原phase5b-m3/0001..0005，然后phase5b-hifi-ui/0006、0007。SystemUI在公开候选f6fd72a3d22a31c3cb120cc8b564114006c606da上按0001、0002、0003应用。不得把公开候选提交当完整目标ROM manifest。

主机回归：python3 tests/run.py /absolute/patched/SystemUI /absolute/patched/HAL。Python工具测试：python3 -m unittest discover -s tests -p 'test_*.py'。Java需要JDK，C需要clang及可用sanitizer；run.py支持JAVA_HOME。完整API/资源验证需要私有设备接口JAR，未入库；不得把no-code接口JAR作为产品。

三个Python工具为readiness、单HAL镜像副本与SHA256SUMS交付检查器；使用边界见docs/phase5b-hifi-final。server-power-policy-20260831是已部署服务器电源策略快照，不自动执行远程变更。

ARM诊断复现使用scripts/verify-hifi-schema3-link.sh，并提供冻结Gate2工作区、headers及全新run目录；HIFI_UI_PATCH指向0006，HIFI_SAFETY_PATCH指向0007，M3_FEATURE=on/off。该脚本有本机工具链默认路径，迁移主机须核验，不是Android目标正式构建。旧verify-hifi-ui-link.sh仅保留schema2历史复现。
