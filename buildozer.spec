[app]
title = RadioPlayer
package.name = radioplayer
package.domain = org.example
source.dir = .
source.include_exts = py,kv,txt,png,ttf
requirements = python3==3.11.9, hostpython3==3.11.9, kivy==2.3.0, certifi, openssl, libffi, liblzma, pyjnius

version = 0.1
orientation = landscape
fullscreen = 1
android.permissions = INTERNET, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE

# 建议的成熟稳定工具链
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