"""NumPy recipe override retaining python-for-android's Meson cross options."""

import shutil
from os.path import join

from pythonforandroid.recipe import MesonRecipe, Recipe


class NumpyRecipe(MesonRecipe):
    version = "v2.3.0"
    url = "git+https://github.com/numpy/numpy"
    extra_build_args = ["-Csetup-args=-Dblas=none", "-Csetup-args=-Dlapack=none"]
    opt_depends = ["libopenblas"]
    need_stl_shared = True
    min_ndk_api_support = 24

    def get_include(self, arch):
        return join(
            self.ctx.get_python_install_dir(arch.arch),
            "numpy/_core/include",
        )

    def get_recipe_meson_options(self, arch):
        options = super().get_recipe_meson_options(arch)
        options["properties"]["longdouble_format"] = (
            "IEEE_DOUBLE_LE"
            if arch.arch in ("armeabi-v7a", "x86")
            else "IEEE_QUAD_LE"
        )
        return options

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env["_PYTHON_HOST_PLATFORM"] = arch.command_prefix
        env["NPY_DISABLE_SVML"] = "1"
        env["TARGET_PYTHON_EXE"] = join(
            Recipe.get_recipe("python3", self.ctx).get_build_dir(arch.arch),
            "android-build",
            "python",
        )
        blas_dir = join(
            Recipe.get_recipe("libopenblas", self.ctx).get_build_dir(arch.arch),
            "build",
        )
        env["CXXFLAGS"] += f" -I{blas_dir} -L{join(blas_dir, 'lib')}"

        if "libopenblas" in self.ctx.recipe_build_order:
            self.ensure_args(
                "-Csetup-args=-Dblas=auto",
                "-Csetup-args=-Dlapack=auto",
                "-Csetup-args=-Dallow-noblas=False",
            )
        return env

    def get_hostrecipe_env(self, arch=None):
        env = super().get_hostrecipe_env(arch=arch)
        env["RANLIB"] = shutil.which("ranlib")
        return env


recipe = NumpyRecipe()
