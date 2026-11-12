# pytest — 모듈 픽스처는 conftest 의 함수 autouse 픽스처보다 먼저 돈다

## 사실

- pytest 는 시험 하나에 필요한 픽스처를 **범위가 넓은 것부터** 만든다: session → package → module → class → function.
  `autouse=True` 여도 function 범위면 module 범위 픽스처 **뒤에** 돈다.
- 그래서 conftest 의 `@pytest.fixture(autouse=True)` 가 `monkeypatch.setenv(...)` 로 환경 변수(저장 폴더 등)를 임시로 돌려도,
  `@pytest.fixture(scope="module")` 픽스처 안의 코드는 **그 설정 전의 환경**(보통 실제 사용자 경로)으로 돈다.
- 함수 범위 `monkeypatch`·`tmp_path` 는 module 범위 픽스처에서 쓸 수 없다(ScopeMismatch). 대신:
  - 임시 폴더: `tmp_path_factory.mktemp("이름")`
  - 환경 변수: `with pytest.MonkeyPatch.context() as mp: mp.setenv(...); ...; yield ...` — 블록을 나가면 되돌림.
    `os.environ[...] = ...` 로 직접 바꾸면 다음 모듈까지 새어 나간다.
- 모듈 픽스처 안에서 돌려 둔 값 위에 시험마다 function autouse 가 또 setenv 하면, 시험이 끝날 때 **모듈 픽스처가 둔 값으로** 되돌아간다
  (monkeypatch 는 바꾸기 직전 값을 기억). 시험 중 경로를 다시 읽는 코드는 시험별 값을 본다 — 모듈 픽스처가 만든 파일을 시험에서 보려면 경로를 픽스처 결과로 넘긴다.

## 증상 예

- 시험을 돌릴 때마다 실제 사용자 데이터 폴더에 시험 데이터가 하나씩 쌓인다(conftest 는 임시 폴더로 돌렸는데도).
  확인: 모듈 픽스처 목록을 훑어 서버·저장 코드를 부르면서 환경을 스스로 돌리지 않는 것을 찾는다
  (`ast` 로 `@pytest.fixture(scope="module")` 함수 본문에 저장 경로 env 이름이 있는지).
