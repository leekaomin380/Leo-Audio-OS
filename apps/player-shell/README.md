# Leo Player Shell

Phase 2 的独立 Android 原型，最低兼容 Android 7.0 / API 24。工程只使用 Android
Framework API，不引入运行时第三方依赖。

## 两种构建变体

- `safePreviewDebug`：普通应用入口，不声明 `HOME`。这是 Gate B 前唯一允许安装的变体；
- `homeCandidateDebug`：声明 `HOME` 候选，但不会自动成为默认桌面。只有 Gate C 通过后才
  允许安装和选择。

初版不会自动启动 Spotify，不会修改默认 HOME，不请求权限，也不会启用原厂桌面出口。
维护页只是行为骨架，本地认证完成前不能视为安全维护模式。

## 构建

项目锁定的 Gradle Wrapper 和 Android Gradle Plugin 版本见构建文件。首次构建需要能够
访问 Google Maven；后续可以使用已缓存依赖离线构建。正式构建基线使用 JDK 17；当前
开发机的更新版 JDK 只用于早期编译验证，不作为最终可复现环境声明。

```sh
./gradlew :app:assembleSafePreviewDebug
```

构建产物必须先经过仓库的源清单与 APK 清单验证，之后才能进入实机安装 Gate B。

```sh
python3 ../../scripts/verify-player-shell-source.py
python3 ../../scripts/verify-player-shell-apks.py
```
