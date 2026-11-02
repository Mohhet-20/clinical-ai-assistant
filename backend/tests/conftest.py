import os

os.environ["PUBMED_LIVE"] = "false"      # tests must not touch the network
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.pop("OPENAI_API_KEY", None)
os.environ["OPENAI_API_KEY_DISABLED_FOR_TESTS"] = "1"

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def no_external(monkeypatch, tmp_path_factory):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.delenv("ADMIN_API_KEYS", raising=False)
    monkeypatch.setenv("PUBMED_LIVE", "false")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")   # disabled; rate limiting has its own test
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path_factory.getbasetemp() / "audit.jsonl"))
