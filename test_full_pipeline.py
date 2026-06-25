"""
전체 파이프라인 직접 테스트
1. 테스트 음성 생성 (TTS)
2. 생성된 음성 인식 (STT)
3. Wake word 감지
4. 명령어 추출
"""

import asyncio
import speech_recognition as sr
import os
import sys

print("="*70)
print("🎤 자비스 전체 파이프라인 테스트")
print("="*70)

# 1️⃣ 테스트 음성 생성
print("\n[1단계] 테스트 음성 파일 생성 중...")
print("-"*70)

test_cases = [
    "자비스 안녕",
    "헤이 자비스 시간이 뭐야",
    "자비스 날씨 봐줘",
]

import edge_tts

async def create_test_audio(text, filename):
    """TTS로 음성 파일 생성"""
    try:
        communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
        with open(filename, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
        return True
    except Exception as e:
        print(f"❌ 생성 실패: {e}")
        return False

# 모든 테스트 음성 생성
test_files = {}
for i, text in enumerate(test_cases):
    filename = f"test_audio_{i}.wav"
    print(f"생성 중: [{i+1}] '{text}'...", end=" ")
    success = asyncio.run(create_test_audio(text, filename))
    if success:
        print("✅ 완료")
        test_files[text] = filename
    else:
        print("❌ 실패")

print(f"\n생성 완료: {len(test_files)}개 파일")

# 2️⃣ STT 인식 테스트
print("\n[2단계] Speech-to-Text 인식 테스트")
print("-"*70)

recognizer = sr.Recognizer()
recognizer.energy_threshold = 100
recognizer.dynamic_energy_threshold = True

stt_results = {}
for original_text, audio_file in test_files.items():
    print(f"\n📝 원문: '{original_text}'")
    print(f"📁 파일: {audio_file}")

    try:
        with sr.AudioFile(audio_file) as source:
            audio = recognizer.record(source)

        # Google Speech-to-Text
        print("🔍 Google STT 인식 중...", end=" ")
        recognized_text = recognizer.recognize_google(audio, language="ko-KR")
        print("✅")
        print(f"📢 인식: '{recognized_text}'")

        stt_results[original_text] = recognized_text

    except sr.UnknownValueError:
        print("❌ 음성 인식 불가")
        stt_results[original_text] = None
    except Exception as e:
        print(f"❌ 오류: {e}")
        stt_results[original_text] = None

# 3️⃣ Wake Word 감지 테스트
print("\n[3단계] Wake Word 감지 테스트")
print("-"*70)

from main import WakeWordDetector

for original_text, recognized_text in stt_results.items():
    print(f"\n원문: '{original_text}'")
    if recognized_text:
        print(f"인식: '{recognized_text}'")
        wake_word, command = WakeWordDetector.process(recognized_text)
        if wake_word:
            print(f"✅ Wake word 감지: '{wake_word}'")
            if command:
                print(f"📋 명령어: '{command}'")
            else:
                print("⚠️ 명령어 없음")
        else:
            print("❌ Wake word 감지 실패")
    else:
        print("⚠️ STT 인식 실패")

# 4️⃣ 정리
print("\n[정리] 테스트 파일 삭제 중...")
for filename in test_files.values():
    try:
        os.remove(filename)
    except:
        pass

print("\n" + "="*70)
print("✅ 테스트 완료")
print("="*70)

# 결과 요약
print("\n📊 결과 요약:")
print(f"생성된 음성 파일: {len(test_files)}개")
success_count = sum(1 for v in stt_results.values() if v is not None)
print(f"인식 성공: {success_count}/{len(stt_results)}")
