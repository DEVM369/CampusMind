"""Shared local/CI checks. Dependencies must already be installed."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-frontend", action="store_true")
    parser.add_argument("--docker-image", help="also build and smoke this image tag")
    args = parser.parse_args()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
           "PYTHONPATH": str(ROOT / "src"), "RAG_EMBEDDING_PROVIDER": "deterministic"}

    def run(label, command):
        print(f"Checking {label}...", flush=True)
        subprocess.run(command, cwd=ROOT, env=env, check=True)

    try:
        if args.build_frontend:
            npm = shutil.which("npm")
            if not npm:
                raise FileNotFoundError("npm")
            run("frontend build", [npm, "run", "check", "--prefix", "frontend"])
        else:
            run("built frontend", ["node", "frontend/scripts/validate.mjs"])
        run("static architecture", [sys.executable, "scripts/validate.py"])
        run("offline tests", [sys.executable, "scripts/test_p0_offline.py",
                              "--tb=short", "-p", "no:cacheprovider"])
        run("offline functional benchmark", [
            sys.executable,
            "scripts/run_offline_benchmark.py",
            "--output",
            str(ROOT / "reports" / "offline" / "benchmark-v1.json"),
        ])
        run("OpenAPI", [sys.executable, "-c",
                        ("from campusmind.main import app; schema = app.openapi(); "
                        "assert schema['info']['title']; "
                        "assert '/api/v1/auth/login' in schema['paths']; "
                        "print('PASS: OpenAPI smoke')")])
        if args.docker_image:
            run("API image build", ["docker", "build", "-f", "infra/docker/Dockerfile",
                                    "-t", args.docker_image, "."])
            run("isolated image HTTP smoke", [
                "docker", "run", "--rm", "--network", "none",
                "-e", "RAG_EMBEDDING_PROVIDER=deterministic", args.docker_image,
                "python", "scripts/smoke_api_image.py",
            ])
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: project checks ({type(exc).__name__})", file=sys.stderr)
        return 1
    print("PASS: CampusMind project checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
