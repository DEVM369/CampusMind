"""Run inside an ephemeral --network none image, without external services."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from check_runtime import http_fetch, run_checks


def main() -> int:
    env = {**os.environ, "RAG_EMBEDDING_PROVIDER": "deterministic"}
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "campusmind.main:app",
         "--host", "127.0.0.1", "--port", "8000"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        fetch = http_fetch("http://127.0.0.1:8000", timeout=30)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("API process exited before liveness")
            try:
                if fetch("/health")[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError("API liveness timed out")
        results = run_checks(fetch, liveness_only=True)
        if not all(item["passed"] for item in results):
            raise RuntimeError("API or built frontend smoke failed")
        if fetch("/api/v1/system/readiness")[0] != 503:
            raise RuntimeError("Readiness must fail without infrastructure")
        print("CM_DOCKER_IMAGE_SMOKE_PASSED")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"FAIL: image smoke ({type(exc).__name__})")
        return 1
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
