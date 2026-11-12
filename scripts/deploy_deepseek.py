"""Sync DeepSeek configuration and the built UI to an existing Ubuntu API container."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


class DeploymentError(RuntimeError):
    pass


def docker(*args: str, input_text: str | None = None, timeout: int = 90) -> str:
    result = subprocess.run(
        ["docker", *args], input=input_text, capture_output=True,
        text=True, timeout=timeout, check=False,
    )
    if result.returncode:
        raise DeploymentError(f"Docker {args[0]} failed")
    return result.stdout.strip()


def export_credentials() -> dict[str, str]:
    from dotenv import dotenv_values

    values = dotenv_values(ROOT / ".env")
    key = (os.getenv("DEEPSEEK_API_KEY") or values.get("DEEPSEEK_API_KEY") or "").strip()
    endpoint = (
        os.getenv("DEEPSEEK_BASE_URL") or values.get("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com"
    ).strip()
    if not key or key in {"not-configured", "local"}:
        raise DeploymentError("Configure DEEPSEEK_API_KEY in the local .env first")
    parts = urlsplit(endpoint)
    if (parts.scheme not in {"https", "http"} or not parts.hostname
            or parts.username or parts.password or parts.query or parts.fragment):
        raise DeploymentError("DeepSeek endpoint must not contain embedded credentials")
    return {"DEEPSEEK_API_KEY": key, "DEEPSEEK_BASE_URL": endpoint}


def build_bundle(stage: Path, credentials: dict[str, str]) -> Path:
    archive = stage / "update.tar.gz"
    with archive.open("xb") as output:
        archive.chmod(0o600)
        with tarfile.open(fileobj=output, mode="w:gz") as bundle:
            bundle.add(ROOT / "src/campusmind/config.py", arcname="config.py")
            bundle.add(ROOT / "frontend/dist", arcname="dist")
            payload = json.dumps(credentials).encode("utf-8")
            info = tarfile.TarInfo("credentials.json")
            info.size = len(payload)
            info.mode = 0o600
            bundle.addfile(info, io.BytesIO(payload))
    return archive


def extract_bundle(archive: Path, target: Path) -> None:
    target.mkdir(mode=0o700)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            destination = (target / member.name).resolve()
            if not destination.is_relative_to(target.resolve()) or member.issym() or member.islnk():
                raise DeploymentError("Unsafe update archive member")
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True, mode=0o700)
            elif member.isfile():
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with bundle.extractfile(member) as source, destination.open("xb") as output:
                    destination.chmod(0o600)
                    shutil.copyfileobj(source, output)
            else:
                raise DeploymentError("Unsupported update archive member")


def apply_update(stage: Path, container: str) -> None:
    if os.name == "nt" or os.geteuid() != 0:
        raise DeploymentError("The remote apply step requires sudo on Ubuntu")
    stage = stage.resolve()
    stage.chmod(0o700)
    payload = stage / "payload"
    extract_bundle(stage / "update.tar.gz", payload)
    backup = stage / "backup"
    backup.mkdir(mode=0o700)
    temporary_secret = f"/tmp/campusmind-deepseek-{uuid4().hex}.json"
    changed = False
    has_dotenv = False
    try:
        metadata = json.loads(docker("inspect", container))[0]
        if (not metadata["State"]["Running"]
                or metadata["HostConfig"]["NetworkMode"] != "host"
                or metadata["Config"]["WorkingDir"] != "/app"):
            raise DeploymentError("Expected a running host-network API container in /app")
        has_dotenv = docker("exec", container, "python", "-c",
                            "from pathlib import Path; print(int(Path('/app/.env').exists()))") == "1"
        docker("cp", f"{container}:/app/src/campusmind/config.py", str(backup / "config.py"))
        docker("cp", f"{container}:/app/frontend/dist", str(backup / "dist"))
        if has_dotenv:
            docker("cp", f"{container}:/app/.env", str(backup / ".env"))
            (backup / ".env").chmod(0o600)
        print("PASS: target container and private backups", flush=True)
        changed = True
        docker("cp", str(payload / "config.py"), f"{container}:/app/src/campusmind/config.py")
        docker("cp", str(payload / "dist") + "/.", f"{container}:/app/frontend/dist")
        docker("cp", str(payload / "credentials.json"), f"{container}:{temporary_secret}")
        configure = (
            "import json,sys; from pathlib import Path; from dotenv import set_key; "
            "values=json.loads(Path(sys.argv[1]).read_text()); "
            "assert set(values)=={'DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL'}; "
            "path=Path('/app/.env'); path.touch(mode=0o600, exist_ok=True); "
            "[set_key(str(path), name, value) for name,value in values.items()]; "
            "path.chmod(0o600)"
        )
        docker("exec", container, "python", "-c", configure, temporary_secret)
        verify_settings = (
            "import json,sys; from pathlib import Path; "
            "from campusmind.config import DEEPSEEK_API_KEY,DEEPSEEK_BASE_URL; "
            "values=json.loads(Path(sys.argv[1]).read_text()); "
            "assert DEEPSEEK_API_KEY==values['DEEPSEEK_API_KEY']; "
            "assert DEEPSEEK_BASE_URL==values['DEEPSEEK_BASE_URL']"
        )
        try:
            docker("exec", container, "python", "-c", verify_settings, temporary_secret)
        except DeploymentError as exc:
            raise DeploymentError("Container environment overrides the requested model settings") from exc
        docker("restart", container)
        print("Checking HTTP startup and the deployed UI...", flush=True)
        deadline = time.monotonic() + 60
        verify_http = (
            "from urllib.request import build_opener,ProxyHandler; "
            "o=build_opener(ProxyHandler({})); "
            "assert o.open('http://127.0.0.1:8000/health', timeout=3).status==200; "
            "html=o.open('http://127.0.0.1:8000/ui/', timeout=3).read().decode(); "
            "assert '20261112-ui6' in html"
        )
        while True:
            try:
                docker("exec", container, "python", "-c", verify_http, timeout=10)
                break
            except DeploymentError:
                if time.monotonic() >= deadline:
                    raise DeploymentError("HTTP startup verification timed out")
                time.sleep(1)
        print("PASS: API startup and UI6; checking the real DeepSeek response...", flush=True)
        verify_model = (
            "import json; from campusmind.config import ACTIVE_LLM,MAIN_MODEL_NAME,main_llm; "
            "assert ACTIVE_LLM=='deepseek'; "
            "r=main_llm.invoke('Reply with the single word OK.', timeout=20, max_tokens=8); "
            "assert r.content; "
            "print(json.dumps({'provider':'deepseek','model':MAIN_MODEL_NAME,'response_ok':True}))"
        )
        result = json.loads(docker("exec", container, "python", "-c", verify_model))
        print(json.dumps(result))
        print("CM_DEEPSEEK_DEPLOYMENT_PASSED", flush=True)
    except Exception:
        if changed:
            print("Update failed; restoring the previous runtime files...", flush=True)
            docker("cp", str(backup / "config.py"), f"{container}:/app/src/campusmind/config.py")
            docker("cp", str(backup / "dist") + "/.", f"{container}:/app/frontend/dist")
            if has_dotenv:
                docker("cp", str(backup / ".env"), f"{container}:/app/.env")
            else:
                docker("exec", container, "python", "-c",
                       "from pathlib import Path; Path('/app/.env').unlink(missing_ok=True)")
            docker("restart", container)
            print("Previous runtime files restored; private backups retained.", flush=True)
        raise
    finally:
        (payload / "credentials.json").unlink(missing_ok=True)
        (stage / "update.tar.gz").unlink(missing_ok=True)
        if changed:
            docker("exec", container, "python", "-c",
                   "import sys; from pathlib import Path; Path(sys.argv[1]).unlink(missing_ok=True)",
                   temporary_secret)


def deploy(ssh_target: str, container: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+", ssh_target):
        raise DeploymentError("Use an SSH destination in username@hostname form")
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise DeploymentError("Build the frontend before deployment")
    credentials = export_credentials()
    remote_stage = f"/tmp/campusmind-deepseek-{uuid4().hex}"
    ssh = ["ssh", "-o", "StrictHostKeyChecking=yes"]
    with tempfile.TemporaryDirectory(prefix="campusmind-deepseek-") as directory:
        stage = Path(directory)
        build_bundle(stage, credentials)
        shutil.copy2(__file__, stage / "deploy_deepseek.py")
        print("Preparing a private update directory on Ubuntu...", flush=True)
        subprocess.run([*ssh, ssh_target, f"umask 077; mkdir {shlex.quote(remote_stage)}"], check=True)
        subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=yes", "update.tar.gz", "deploy_deepseek.py",
             f"{ssh_target}:{remote_stage}/"], cwd=stage, check=True,
        )
        command = (
            f"sudo python3 {shlex.quote(remote_stage)}/deploy_deepseek.py "
            f"--apply {shlex.quote(remote_stage)} --container {shlex.quote(container)}"
        )
        subprocess.run([*ssh, "-t", ssh_target, command], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh", help="existing SSH destination, e.g. operator@ubuntu-host")
    parser.add_argument("--container", default="campusmind-api")
    parser.add_argument("--apply", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.apply:
            apply_update(args.apply, args.container)
        elif args.ssh:
            deploy(args.ssh, args.container)
        else:
            parser.error("--ssh is required")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        message = str(exc) if isinstance(exc, DeploymentError) else type(exc).__name__
        print(f"FAIL: DeepSeek deployment: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
