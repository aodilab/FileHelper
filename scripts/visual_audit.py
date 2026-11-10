import os
import pathlib
from PIL import Image
from config.settings import BASE_DIR, CODE_LINE_RULES, ICON_PNG_PATH, SCRATCH_DIR, WIN_WIDTH, WIN_HEIGHT
from src.ui.renderer import AppleNeoRenderer


def render_audit_snapshots(output_dir=None):
    """Render 3 standard UI states (Empty, Queue with long names, Modal) for visual self-audit."""
    target_dir = output_dir or SCRATCH_DIR
    os.makedirs(target_dir, exist_ok=True)
    renderer = AppleNeoRenderer(WIN_WIDTH, WIN_HEIGHT)

    # 1. Zero state
    img_empty, _ = renderer.render([], "192.168.1.2", 8899)
    p_empty = os.path.join(target_dir, "audit_empty.png")
    img_empty.save(p_empty)

    # 2. Queue state: time chip, wrapped text, phone image (hovered, shows actions), file card in transfer
    sample_thumb = Image.open(ICON_PNG_PATH).convert("RGBA") if os.path.exists(ICON_PNG_PATH) else Image.new("RGBA", (160, 120), (7, 193, 96, 255))
    t0 = 1794300000
    sample_items = [
        {"id": "1", "kind": "text", "sender": "pc", "text": "https://github.com/aodilab/FileHelper 这是一段比较长的文字，用来检查自动换行效果", "size_str": "40 字", "status": "点击复制", "ts": t0},
        {"id": "2", "kind": "memory", "sender": "phone", "name": "IMG_8842.png", "thumb": sample_thumb, "size_str": "286.6 KB", "status": "已复制", "ts": t0 + 30},
        {"id": "3", "kind": "file", "sender": "pc", "name": "赵云_王者出装箱_实操演示视频.mp4", "size_str": "8.66 MB", "status": "传输中 45%", "progress": 45, "ts": t0 + 900},
        {"id": "4", "kind": "text", "sender": "phone", "text": "收到", "size_str": "2 字", "status": "点击复制", "ts": t0 + 920},
    ]
    img_queue, _ = renderer.render(sample_items, "192.168.1.2", 8899, phone_connected=True, hover_id="row_2")
    p_queue = os.path.join(target_dir, "audit_queue.png")
    img_queue.save(p_queue)

    # 3. In-window frosted glass modal state
    img_modal, _ = renderer.render(sample_items, "192.168.1.2", 8899, modal_open=True)
    p_modal = os.path.join(target_dir, "audit_modal.png")
    img_modal.save(p_modal)

    return [p_empty, p_queue, p_modal]


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
