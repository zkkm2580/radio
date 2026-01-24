[app]
title = RadioPlayer
package.name = radioplayer
package.domain = org.example

source.dir = .
source.include_exts = py,kv,txt

version = 0.1

requirements = python3,kivy,ffpyplayer

orientation = landscape

fullscreen = 1

android.permissions = INTERNET
# Android SDK Build Tools version
android.build_tools_version = 33.0.2

android.api = 33
android.minapi = 21

android.ndk = 25b

android.archs = arm64-v8a,armeabi-v7a

log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1

