#!/bin/sh
# Offline APK build: aapt2 + javac + d8 + apksigner. No Gradle, no network.
# Stage 1 artifact: an ORDINARY app. Not privileged, not platform-signed.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SDK=${ANDROID_SDK:-$HOME/Library/Android/sdk}
BT=$SDK/build-tools/36.0.0
JAR=$SDK/platforms/android-36/android.jar
JDK=${JAVA_HOME:-/opt/homebrew/opt/openjdk}
export JAVA_HOME="$JDK"
export PATH="$JDK/bin:$PATH"
OUT=$HERE/build
rm -rf "$OUT"; mkdir -p "$OUT/res" "$OUT/gen" "$OUT/classes"

echo "[1/6] aapt2 compile"
"$BT/aapt2" compile --dir "$HERE/res" -o "$OUT/res.zip"

echo "[2/6] aapt2 link"
"$BT/aapt2" link -o "$OUT/base.apk" -I "$JAR" \
  --manifest "$HERE/AndroidManifest.xml" \
  --java "$OUT/gen" --min-sdk-version 29 --target-sdk-version 29 \
  "$OUT/res.zip"

echo "[3/6] javac"
find "$HERE/java" "$OUT/gen" -name '*.java' > "$OUT/sources.txt"
"$JDK/bin/javac" -source 8 -target 8 -nowarn \
  -bootclasspath "$JAR" -classpath "$JAR:$BT/core-lambda-stubs.jar" \
  -d "$OUT/classes" @"$OUT/sources.txt" 2>&1 | grep -v 'bootstrap class path\|source value 8\|target value 8\|deprecat' || true

echo "[4/6] d8"
find "$OUT/classes" -name '*.class' > "$OUT/classes.txt"
"$BT/d8" --min-api 29 --output "$OUT" --lib "$JAR" @"$OUT/classes.txt"

echo "[5/6] package + align"
cp "$OUT/base.apk" "$OUT/unsigned.apk"
(cd "$OUT" && zip -q -u unsigned.apk classes.dex)
"$BT/zipalign" -p -f 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"

echo "[6/6] sign"
# Throwaway debug key. NOT a platform key, NOT the MoKee release key. This APK is
# installed with `adb install` as an ordinary app; its signature grants it nothing.
if [ ! -f "$OUT/debug.keystore" ]; then
  "$JDK/bin/keytool" -genkeypair -v -keystore "$OUT/debug.keystore" \
    -storepass android -keypass android -alias leohifidebug \
    -keyalg RSA -keysize 2048 -validity 3650 \
    -dname "CN=Leo HiFi Stage1 Debug, OU=throwaway, O=none, C=CN" >/dev/null 2>&1
fi
"$BT/apksigner" sign --ks "$OUT/debug.keystore" --ks-pass pass:android \
  --key-pass pass:android --ks-key-alias leohifidebug \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
  --min-sdk-version 29 --out "$OUT/leo-hifi-stage1.apk" "$OUT/aligned.apk"
"$BT/apksigner" verify --min-sdk-version 29 -v "$OUT/leo-hifi-stage1.apk" | head -5

echo
echo "APK: $OUT/leo-hifi-stage1.apk"
ls -l "$OUT/leo-hifi-stage1.apk"
