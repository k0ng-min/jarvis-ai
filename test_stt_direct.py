"""
Google Speech-to-Text API 직접 테스트
생성된 음성 파일로 인식 테스트
"""

import speech_recognition as sr
import asyncio
import os

print("[테스트] 한국어 음성 파일 생성 중...")

# edge-tts로 "자비스 안녕" 음성 생성
try:
    import edge_tts

    async def create_test_audio():
        text = "자비스 안녕"
        communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
        with open("test_voice.wav", "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])

    asyncio.run(create_test_audio())
    print("[테스트] ✅ 음성 파일 생성 완료: test_voice.wav")
except Exception as e:
    print(f"[테스트] ❌ 음성 생성 실패: {e}")
    exit(1)

# 생성한 음성을 STT로 인식
print("[테스트] Google Speech-to-Text 테스트 중...")
try:
    recognizer = sr.Recognizer()
    with sr.AudioFile("test_voice.wav") as source:
        audio = recognizer.record(source)

    text = recognizer.recognize_google(audio, language="ko-KR")
    print(f"[테스트] ✅ 인식 결과: '{text}'")

except Exception as e:
    print(f"[테스트] ❌ 인식 실패: {e}")

# Whisper 테스트
print("\n[테스트] Whisper 모델 테스트 중...")
try:
    import whisper

    model = whisper.load_model("base")
    result = model.transcribe("test_voice.wav", language="ko")
    print(f"[테스트] ✅ Whisper 인식 결과: '{result['text']}'")

except Exception as e:
    print(f"[테스트] ❌ Whisper 실패: {e}")

# 파일 정리
try:
    os.remove("test_voice.wav")
except:
    pass

print("\n[테스트] 완료")
