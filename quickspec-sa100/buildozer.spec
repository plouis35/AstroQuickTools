[app]

title = QuickSpec SA100
package.name = quickspecsa100
package.domain = fr.plouis
source.dir = .
source.include_exts = py,kv,png
version = 0.1.0
requirements = python3,kivy==2.3.1,numpy,pillow
orientation = portrait
fullscreen = 0

android.api = 35
# Keep the same minimum as the working Android project (Android 7.0).
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True

p4a.branch = develop
# This project is nested under the directory containing the shared local recipe.
# Run Buildozer from quickspec-sa100/ so this relative path resolves correctly.
p4a.local_recipes = ../p4a-recipes

[buildozer]
log_level = 2
warn_on_root = 1
