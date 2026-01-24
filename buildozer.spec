[app]
title = RadioPlayer
package.name = radioplayer
package.domain = org.example
source.dir = .
source.include_exts = py,kv,txt,png,jpg

# 核心修改：增加 liblzma 解决压缩库缺失，增加 pyjnius 解决 C 源码生成问题
requirements = python3, kivy==2.3.0, ffpyplayer, certifi, openssl, libffi, liblzma, pyjnius

version = 0.1
orientation = landscape
fullscreen = 1
android.permissions = INTERNET

# 停止手动指定路径，让 Buildozer 自动下载到默认位置
# android.sdk_path = (这行删掉或注释掉)

android.api = 33
android.minapi = 21
android.ndk = 25b
android.build_tools_version = 33.0.2
android.accept_sdk_license = True
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
