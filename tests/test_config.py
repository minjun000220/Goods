import os

from config import _load_dotenv


def test_dotenv_loads_without_overriding(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# 주석\nGT_TEST_A=hello\nGT_TEST_B=\"quoted\"\nGT_TEST_EMPTY=\nGT_TEST_KEEP=new\n", encoding="utf-8")
    monkeypatch.setenv("GT_TEST_KEEP", "old")
    for k in ("GT_TEST_A", "GT_TEST_B", "GT_TEST_EMPTY"):
        monkeypatch.delenv(k, raising=False)
    _load_dotenv(env)
    assert os.environ["GT_TEST_A"] == "hello" and os.environ["GT_TEST_B"] == "quoted"
    assert "GT_TEST_EMPTY" not in os.environ          # 빈 값은 '설정 안 함'
    assert os.environ["GT_TEST_KEEP"] == "old"         # 이미 있는 값은 유지
