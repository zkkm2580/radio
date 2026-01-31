[app]
title = RadioPlayer
package.name = radioplayer
package.domain = org.example
source.dir = .
source.include_exts = py,kv,txt,png
requirements = python3, kivy==2.3.0, ffpyplayer, certifi, openssl, libffi, liblzma, pyjnius

version = 0.1
orientation = landscape
fullscreen = 1
android.permissions = INTERNET

# 升级到 API 33 和 NDK 25b
android.api = 33
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21
android.build_tools_version = 33.0.0
android.accept_sdk_license = True
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
