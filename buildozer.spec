[app]
title = RadioPlayer
package.name = radioplayer
package.domain = org.example
source.dir = .
source.include_exts = py,kv,txt,png,ttf
requirements = python3==3.11.9, hostpython3==3.11.9, kivy==2.3.0, certifi, openssl, libffi, liblzma, pyjnius

version = 0.2
orientation = landscape
fullscreen = 1
# INTERNET 拉列表；ACCESS_NETWORK_STATE 判断网络；WAKE_LOCK 保证息屏不断播
# 注：Android 13 起 READ_EXTERNAL_STORAGE 已基本失效，仅保留用于老设备
android.permissions = INTERNET, ACCESS_NETWORK_STATE, WAKE_LOCK, READ_EXTERNAL_STORAGE

# 直播列表里的电台有 http:// 明文流，Android 9+ 需要放行 cleartext，
# 否则 MediaPlayer 会直接拒绝播放（见 hooks/patch_manifest.py 说明）
p4a.hook = ./hooks/patch_manifest.py

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