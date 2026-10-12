import os

os.environ["PUBMED_LIVE"] = "false"      # tests must not touch the network
os.environ.pop("OPENAI_API_KEY", None)
os.environ["OPENAI_API_KEY_DISABLED_FOR_TESTS"] = "1"

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PUBMED_LIVE", "false")
