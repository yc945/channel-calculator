[app]

title = 明渠水力计算
package.name = channelcalc
package.domain = org.water.channel
source.dir = .
source.include_exts = py,kv,ttf,otf,png,jpg
version = 2.0

requirements = python3==3.11.0,kivy==2.3.0,pillow

orientation = portrait
fullscreen = 0

android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a
android.permissions =

[buildozer]
log_level = 2
warn_on_root = 1
