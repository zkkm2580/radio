[app]
title = RadioPlayer
package.name = radioplayer
package.domain = org.example

source.dir = .
source.include_exts = py,kv,txt

version = 0.1

requirements = python3,kivy,ffpyplayer
source.include_exts = py,png,jpg,kv,atlas,json
orientation = landscape

fullscreen = 1

# 告诉 Buildozer 不要下载，直接用我们准备好的路径
android.sdk_path = /home/runner/android-sdk
android.ndk_path = /home/runner/.buildozer/android/platform/android-ndk-r25b
android.accept_sdk_license = True

# 检查权限是否写对
android.permissions = INTERNET
# Android SDK Build Tools version
android.build_tools_version = 33.0.2
android.sdk = 33
android.api = 33
android.minapi = 21

android.ndk = 25b

android.archs = arm64-v8a,armeabi-v7a

log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1


