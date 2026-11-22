import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from src.core.queue_manager import check_existing_instance_and_send


def main():
    args = sys.argv[1:]

    if "--icon" in args:
        from scripts.icon_builder import build_app_icons
        build_app_icons()
        print("Icons generated in assets/.")
        return

    if "--shortcut" in args:
        from scripts.icon_builder import create_desktop_shortcut
        path = create_desktop_shortcut()
        print(f"Shortcut created: {path}")
        return

    if "--audit" in args:
        from scripts.visual_audit import audit_code_lines, render_audit_snapshots
        out_dir = None
        idx = args.index("--audit")
        if idx + 1 < len(args) and not args[idx + 1].startswith("--"):
            out_dir = args[idx + 1]
        paths = render_audit_snapshots(out_dir)
        for p in paths:
            print(f"Audit snapshot: {p}")
        results, violations = audit_code_lines()
        for rel, lines, golden, max_l, status in results:
            print(f"[LINE AUDIT] {rel:32s} | {lines:3d} lines | golden {golden:7s} | { max_l:6s} | {status}")
        if violations:
            raise SystemExit(f"Line count violations: {violations}")
        return

    if "--all" in args:
        from scripts.icon_builder import build_app_icons, create_desktop_shortcut
        from scripts.visual_audit import audit_code_lines, render_audit_snapshots
        build_app_icons()
        create_desktop_shortcut()
        render_audit_snapshots(sync_assets=True)
        _, violations = audit_code_lines()
        if violations:
            raise SystemExit(f"Line count violations: {violations}")
        print("All build, preview sync, and audit tasks completed.")
        return

    if "--package" in args:
        from scripts.packager import build_release_packages
        build_release_packages()
        return

    if "--android" in args:
        from scripts.android_builder import build_android_apk
        apk = build_android_apk()
        print(f"Android APK built: {apk}")
        return

    # Filter out CLI flags; remaining arguments are dropped file paths
    dropped_files = [a for a in args if not a.startswith("--")]

    if check_existing_instance_and_send(dropped_files):
        sys.exit(0)

    from src.ui.desktop_app import launch_desktop_app
    launch_desktop_app(initial_files=dropped_files, start_hidden=("--tray" in args and not dropped_files))


if __name__ == "__main__":
    main()
