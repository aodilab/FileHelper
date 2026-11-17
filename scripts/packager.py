import os
import shutil
import subprocess
import sys
import zipfile

from config.settings import APPLE_TOUCH_ICON_PATH, BASE_DIR, ICON_ICO_PATH, ICON_PNG_PATH, MOBILE_HTML_PATH
from scripts.icon_builder import build_app_icons

APP_NAME = "FileHelper"
PORTABLE_ZIP_NAME = "FileHelper-win64-portable.zip"


def _find_inno_compiler():
    """Locate Inno Setup compiler (ISCC.exe) on PATH or default install directories."""
    cmd = shutil.which("iscc") or shutil.which("ISCC")
    if cmd:
        return cmd
    for env_key in ("ProgramFiles(x86)", "ProgramFiles"):
        root = os.environ.get(env_key, "")
        candidate = os.path.join(root, "Inno Setup 6", "ISCC.exe") if root else ""
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _zip_directory(src_dir, zip_path):
    """Compress `src_dir` into `zip_path` preserving the top-level folder name."""
    parent = os.path.dirname(os.path.abspath(src_dir))
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, _, files in os.walk(src_dir):
            for fname in sorted(files):
                full_path = os.path.join(root, fname)
                arcname = os.path.relpath(full_path, parent)
                zf.write(full_path, arcname)


def build_release_packages(version="1.0.0"):
    """Build PyInstaller --onedir bundle, portable .zip, and optional Inno Setup installer."""
    if not all(os.path.exists(p) for p in (ICON_ICO_PATH, ICON_PNG_PATH, APPLE_TOUCH_ICON_PATH)):
        build_app_icons()

    dist_dir = os.path.join(BASE_DIR, "dist")
    build_dir = os.path.join(BASE_DIR, "build")
    bundle_dir = os.path.join(dist_dir, APP_NAME)
    if os.path.exists(bundle_dir):
        shutil.rmtree(bundle_dir, ignore_errors=True)

    entry_script = os.path.join(BASE_DIR, "build.py")
    sep = ";" if os.name == "nt" else ":"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--noconsole",
        "--clean",
        "--noconfirm",
        f"--name={APP_NAME}",
        f"--icon={ICON_ICO_PATH}",
        f"--distpath={dist_dir}",
        f"--workpath={build_dir}",
        f"--specpath={build_dir}",
        f"--add-data={MOBILE_HTML_PATH}{sep}templates",
        f"--add-data={ICON_ICO_PATH}{sep}assets",
        f"--add-data={ICON_PNG_PATH}{sep}assets",
        f"--add-data={APPLE_TOUCH_ICON_PATH}{sep}assets",
        "--collect-all=tkinterdnd2",
        "--collect-all=pillow_heif",
        "--hidden-import=win32clipboard",
        "--hidden-import=win32com.client",
        "--exclude-module=numpy",
        "--exclude-module=scipy",
        "--exclude-module=pandas",
        "--exclude-module=matplotlib",
        "--exclude-module=pytest",
        entry_script,
    ]
    subprocess.run(cmd, cwd=BASE_DIR, check=True)

    zip_path = os.path.join(dist_dir, PORTABLE_ZIP_NAME)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    _zip_directory(bundle_dir, zip_path)
    outputs = [bundle_dir, zip_path]

    iscc = _find_inno_compiler()
    iss_path = os.path.join(BASE_DIR, "scripts", "installer.iss")
    if iscc and os.path.exists(iss_path):
        subprocess.run([iscc, f"/DMyAppVersion={version}", iss_path], cwd=BASE_DIR, check=True)
        setup_exe = os.path.join(dist_dir, "FileHelper-Setup.exe")
        if os.path.exists(setup_exe):
            outputs.append(setup_exe)
    else:
        print("Inno Setup (ISCC.exe) not found; skipped FileHelper-Setup.exe.")

    for item in outputs:
        print(f"Release artifact: {item}")
    return outputs
