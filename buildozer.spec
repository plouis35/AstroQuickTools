[app]

title = HelloWorld
package.name = helloworld
package.domain = org.example
source.dir = .
source.include_exts = py,kv,png,jpg,atlas
version = 0.1.0
requirements = python3,kivy==2.3.1
orientation = portrait
fullscreen = 0

# Android builds use a 64-bit ARM APK compatible with most recent phones.
android.api = 35
# Python 3.14 uses pwritev, which Android exposes from API 24.
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True

# Python 3.14 Android wheels require the updated package installer.
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1
