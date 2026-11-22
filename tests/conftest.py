"""모든 테스트에 공통으로 적용하는 설정."""
import pytest


@pytest.fixture(autouse=True)
def _llm_explain_off(monkeypatch):
    # app.py가 .env를 읽으므로, .env에 OPENSESAME_FINAL_EXPLAIN=llm을 켜 둔 채 pytest를 돌리면
    # 다른 테스트가 실제 LLM을 불러 크레딧이 나갈 수 있다(#17 리뷰 3). 테스트마다 끄고 시작한다.
    # 켜야 하는 테스트는 그 안에서 monkeypatch.setenv로 다시 켠다.
    monkeypatch.delenv("OPENSESAME_FINAL_EXPLAIN", raising=False)
