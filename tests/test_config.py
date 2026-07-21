import os

from split_peel.config import load_dotenv


def test_load_dotenv_sets_missing_values(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("SPLIT_PEEL_VOICE_PROVIDER=openai\nQUOTED='value'\n", encoding="utf-8")
    monkeypatch.delenv("SPLIT_PEEL_VOICE_PROVIDER", raising=False)
    monkeypatch.delenv("QUOTED", raising=False)

    load_dotenv(env_path)

    assert os.environ["SPLIT_PEEL_VOICE_PROVIDER"] == "openai"
    assert os.environ["QUOTED"] == "value"
