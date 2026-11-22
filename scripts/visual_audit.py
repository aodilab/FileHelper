import os
import pathlib
import shutil
from PIL import Image
from config.settings import ASSETS_DIR, BASE_DIR, CODE_LINE_RULES, ICON_PNG_PATH, SCRATCH_DIR, WIN_WIDTH, WIN_HEIGHT
from src.ui.renderer import AppleNeoRenderer
from src.ui.image_viewer import ImageViewerRenderer
from src.ui.image_editor import ImageEditorSession


def render_audit_snapshots(output_dir=None, sync_assets=False):
    """Render 5 standard desktop states (Empty, Queue, Modal, Viewer, ViewerEdit) for visual self-audit."""
    target_dir = output_dir or SCRATCH_DIR
    os.makedirs(target_dir, exist_ok=True)
    renderer = AppleNeoRenderer(WIN_WIDTH, WIN_HEIGHT)

    # 1. Zero state
    img_empty, _ = renderer.render([], "192.168.1.2", 8899)
    p_empty = os.path.join(target_dir, "audit_empty.png")
    img_empty.save(p_empty)

    # 2. Queue state: time chip, wrapped text, tall phone screenshot, 2-line file card, and composer draft paste
    sample_thumb = Image.open(ICON_PNG_PATH).convert("RGBA") if os.path.exists(ICON_PNG_PATH) else Image.new("RGBA", (160, 120), (7, 193, 96, 255))
    tall_shot = Image.new("RGBA", (390, 844), (255, 255, 255, 255))
    tall_shot.alpha_composite(sample_thumb.resize((220, 220), Image.Resampling.LANCZOS), (85, 280))
    draft_shot = Image.new("RGBA", (420, 180), (250, 250, 252, 255))
    draft_shot.alpha_composite(sample_thumb.resize((120, 120), Image.Resampling.LANCZOS), (150, 30))
    t0 = 1794300000
    peers = [{"cid": "ios_1", "kind": "ios", "label": "iPhone"}, {"cid": "android_1", "kind": "android", "label": "Android"}]
    sample_items = [
        {"id": "1", "kind": "text", "sender": "pc", "sender_id": "pc", "sender_label": "电脑", "text": "https://github.com/aodilab/FileHelper 这是一段比较长的文字，用来检查自动换行效果", "size_str": "40 字", "status": "点击复制", "ts": t0},
        {"id": "2", "kind": "memory", "sender": "ios", "sender_id": "ios_1", "sender_label": "iPhone", "name": "IMG_8842.png", "thumb": tall_shot, "size_str": "286.6 KB", "status": "已复制", "ts": t0 + 30},
        {"id": "3", "kind": "text", "sender": "android", "sender_id": "android_1", "sender_label": "Android", "text": "安卓端已接入，三端消息实时共享", "size_str": "15 字", "status": "点击复制", "ts": t0 + 60},
        {"id": "4", "kind": "file", "sender": "pc", "sender_id": "pc", "sender_label": "电脑", "name": "周末旅行原片_4K60fps_HDR实拍.mp4", "size_str": "1.28 GB", "status": "传输中 45%", "progress": 45, "ts": t0 + 900},
    ]
    sc_y = renderer.max_scroll(sample_items, draft_img=draft_shot)
    img_queue, _ = renderer.render(sample_items, "192.168.1.2", 8899, scroll_y=sc_y, phone_connected=True, hover_id="row_2", draft_img=draft_shot, connected_devices=peers)
    p_queue = os.path.join(target_dir, "audit_queue.png")
    img_queue.save(p_queue)

    # 3. In-window frosted glass QR modal state (showing live connected peers)
    img_modal, _ = renderer.render(sample_items, "192.168.1.2", 8899, modal_open=True, connected_devices=[peers[0]])
    p_modal = os.path.join(target_dir, "audit_modal.png")
    img_modal.save(p_modal)

    # 4 & 5. Standalone WeChat-style image viewer (browse bar + top-bar vector edit mode)
    viewer_renderer = ImageViewerRenderer(460, 760)
    fit_z = viewer_renderer.calc_fit_zoom(*tall_shot.size)
    img_viewer, _ = viewer_renderer.render(tall_shot, zoom=fit_z, has_prev=True, has_next=True, hover_id="btn_edit")
    p_viewer = os.path.join(target_dir, "audit_viewer.png")
    img_viewer.save(p_viewer)

    dummy = type("V", (), {"renderer": viewer_renderer, "pil_img": tall_shot, "zoom": fit_z, "pan_x": 0.0, "pan_y": 0.0})()
    ed = ImageEditorSession(dummy); ed.start(tall_shot)
    ed.history.append(ed.work_img.copy())
    ed._apply_stroke(ed.work_img, "rect", [(65, 260), (325, 520)])
    img_v_edit, _ = viewer_renderer.render(ed.current_image(), zoom=fit_z, has_prev=True, has_next=True, editor=ed)
    p_v_edit = os.path.join(target_dir, "audit_viewer_edit.png")
    img_v_edit.save(p_v_edit)

    if sync_assets:
        os.makedirs(ASSETS_DIR, exist_ok=True)
        for src_p, dst_name in [
            (p_empty, "preview_empty.png"),
            (p_queue, "preview_queue.png"),
            (p_modal, "preview_modal.png"),
            (p_v_edit, "preview_viewer.png"),
        ]:
            shutil.copy2(src_p, os.path.join(ASSETS_DIR, dst_name))

    return [p_empty, p_queue, p_modal, p_viewer, p_v_edit]


def audit_code_lines():
    """Verify all project files strictly comply with AGENTS.md Section IV line-count redlines."""
    base = pathlib.Path(BASE_DIR)
    results = []
    violations = []

    targets = [
        ("AGENTS.md", [base / "AGENTS.md"]),
        ("config", sorted((base / "config").rglob("*.py"))),
        ("scripts", sorted((base / "scripts").rglob("*.py"))),
        ("src", [p for p in sorted((base / "src").rglob("*.py")) if p.name != "__init__.py"]),
        ("templates", sorted((base / "templates").rglob("*.html"))),
    ]

    for category, files in targets:
        rule = CODE_LINE_RULES[category]
        g_min, g_max = rule["golden"]
        hard_max = rule["max"]
        for fp in files:
            if not fp.exists():
                continue
            lines = len(fp.read_text(encoding="utf-8").splitlines())
            rel = str(fp.relative_to(base)).replace("\\", "/")
            in_golden = g_min <= lines <= g_max
            under_redline = lines <= hard_max
            status = "GOLDEN" if in_golden else ("OK (<=MAX)" if under_redline else "VIOLATION")
            results.append((rel, lines, f"{g_min}~{g_max}", f"<={hard_max}", status))
            if not under_redline or not in_golden:
                violations.append(f"{rel}: {lines} lines (expected {g_min}~{g_max}, max {hard_max})")

    return results, violations
