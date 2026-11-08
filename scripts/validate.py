from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

errors: list[str] = []

# 1. Syntax
python_files = [
    *SRC.rglob("*.py"),
    *(ROOT / "tests").rglob("*.py"),
    *(ROOT / "scripts").glob("*.py"),
    *(ROOT / "migrations").rglob("*.py"),
]
for path in python_files:
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"AST {path.relative_to(ROOT)}: {exc}")

# 2. Package/module graph
modules: set[str] = set()
for path in SRC.rglob("*.py"):
    rel = path.relative_to(SRC)
    if path.name == "__init__.py":
        modules.add(".".join(rel.parent.parts))
    else:
        modules.add(".".join(rel.with_suffix("").parts))

for path in python_files:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    for node in ast.walk(tree):
        candidates: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            candidates.append(node.module)
        elif isinstance(node, ast.Import):
            candidates.extend(alias.name for alias in node.names)
        for module in candidates:
            if not module.startswith("campusmind"):
                continue
            if module not in modules and not any(item.startswith(module + ".") for item in modules):
                errors.append(f"missing local module: {module} ({path.relative_to(ROOT)})")

# 3. No legacy package imports / stage naming
legacy_import = re.compile(r"(?m)^\s*(?:from\s+app(?:\.|\s)|import\s+app(?:\.|\s|$))")
for path in python_files:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if legacy_import.search(text):
        errors.append(f"legacy app import: {path.relative_to(ROOT)}")

for path in ROOT.rglob("*"):
    if any(part in {"node_modules", "reports", "data", "logs", ".git", ".venv", "venv"}
           for part in path.relative_to(ROOT).parts):
        continue
    low = path.name.lower()
    if "step" in low:
        errors.append(f"stage-named artifact remains: {path.relative_to(ROOT)}")

# 4. Required final architecture
required = [
    "src/campusmind/main.py",
    "src/campusmind/config.py",
    "src/campusmind/agent/runtime.py",
    "src/campusmind/agent/multi.py",
    "src/campusmind/knowledge/rag.py",
    "src/campusmind/knowledge/graph_rag.py",
    "src/campusmind/knowledge/hybrid.py",
    "src/campusmind/tools/course.py",
    "src/campusmind/tools/actions.py",
    "src/campusmind/platform/security.py",
    "frontend/src/main.ts",
    "frontend/src/api.ts",
    "frontend/src/views/chat.ts",
    "frontend/dist/index.html",
    "frontend/dist/src/main.js",
    "frontend/dist/vendor/vue.global.prod.js",
    "migrations/versions/20260924_0010_observability.py",
    "migrations/versions/20260926_0011_auth_sessions.py",
]
for item in required:
    if not (ROOT / item).exists():
        errors.append(f"required artifact missing: {item}")

# 5. V1.1 safety hardening must remain present.
course = (ROOT / "src/campusmind/tools/course.py").read_text(encoding="utf-8")
actions = (ROOT / "src/campusmind/tools/actions.py").read_text(encoding="utf-8")
adaptive = (ROOT / "src/campusmind/knowledge/adaptive.py").read_text(encoding="utf-8")
if "def can_answer(" not in course or "find_courses_mentioned_in_text" not in course:
    errors.append("CourseTool V1.1 entity guard missing")
if "faq_markers" not in actions or "确认" not in actions:
    errors.append("Classroom FAQ/action guard missing")
if ".can_answer(query)" not in adaptive:
    errors.append("Adaptive execution-time CourseTool guard missing")

source_count = len(list(SRC.rglob("*.py")))
if source_count > 60:
    errors.append(f"source tree is no longer slim: {source_count} Python files")

if errors:
    print("FAIL: CampusMind Final Slim validation")
    for error in errors:
        print(" -", error)
    raise SystemExit(1)

print(f"PASS: static architecture/safety validation ({source_count} source Python files)")
