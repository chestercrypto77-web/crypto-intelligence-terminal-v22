from __future__ import annotations

from pathlib import Path
import zipfile
import pytest

from v22.core import LiveEvidenceCollector
from v22.runtime.lambda_adapter import InvocationRejected, runtime_from_environment
from scripts.build_v22_lambda_zip import build, inspect


def test_aws_lambda_requires_postgres_neon(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "v22-brain")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'brain.db'}")
    monkeypatch.delenv("V22_ALLOW_EPHEMERAL_SQLITE", raising=False)
    with pytest.raises(InvocationRejected, match="Postgres/Neon"):
        runtime_from_environment()


def test_aws_lambda_defaults_to_live_collector(monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "v22-brain")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-test-pooler.ap-southeast-2.aws.neon.tech/neondb")
    monkeypatch.delenv("V22_COLLECTOR_MODE", raising=False)
    runtime = runtime_from_environment()
    assert runtime.collector_factory is LiveEvidenceCollector


def test_explicit_snapshot_mode_remains_available_in_aws(monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "v22-brain")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-test-pooler.ap-southeast-2.aws.neon.tech/neondb")
    monkeypatch.setenv("V22_COLLECTOR_MODE", "snapshot")
    assert runtime_from_environment().collector_factory is not LiveEvidenceCollector


def test_source_lambda_zip_has_required_root_layout(tmp_path: Path):
    out = build(tmp_path / "lambda.zip", install_deps=False)
    inspect(out, require_deps=False)
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    assert "v22/runtime/lambda_entry.py" in names
    assert "config/v22_live_assets.json" in names
    assert not any(n.startswith("v22/tests/") for n in names)

def test_aws_foundation_template_has_no_schedule_or_database_secret():
    text=(Path(__file__).resolve().parents[2]/'aws'/'v22_lambda_foundation.yaml').read_text()
    assert 'AWS::Lambda::Function' in text
    assert 'AWS::Events::Rule' not in text
    assert 'DATABASE_URL' not in text
    assert 'python3.12' in text
    assert 'ap-southeast-2' not in text  # region comes from stack location, not hardcoded resource


def test_oidc_role_is_repo_and_main_branch_restricted():
    text=(Path(__file__).resolve().parents[2]/'aws'/'v22_github_oidc_deploy_role.yaml').read_text()
    assert 'token.actions.githubusercontent.com:aud' in text
    assert 'ref:refs/heads/main' in text
    assert 'lambda:UpdateFunctionCode' in text
    assert 'lambda:InvokeFunction' in text
    assert 'iam:PassRole' not in text
