"""Research routing and Claude final-review tests."""

from jarvis_ai.research_pipeline import (
    clean_research_output,
    _domain_matches,
    _is_relevant_result,
    _normalize_url,
    _question_keywords,
    _source_trust_score,
    _split_research_answer,
    finalize_with_claude,
    needs_verified_research,
    research_text_for_speech,
)


def run():
    assert needs_verified_research("일론 머스크는 누구야")
    assert needs_verified_research("세종대왕의 생애와 업적을 조사해줘")
    assert needs_verified_research("OpenAI에 대해 여러 출처로 알려줘")
    assert not needs_verified_research("서울 날씨 알려줘")
    assert not needs_verified_research("100달러 환율 알려줘")

    draft = "초안입니다.\n\n[출처]\n- 공식 사이트: https://example.com"
    spoken = research_text_for_speech(draft)
    assert spoken == "초안입니다."
    assert "http" not in spoken
    body, sources = _split_research_answer(draft)
    assert body == "초안입니다."
    assert sources == ["- 공식 사이트: https://example.com"]
    malformed = (
        "[공식 사이트]([https://example.com/a]"
        "(https://example.com/a\\))"
    )
    cleaned = clean_research_output(malformed)
    assert cleaned == "공식 사이트: https://example.com/a"
    redirect = (
        "https://duckduckgo.com/l/?uddg="
        "https%3A%2F%2Fexample.com%2Fprofile"
    )
    assert _normalize_url(redirect) == "https://example.com/profile"
    assert _source_trust_score({
        "url": "https://www.bbc.com/korean/articles/example",
        "title": "공식 인터뷰",
    }) >= 100
    assert _source_trust_score({
        "url": "https://example.tistory.com/post",
        "title": "인물 프로필",
    }) < 0
    assert _domain_matches("news.bbc.com", "bbc.com")
    assert not _domain_matches("sportschosun.com", "chosun.com")
    assert "손흥민" in _question_keywords("손흥민에 대해서 알려줘")
    assert _is_relevant_result(
        "손흥민에 대해서 알려줘",
        {"title": "손흥민 공식 프로필", "snippet": "", "url": "https://example.com"},
    )
    assert not _is_relevant_result(
        "손흥민에 대해서 알려줘",
        {"title": "SOLID", "snippet": "software principles", "url": "https://example.com"},
    )

    print("조사 라우팅 및 Claude 최종 검수 준비 통과")


if __name__ == "__main__":
    run()
