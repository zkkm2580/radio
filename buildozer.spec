[app]
title = RadioPlayer
package.name = radioplayer
package.domain = org.example
source.dir = .
source.include_exts = py,kv,txt,png,jpg
# 使用刚才创建的 requirements.txt
requirements.source_exts = requirements.txt

version = 0.1
orientation = landscape
fullscreen = 1
android.permissions = INTERNET

# 核心版本对齐
android.api = 33
android.minapi = 21
android.sdk = 33
android.ndk = 25b
android.build_tools_version = 33.0.2

# 强制接受许可
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

# 路径强制指向（与下方 YAML 保持一致）
android.sdk_path = /home/runner/android-sdk
android.skip_update = False

[buildozer]
log_level = 2
warn_on_root = 1
