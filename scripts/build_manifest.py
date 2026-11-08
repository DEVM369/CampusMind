"""Generate source inventories without local secrets, caches, or runtime data."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inventory(paths: list[str]) -> dict:
    files = []
    for name in sorted(paths):
        content = (ROOT / name).read_bytes()
        files.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    tree = "".join(f"{item['sha256']}  {item['path']}\n" for item in files).encode("utf-8")
    return {
        "files_count": len(files),
        "tree_sha256": hashlib.sha256(tree).hexdigest(),
        "tree_hash_algorithm": "SHA256 of UTF-8 <sha256><two spaces><posix_path><LF>, sorted by path",
        "files": files,
    }


def source_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True,
    )
    excluded = {".git", ".idea", ".venv", "venv", "node_modules", "__pycache__",
                ".pytest_cache", ".ruff_cache", "reports", "data", "logs"}
    paths = []
    for name in sorted(set(result.stdout.decode("utf-8").split("\0")) - {""}):
        path = Path(name)
        if not (ROOT / path).is_file():
            continue
        if any(part in excluded or part.endswith(".egg-info") for part in path.parts):
            continue
        if path.name != ".env.example" and (
            path.name == ".env" or path.name.startswith((".env.", "test.env"))
        ):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        paths.append(name)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check without writing manifests")
    args = parser.parse_args()
    paths = source_paths()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    frontend = {
        "name": "CampusMind Vue Frontend", "version": version,
        "framework": "Vue 3 + TypeScript", "vue_runtime_version": "3.5.13",
        "runtime_requires_node": False, "entry": "/ui/",
        **inventory([name for name in paths if name.startswith("frontend/")
                     and name != "frontend/manifest.json"]),
    }
    targets = {"frontend/manifest.json": frontend}
    if not args.check:
        write_manifest("frontend/manifest.json", frontend)
    release = {
        "name": "CampusMind", "version": version, "manifest_format": 2,
        "release_status": "development_snapshot", "alembic_head": "20260926_0011",
        "scope": "Source inventory only; does not certify deployment, security review or publication readiness.",
        **inventory([name for name in paths if name != "release/manifest.json"]),
    }
    targets["release/manifest.json"] = release
    for name, manifest in targets.items():
        if args.check:
            if json.loads((ROOT / name).read_text("utf-8")) != manifest:
                raise SystemExit(f"FAIL: {name} is stale; run python scripts/build_manifest.py")
        elif name != "frontend/manifest.json":
            write_manifest(name, manifest)
        print(f"PASS: {name} ({manifest['files_count']} files)")


def write_manifest(name: str, manifest: dict) -> None:
    with (ROOT / name).open("w", encoding="utf-8", newline="\n") as output:
        json.dump(manifest, output, ensure_ascii=True, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
