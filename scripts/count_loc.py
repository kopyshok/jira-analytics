"""Count clean SLOC: backend (app/) + frontend (frontend/src/), exclude comments/blank/tests."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BACKEND_ROOT = ROOT / "app"
FRONTEND_ROOT = ROOT / "frontend" / "src"

PY_EXCLUDE_DIRS = {"__pycache__"}
TS_EXCLUDE_DIRS = {"__tests__", "tests"}

TEST_NAME_RE = re.compile(r"(^|[\\/])(test_|.*\.test\.|.*\.spec\.)", re.IGNORECASE)


def is_test_path(p: Path) -> bool:
    s = str(p).replace("\\", "/")
    return bool(re.search(r"(^|/)(tests?|__tests__)(/|$)", s)) or bool(
        re.search(r"/(test_[^/]+\.py|[^/]+\.(test|spec)\.[tj]sx?)$", s)
    )


def count_python(path: Path) -> int:
    """Strip triple-quoted docstrings + # comments + blanks."""
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        return 0
    # remove triple-quoted strings (greedy-safe non-greedy)
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    n = 0
    for line in src.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        n += 1
    return n


def strip_block_comments(src: str) -> str:
    return re.sub(r"/\*[\s\S]*?\*/", "", src)


def count_ts(path: Path) -> int:
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        return 0
    src = strip_block_comments(src)
    n = 0
    for line in src.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("//"):
            continue
        n += 1
    return n


def count_css(path: Path) -> int:
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        return 0
    src = strip_block_comments(src)
    n = 0
    for line in src.splitlines():
        s = line.strip()
        if not s:
            continue
        n += 1
    return n


def walk(root: Path, exts: set[str], excluded_dirs: set[str]):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in excluded_dirs for part in p.parts):
            continue
        if p.suffix.lower() not in exts:
            continue
        if is_test_path(p):
            continue
        yield p


def main() -> None:
    # Backend
    py_files = list(walk(BACKEND_ROOT, {".py"}, PY_EXCLUDE_DIRS))
    backend_total = sum(count_python(p) for p in py_files)

    # Frontend
    ts_exts = {".ts", ".tsx", ".js", ".jsx"}
    ts_files = list(walk(FRONTEND_ROOT, ts_exts, TS_EXCLUDE_DIRS))
    css_files = list(walk(FRONTEND_ROOT, {".css", ".scss"}, TS_EXCLUDE_DIRS))
    fe_ts_total = sum(count_ts(p) for p in ts_files)
    fe_css_total = sum(count_css(p) for p in css_files)

    print("=== Backend (app/, .py, no tests/comments/blanks) ===")
    print(f"files: {len(py_files)}")
    print(f"SLOC : {backend_total}")
    print()
    print("=== Frontend (frontend/src/, .ts/.tsx/.js/.jsx + .css) ===")
    print(f"ts files : {len(ts_files)}  SLOC: {fe_ts_total}")
    print(f"css files: {len(css_files)}  SLOC: {fe_css_total}")
    print(f"frontend total SLOC: {fe_ts_total + fe_css_total}")
    print()
    print("=== GRAND TOTAL ===")
    print(f"SLOC: {backend_total + fe_ts_total + fe_css_total}")

    # Per-area breakdown
    print()
    print("=== Backend breakdown by top-level dir ===")
    by_dir: dict[str, int] = {}
    for p in py_files:
        rel = p.relative_to(BACKEND_ROOT)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        by_dir[top] = by_dir.get(top, 0) + count_python(p)
    for k, v in sorted(by_dir.items(), key=lambda x: -x[1]):
        print(f"  {k:20s} {v}")

    print()
    print("=== Frontend breakdown by top-level dir ===")
    by_dir2: dict[str, int] = {}
    for p in ts_files + css_files:
        rel = p.relative_to(FRONTEND_ROOT)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        cnt = count_ts(p) if p.suffix.lower() in ts_exts else count_css(p)
        by_dir2[top] = by_dir2.get(top, 0) + cnt
    for k, v in sorted(by_dir2.items(), key=lambda x: -x[1]):
        print(f"  {k:20s} {v}")


if __name__ == "__main__":
    main()
