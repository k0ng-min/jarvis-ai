"""
현재 연결된 모든 마이크 확인 및 테스트
"""

import sounddevice as sd
import speech_recognition as sr

print("="*70)
print("🎤 현재 연결된 마이크 목록")
print("="*70)

devices = sd.query_devices()
print(f"\n총 {len(devices)}개 장치\n")

# 입력 장치만 필터링
input_devices = []
for i, device in enumerate(devices):
    if device['max_input_channels'] > 0:
        input_devices.append((i, device))
        status = "✅ INPUT" if device['max_output_channels'] == 0 else "⚠️ INPUT+OUTPUT"
        print(f"[{i}] {device['name']}")
        print(f"     채널: 입력={device['max_input_channels']}, 출력={device['max_output_channels']}")
        print(f"     상태: {status}\n")

print("="*70)
print("🎤 마이크 테스트")
print("="*70)

if input_devices:
    print(f"\n입력 장치 {len(input_devices)}개 발견\n")

    # 현재 기본 마이크
    default_input = sd.default.device[0]
    print(f"📌 현재 기본 입력: [{default_input}] {devices[default_input]['name']}\n")

    # 각 입력 장치 테스트
    for mic_idx, device_info in input_devices:
        print(f"테스트: [{mic_idx}] {device_info['name']}")
        try:
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = 100

            with sr.Microphone(device_index=mic_idx) as source:
                print(f"  ✅ 마이크 접근 가능")
                recognizer.adjust_for_ambient_noise(source, duration=0.1)
                print(f"  ✅ 배경음 적응 완료")
        except Exception as e:
            print(f"  ❌ 오류: {e}")
        print()
else:
    print("❌ 입력 장치를 찾을 수 없습니다!")

print("="*70)
print("추천: 위 목록에서 USE_MIC_INDEX를 설정하세요")
print("="*70)
