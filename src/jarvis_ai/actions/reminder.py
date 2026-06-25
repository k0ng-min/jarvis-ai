# actions/reminder.py — 자비스 알림 설정 (Windows 작업 스케줄러)

import subprocess
import os
import sys
from datetime import datetime


def reminder(parameters: dict, response=None, player=None, session_memory=None) -> str:
    date_str = parameters.get("date")
    time_str = parameters.get("time")
    message  = parameters.get("message", "알림")

    if not date_str or not time_str:
        return "날짜와 시간을 모두 알려주세요."

    try:
        target_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

        if target_dt <= datetime.now():
            return "이미 지난 시간입니다."

        task_name    = f"JarvisReminder_{target_dt.strftime('%Y%m%d_%H%M')}"
        safe_message = message.replace('"', '').replace("'", "").strip()[:200]

        python_exe = sys.executable
        if python_exe.lower().endswith("python.exe"):
            pythonw = python_exe.replace("python.exe", "pythonw.exe")
            if os.path.exists(pythonw):
                python_exe = pythonw

        temp_dir      = os.environ.get("TEMP", "C:\\Temp")
        notify_script = os.path.join(temp_dir, f"{task_name}.pyw")
        project_root  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        script_code = f'''import sys, os, time
sys.path.insert(0, r"{project_root}")

try:
    import winsound
    for freq in [800, 1000, 1200]:
        winsound.Beep(freq, 200)
        time.sleep(0.1)
except Exception:
    pass

try:
    from win10toast import ToastNotifier
    ToastNotifier().show_toast(
        "자비스 알림",
        "{safe_message}",
        duration=15,
        threaded=False
    )
except Exception:
    try:
        import subprocess
        subprocess.run(["msg", "*", "/TIME:30", "{safe_message}"], shell=True)
    except Exception:
        pass

time.sleep(3)
try:
    os.remove(__file__)
except Exception:
    pass
'''
        with open(notify_script, "w", encoding="utf-8") as f:
            f.write(script_code)

        xml_content = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>자비스 알림: {safe_message}</Description></RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{target_dt.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Actions>
    <Exec>
      <Command>{python_exe}</Command>
      <Arguments>"{notify_script}"</Arguments>
    </Exec>
  </Actions>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Principals>
    <Principal>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
</Task>'''

        xml_path = os.path.join(temp_dir, f"{task_name}.xml")
        with open(xml_path, "w", encoding="utf-16") as f:
            f.write(xml_content)

        result = subprocess.run(
            f'schtasks /Create /TN "{task_name}" /XML "{xml_path}" /F',
            shell=True, capture_output=True, text=True
        )
        try:
            os.remove(xml_path)
        except Exception:
            pass

        if result.returncode != 0:
            try:
                os.remove(notify_script)
            except Exception:
                pass
            return "알림을 설정하는 중 시스템 오류가 발생했습니다."

        if player:
            player.write_log(f"[알림] {date_str} {time_str} 설정 완료")

        return f"{target_dt.strftime('%m월 %d일 %H:%M')}에 알림이 설정되었습니다."

    except ValueError:
        return "날짜/시간 형식을 이해할 수 없습니다."
    except Exception as e:
        return f"알림 설정 오류: {str(e)[:80]}"
