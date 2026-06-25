"""UI만 단독 테스트 — 이 파일 실행해서 창 열리면 ui.py는 정상"""
import sys
print("[TEST] ui.py 임포트 중...")
try:
    from jarvis_ai.ui import JarvisUI
    print("[TEST] JarvisUI 임포트 성공")
except Exception as e:
    print(f"[TEST] ❌ 임포트 실패: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

print("[TEST] 창 생성 중...")
try:
    ui = JarvisUI()
    print("[TEST] 창 생성 성공 — 창이 열리면 X 버튼으로 닫으세요")
    ui.root.mainloop()
    print("[TEST] 정상 종료")
except Exception as e:
    print(f"[TEST] ❌ 창 생성 실패: {e}")
    import traceback; traceback.print_exc()
