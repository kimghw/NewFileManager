# OWPML 2024 XSD — 출처

이 폴더의 `owpml-*.xsd` 5개는 **python-hwpx 6.11.0**(airmang, Apache License 2.0)의 `hwpx/tools/_schemas/` 에서 바꾸지 않고 복사했다
(2026-11-08, PyPI wheel `python_hwpx-6.11.0-py3-none-any.whl` SHA-256 4B8369414DCBF32036CF9AC7F9DBFE3DD78D0F62230969034E6E6B5085912A62).
라이선스 전문: [LICENSE-python-hwpx.txt](LICENSE-python-hwpx.txt).

python-hwpx NOTICE 의 문서 형식 표기를 그대로 옮긴다:

> Parts of this project were developed with reference to the publicly released Hancom file-format documentation (HWP 5.0 / HWPML)
> and the public OWPML schema. As required by that documentation:
> “본 제품은 한글과컴퓨터의 ᄒᆞᆫ글 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.”
>
> "HWPX" is the document format specified and trademarked by Hancom Inc. (한글과컴퓨터). This project is an independent,
> unofficial implementation and is not affiliated with, endorsed by, or sponsored by Hancom Inc.

- 네임스페이스는 `http://www.owpml.org/owpml/2024/{head,paragraph,core,section}` — 한글 2020 저장본(2011 네임스페이스)은
  `app/owpml_check.py` 가 바꿔 넣고 검사한다. 판 차이·한글 저장본과의 불일치는 [references/OWPML_스키마.md](../../references/OWPML_스키마.md).
- 한컴 공식 저장소(hancom-io/hwpx-owpml-model, Apache-2.0)에는 XSD 가 없다(C++ 모델만). 공식 XSD 가 나오면 바꿔 끼운다.
