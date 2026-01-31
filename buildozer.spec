[app]
title = RadioPlayer
package.name = radioplayer
package.domain = org.example
source.dir = .
source.include_exts = py,kv,txt,png
# 核心修改：增加 liblzma 解决压缩库缺失，增加 pyjnius 解决 C 源码生成问题
requirements = python3, kivy==2.3.0, ffpyplayer, certifi, openssl, libffi, liblzma, pyjnius

version = 0.1
orientation = landscape
fullscreen = 1
android.permissions = INTERNET

# 停止手动指定路径，让 Buildozer 自动下载到默认位置
# android.sdk_path = (这行删掉或注释掉)

android.api = 31
android.minapi = 21
android.sdk = 31
android.ndk = 25b
android.build_tools_version = 31.0.0
android.accept_sdk_license = True
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
