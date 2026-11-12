import io
import json
import tarfile
from types import SimpleNamespace

import pytest

from scripts import deploy_deepseek as deployment


def make_source(tmp_path, monkeypatch):
    root = tmp_path / "source"
    (root / "src/campusmind").mkdir(parents=True)
    (root / "src/campusmind/config.py").write_text('ACTIVE_LLM = "deepseek"\n')
    (root / "frontend/dist").mkdir(parents=True)
    (root / "frontend/dist/index.html").write_text("ui6")
    (root / ".env").write_text(
        "DEEPSEEK_API_KEY=synthetic-deepseek-key\nPOSTGRES_PASSWORD=private-db-sentinel\n"
    )
    monkeypatch.setattr(deployment, "ROOT", root)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    return root


def test_export_only_contains_model_credentials(tmp_path, monkeypatch):
    make_source(tmp_path, monkeypatch)
    credentials = deployment.export_credentials()
    assert credentials == {
        "DEEPSEEK_API_KEY": "synthetic-deepseek-key",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    }
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-environment-key")
    assert deployment.export_credentials()["DEEPSEEK_API_KEY"] == "synthetic-environment-key"


def test_endpoint_error_does_not_disclose_embedded_credentials(tmp_path, monkeypatch):
    make_source(tmp_path, monkeypatch)
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://operator:private-sentinel@example.com")
    with pytest.raises(deployment.DeploymentError) as error:
        deployment.export_credentials()
    assert "private-sentinel" not in str(error.value)


def test_update_bundle_excludes_other_environment_credentials(tmp_path, monkeypatch):
    make_source(tmp_path, monkeypatch)
    stage = tmp_path / "stage"
    stage.mkdir()
    archive = deployment.build_bundle(stage, deployment.export_credentials())
    with tarfile.open(archive) as bundle:
        assert ".env" not in bundle.getnames()
        credentials = json.load(bundle.extractfile("credentials.json"))
        assert set(credentials) == {"DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"}
        for member in bundle.getmembers():
            if member.isfile():
                assert b"private-db-sentinel" not in bundle.extractfile(member).read()


@pytest.mark.parametrize("kind", ["traversal", "symlink"])
def test_archive_cannot_write_outside_private_stage(tmp_path, kind):
    archive = tmp_path / "update.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        info = tarfile.TarInfo("../outside" if kind == "traversal" else "link")
        if kind == "symlink":
            info.type = tarfile.SYMTYPE
            info.linkname = "../outside"
            bundle.addfile(info)
        else:
            info.size = 4
            bundle.addfile(info, io.BytesIO(b"data"))
    with pytest.raises(deployment.DeploymentError):
        deployment.extract_bundle(archive, tmp_path / "payload")
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize("model_ok,has_dotenv", [(True, True), (False, True), (False, False)])
def test_apply_verifies_model_and_restores_files_on_failure(
    tmp_path, monkeypatch, capsys, model_ok, has_dotenv,
):
    make_source(tmp_path, monkeypatch)
    stage = tmp_path / "stage"
    stage.mkdir()
    deployment.build_bundle(stage, deployment.export_credentials())
    monkeypatch.setattr(deployment, "os", SimpleNamespace(name="posix", geteuid=lambda: 0))
    calls = []

    def fake_docker(*args, **kwargs):
        calls.append(args)
        if args[0] == "inspect":
            return json.dumps([{
                "State": {"Running": True}, "HostConfig": {"NetworkMode": "host"},
                "Config": {"WorkingDir": "/app"},
            }])
        if args[0] == "cp" and args[1].startswith("campusmind-api:"):
            target = deployment.Path(args[2])
            if target.name == "dist":
                target.mkdir()
                (target / "index.html").write_text("old-ui")
            else:
                target.write_text("private-backup-sentinel")
        if args[0] == "exec" and "Path('/app/.env').exists()" in args[-1]:
            return str(int(has_dotenv))
        if args[0] == "exec" and "main_llm.invoke" in args[-1]:
            if not model_ok:
                raise deployment.DeploymentError("Docker exec failed")
            return json.dumps({"provider": "deepseek", "model": "test-model", "response_ok": True})
        return ""

    monkeypatch.setattr(deployment, "docker", fake_docker)
    if model_ok:
        deployment.apply_update(stage, "campusmind-api")
    else:
        with pytest.raises(deployment.DeploymentError):
            deployment.apply_update(stage, "campusmind-api")
        assert any(args[0] == "cp" and args[1] == str(stage / "backup/config.py") for args in calls)
        if has_dotenv:
            assert any(args[0] == "cp" and args[1] == str(stage / "backup/.env") for args in calls)
        else:
            assert any(args[0] == "exec" and "Path('/app/.env').unlink" in args[-1] for args in calls)
    assert not (stage / "update.tar.gz").exists()
    assert not (stage / "payload/credentials.json").exists()
    assert any(args[0] == "exec" and "unlink(missing_ok=True)" in args[-2] for args in calls if len(args) > 2)
    output = capsys.readouterr()
    if model_ok:
        assert "CM_DEEPSEEK_DEPLOYMENT_PASSED" in output.out
    else:
        assert "Previous runtime files restored" in output.out
    assert "synthetic-deepseek-key" not in output.out + output.err
    assert "private-backup-sentinel" not in output.out + output.err
