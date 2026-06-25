"""Research routing and Gemini fallback tests."""

import os

from jarvis_ai.research_pipeline import (
    needs_verified_research,
    research_text_for_speech,
    review_with_gemini,
)


def run():
    assert needs_verified_research("일론 머스크는 누구야")
    assert needs_verified_research("세종대왕의 생애와 업적을 조사해줘")
    assert needs_verified_research("OpenAI에 대해 여러 출처로 알려줘")
    assert not needs_verified_research("서울 날씨 알려줘")
    assert not needs_verified_research("100달러 환율 알려줘")

    previous = os.environ.pop("GEMINI_API_KEY", None)
    try:
        draft = "초안입니다.\n\n[출처]\n- 공식 사이트: https://example.com"
        assert review_with_gemini("질문", draft) == draft
        spoken = research_text_for_speech(draft)
        assert spoken == "초안입니다."
        assert "http" not in spoken
    finally:
        if previous is not None:
            os.environ["GEMINI_API_KEY"] = previous

    print("조사 라우팅 및 Gemini 무키 폴백 통과")


if __name__ == "__main__":
    run()
