import glob
import os
import shutil
import subprocess
import zipfile
from PIL import Image, ImageDraw
from config.settings import BASE_DIR, DEFAULT_PORT
from scripts.icon_builder import _draw_transfer_folder_glyph
from src.core.peer_hub import get_local_ip

ANDROID_DIR = os.path.join(BASE_DIR, "android")
DIST_APK = os.path.join(BASE_DIR, "dist", "FileHelper-Android.apk")
KEYSTORE_PATH = os.path.join(os.path.expanduser("~"), ".android", "filehelper-release.jks")
MIPMAPS = [("mdpi", 48, 108), ("hdpi", 72, 162), ("xhdpi", 96, 216), ("xxhdpi", 144, 324), ("xxxhdpi", 192, 432)]


def _find_jdk():
    cands = [os.environ.get("JAVA_HOME", "")]
    javac_in_path = shutil.which("javac")
    if javac_in_path:
        cands.append(os.path.dirname(os.path.dirname(javac_in_path)))
    cands.extend(sorted(glob.glob(os.path.join(os.path.expanduser("~"), ".antigravity-ide", "extensions", "redhat.java*", "jre", "*")), reverse=True))
    for root in cands:
        if root and os.path.exists(os.path.join(root, "bin", "javac.exe")):
            return root
    raise RuntimeError("JDK not found. Install JDK 17+ or set JAVA_HOME.")


def _find_sdk():
    for root in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")):
        if not root or not os.path.isdir(root):
            continue
        plats = sorted(glob.glob(os.path.join(root, "platforms", "android-*")), reverse=True)
        bts = sorted(glob.glob(os.path.join(root, "build-tools", "*")), reverse=True)
        if plats and bts and os.path.exists(os.path.join(plats[0], "android.jar")):
            return plats[0], bts[0]
    raise RuntimeError("Android SDK (platforms + build-tools) not found under %LOCALAPPDATA%\\Android\\Sdk.")


def _render_icons(res_dir):
    size = 512
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        gd.line([(0, y), (size, y)], fill=(int(25 - 18 * y / size), int(211 - 18 * y / size), int(110 - 14 * y / size), 255))

    legacy = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(16, 16), (size - 16, size - 16)], radius=112, fill=255)
    legacy.paste(grad, (0, 0), mask)
    _draw_transfer_folder_glyph(ImageDraw.Draw(legacy), size)

    glyph = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    _draw_transfer_folder_glyph(ImageDraw.Draw(glyph), size)
    fg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inner = int(size * 0.66)
    off = (size - inner) // 2
    fg.alpha_composite(glyph.resize((inner, inner), Image.Resampling.LANCZOS), (off, off))

    for dpi, leg_px, adp_px in MIPMAPS:
        d = os.path.join(res_dir, f"mipmap-{dpi}")
        os.makedirs(d, exist_ok=True)
        legacy.resize((leg_px, leg_px), Image.Resampling.LANCZOS).save(os.path.join(d, "ic_launcher.png"), "PNG")
        fg.resize((adp_px, adp_px), Image.Resampling.LANCZOS).save(os.path.join(d, "ic_launcher_foreground.png"), "PNG")


def _run(cmd, env):
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
    return proc


def _ensure_keystore(jdk_bin, env):
    if os.path.exists(KEYSTORE_PATH):
        return
    os.makedirs(os.path.dirname(KEYSTORE_PATH), exist_ok=True)
    _run([
        os.path.join(jdk_bin, "keytool.exe"), "-genkeypair", "-v",
        "-keystore", KEYSTORE_PATH, "-alias", "filehelper",
        "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
        "-storepass", "filehelper123", "-keypass", "filehelper123",
        "-dname", "CN=FileHelper, OU=AodiLab, O=AodiLab, L=Local, S=Local, C=CN",
    ], env)


def build_android_apk():
    """Compile, package, align, and sign the lightweight Android WebView APK into dist/FileHelper-Android.apk."""
    jdk = _find_jdk()
    jdk_bin = os.path.join(jdk, "bin")
    plat_dir, bt_dir = _find_sdk()
    android_jar = os.path.join(plat_dir, "android.jar")

    env = os.environ.copy()
    env["JAVA_HOME"] = jdk
    env["PATH"] = jdk_bin + os.pathsep + env.get("PATH", "")

    work = os.path.join(BASE_DIR, "build", "android")
    if os.path.exists(work):
        shutil.rmtree(work)
    res_copy, gen_dir, cls_dir, dex_dir = [os.path.join(work, n) for n in ("res", "gen", "classes", "dex")]
    shutil.copytree(os.path.join(ANDROID_DIR, "res"), res_copy)
    for d in (gen_dir, cls_dir, dex_dir, os.path.dirname(DIST_APK)):
        os.makedirs(d, exist_ok=True)
    _render_icons(res_copy)

    res_zip = os.path.join(work, "res.zip")
    unsigned_apk = os.path.join(work, "unsigned.apk")
    aligned_apk = os.path.join(work, "aligned.apk")

    _run([os.path.join(bt_dir, "aapt2.exe"), "compile", "--dir", res_copy, "-o", res_zip], env)
    _run([
        os.path.join(bt_dir, "aapt2.exe"), "link", "-o", unsigned_apk,
        "-I", android_jar, "--manifest", os.path.join(ANDROID_DIR, "AndroidManifest.xml"),
        "--java", gen_dir, "--auto-add-overlay", res_zip,
    ], env)

    defaults_dir = os.path.join(gen_dir, "com", "aodilab", "filehelper")
    os.makedirs(defaults_dir, exist_ok=True)
    default_url = f"http://{get_local_ip()}:{DEFAULT_PORT}"
    with open(os.path.join(defaults_dir, "BuildDefaults.java"), "w", encoding="utf-8") as fp:
        fp.write(f'package com.aodilab.filehelper;\nfinal class BuildDefaults {{ static final String DEFAULT_SERVER_URL = "{default_url}"; }}\n')

    java_files = sorted(glob.glob(os.path.join(ANDROID_DIR, "java", "**", "*.java"), recursive=True))
    java_files += sorted(glob.glob(os.path.join(gen_dir, "**", "*.java"), recursive=True))
    _run([os.path.join(jdk_bin, "javac.exe"), "--release", "11", "-encoding", "UTF-8", "-classpath", android_jar, "-d", cls_dir, *java_files], env)

    class_files = sorted(glob.glob(os.path.join(cls_dir, "**", "*.class"), recursive=True))
    _run([os.path.join(bt_dir, "d8.bat"), "--release", "--min-api", "24", "--lib", android_jar, "--output", dex_dir, *class_files], env)

    with zipfile.ZipFile(unsigned_apk, "a") as zf:
        zf.write(os.path.join(dex_dir, "classes.dex"), "classes.dex", compress_type=zipfile.ZIP_STORED)

    _run([os.path.join(bt_dir, "zipalign.exe"), "-f", "-p", "4", unsigned_apk, aligned_apk], env)
    _ensure_keystore(jdk_bin, env)
    _run([
        os.path.join(bt_dir, "apksigner.bat"), "sign",
        "--v1-signing-enabled", "true", "--v2-signing-enabled", "true", "--v3-signing-enabled", "true", "--v4-signing-enabled", "false",
        "--ks", KEYSTORE_PATH, "--ks-key-alias", "filehelper",
        "--ks-pass", "pass:filehelper123", "--key-pass", "pass:filehelper123",
        "--out", DIST_APK, aligned_apk,
    ], env)
    _run([os.path.join(bt_dir, "apksigner.bat"), "verify", DIST_APK], env)
    shutil.rmtree(work, ignore_errors=True)
    return DIST_APK
