"""pytest 전체를 **병렬로** — 두 묶음을 같이 돌린다(2026-11-12 사용자 "서버 테스트 시간을 좀 줄이도록 병렬로").

    python -X utf8 tools/run_pytest.py [--jobs 6] [--tmp <임시 폴더>] [pytest 인자 … 예: -k merge -x]

① 병렬 묶음: tests/ 에서 아래 COM 파일을 뺀 나머지 — pytest-xdist 로 일꾼 여러 개, 파일 단위 분배(--dist loadfile: 모듈 범위 픽스처가 일꾼마다 다시 만들어지지 않게).
② 차례 묶음: 한글·Word(COM)를 띄울 수 있는 파일 — 프로그램 하나를 여러 시험이 동시에 잡지 않게 한 프로세스에서 차례로.
실측(2026-11-12 · 8코어 · 일꾼 6): 전체 358초 = 병렬 묶음 718개 356초 ∥ 차례 묶음 63개 84초 — 한 줄로 돌리면 약 15분. 화면 검사(tools/run_ui_gates.py)와는 같이 돌리지 않는다(부하로 API 시험이 떨어진다).
임시 폴더는 E: 에(C: 가 차면 시험이 무더기로 떨어진다 — 기본 artifacts/pytest_tmp, pytest 가 시작할 때 비운다). 하나라도 떨어지면 종료 코드 1."""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COM = ["test_pdf_render.py", "test_pdf_style.py", "test_upload_hwp.py", "test_docx_web.py", "test_server.py", "test_works.py", "test_style_verify_pdf.py"]  # pdf_render·win32com 을 만지는 파일(grep 으로 고름 — 새로 생기면 여기에 더한다)
ap = argparse.ArgumentParser()
ap.add_argument("--jobs", type=int, default=6)
ap.add_argument("--tmp", default=str(ROOT / "artifacts" / "pytest_tmp"))
args, rest = ap.parse_known_args()
tmp = Path(args.tmp).resolve()
tmp.mkdir(parents=True, exist_ok=True)
base = [sys.executable, "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
groups = {
    "병렬": base + ["tests", "-n", str(args.jobs), "--dist", "loadfile", f"--basetemp={tmp / 'par'}"] + [f"--ignore=tests/{f}" for f in COM] + rest,
    "차례(COM)": base + [f"tests/{f}" for f in COM if (ROOT / "tests" / f).is_file()] + [f"--basetemp={tmp / 'com'}"] + rest,
}
t0, live = time.time(), {}
for name, cmd in groups.items():
    log = (tmp / f"{'par' if name == '병렬' else 'com'}.log").open("w", encoding="utf-8")
    live[name] = (subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"}), log, time.time())
bad = False
for name, (proc, log, started) in live.items():
    code = proc.wait()
    log.close()
    lines = Path(log.name).read_text(encoding="utf-8", errors="replace").splitlines()
    ok = code in (0, 5)  # 5 = 고른 시험이 이 묶음에 없음(-k 로 거른 때)
    bad = bad or not ok
    print(f"{name}: {'통과' if ok else '실패'}(종료 코드 {code}) — {lines[-1].strip() if lines else ''}")
    for x in lines:
        if x.startswith(("FAILED", "ERROR")):
            print("   ", x[:240])
print(f"전체 {time.time() - t0:.0f}초 · 기록 {tmp}")
sys.exit(1 if bad else 0)
