"""한글 자동화 보안 모듈 등록 — COM(`HWPFrame.HwpObject`)으로 파일을 열 때 뜨는 「파일 접근 허용」 확인 창을 없앤다(2026-11-01 사용자 요청).

한글 환경 설정 메뉴에는 이 창을 끄는 항목이 없다. 공식 방법은 자동화 보안 모듈 DLL 을 레지스트리에 등록하고 스크립트가
`RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")` 을 부르는 것이다(app/render_anchors.py·tools/hwp_to_hwpx.py 는 이미 부른다).

  레지스트리: HKCU\\Software\\HNC\\HwpAutomation\\Modules — 값 이름 FilePathCheckerModule(REG_SZ) = DLL 경로
  DLL: 한컴이 배포하는 FilePathCheckerModule(Example).dll — pyhwpx 휠(pyhwpx/FilePathCheckerModule.dll)에 들어 있다.

usage:
  python tools/hwp_register_module.py                 # pip download pyhwpx → DLL 꺼내 %LOCALAPPDATA%\\NewFileManager\\ 에 두고 등록
  python tools/hwp_register_module.py --dll <경로>    # 이미 있는 DLL 을 등록
  python tools/hwp_register_module.py --check <hwpx>  # 등록 뒤 확인: 창 숨긴 한글로 열어 RegisterModule·Open 결과 출력(확인 창이 뜨면 멈춤)
  python tools/hwp_register_module.py --status        # 등록 상태만
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
import winreg
import zipfile
from pathlib import Path

KEY = r"Software\HNC\HwpAutomation\Modules"
NAME = "FilePathCheckerModule"
DEST = Path(os.environ.get("LOCALAPPDATA", ".")) / "NewFileManager" / "FilePathCheckerModule.dll"


def status():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            v, _ = winreg.QueryValueEx(k, NAME)
    except OSError:
        return None
    return v


def fetch_dll(dest):
    """pyhwpx 휠을 임시 폴더에 내려받아 DLL 만 꺼낸다(패키지는 설치하지 않음)."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, "-m", "pip", "download", "pyhwpx", "--no-deps", "-q", "-d", tmp], check=True)
        whl = next(Path(tmp).glob("pyhwpx-*.whl"))
        with zipfile.ZipFile(whl) as z:
            data = z.read("pyhwpx/FilePathCheckerModule.dll")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def register(dll):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, str(dll))


def check(src):
    import win32com.client
    hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
    print("RegisterModule:", hwp.RegisterModule("FilePathCheckDLL", NAME), flush=True)
    try:
        hwp.XHwpWindows.Item(0).Visible = False
    except Exception as e:
        print("창 숨김 실패:", e, flush=True)
    t0 = time.time()
    print("Open:", hwp.Open(str(Path(src).resolve()), "HWPX", "forceopen:true"), f"{time.time() - t0:.1f}s", flush=True)
    hwp.Clear(1)
    hwp.Quit()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dll", help="등록할 DLL 경로(없으면 pyhwpx 휠에서 꺼냄)")
    ap.add_argument("--check", metavar="HWPX", help="등록 뒤 한글 COM 으로 열어 확인")
    ap.add_argument("--status", action="store_true", help="등록 상태만 보고 끝")
    a = ap.parse_args()
    cur = status()
    print("지금 등록:", cur or "(없음)", "| 파일 있음" if cur and Path(cur).exists() else "")
    if a.status:
        return
    if not a.check or not cur:
        dll = Path(a.dll).resolve() if a.dll else (Path(cur) if cur and Path(cur).exists() else fetch_dll(DEST))
        if not dll.exists():
            sys.exit(f"DLL 없음: {dll}")
        register(dll)
        print("등록:", f"HKCU\\{KEY}\\{NAME} =", dll)
    if a.check:
        check(a.check)


if __name__ == "__main__":
    main()
