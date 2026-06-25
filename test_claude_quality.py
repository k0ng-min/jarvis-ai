"""Claude 설명·추론·복잡 대화 응답 품질/속도 확인."""

import time

import main


PROMPTS = [
    "하늘이 파랗게 보이는 이유를 중학생도 이해하게 두 문장으로 설명해줘.",
    (
        "철수는 영희보다 키가 크고 영희는 민수보다 키가 크다. "
        "세 사람 중 누가 가장 작은지 이유와 함께 답해줘."
    ),
    (
        "나는 예산 120만원이고 학교 과제, 파이썬 개발, 가벼운 영상 편집을 하며 "
        "무게를 중요하게 생각해. 노트북을 고를 때 우선순위와 타협점을 "
        "세 문장으로 정리해줘."
    ),
]


def main_test():
    system_prompt = main._load_system_prompt()
    for index, prompt in enumerate(PROMPTS, 1):
        started = time.monotonic()
        response = main._call_claude(prompt, system_prompt)
        elapsed = time.monotonic() - started
        print(f"\n[{index}] {prompt}")
        print(f"{elapsed:.1f}초 | {response}")
        if not response:
            raise AssertionError(f"{index}번 Claude 응답이 비어 있습니다.")


if __name__ == "__main__":
    main_test()
