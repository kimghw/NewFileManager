# Claude API — 구조화 출력(JSON schema) 호출

`app/llm.py` 의 API 길(`_api`)이 쓰는 Anthropic Messages API 의 꼴과 실측. (이 파일은 `app/llm.py` 머리말이 가리키던 이름으로 새로 만든 것 — 2026-11-12.)

## 호출 꼴

- `anthropic.Anthropic(timeout=…, max_retries=0).messages.create(model=…, max_tokens=…, messages=[{"role": "user", "content": 글}],
  output_config={"effort": "low|medium|high", "format": {"type": "json_schema", "schema": 스키마}})`
  → 답의 `content` 가운데 `type == "text"` 블록의 글이 스키마에 맞는 JSON. `stop_reason != "end_turn"`(거절·max_tokens)이면 스키마에 안 맞을 수 있어 실패로 본다.
- 키: env `ANTHROPIC_API_KEY`(또는 `ANTHROPIC_AUTH_TOKEN`). 응답에 비용(USD)이 없다 — `costUsd` 는 None(SDK·CLI 길만 비용을 준다).
- 서버 쪽 거절 대체(`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`)는 받는 모델에만 건다(`llm.FALLBACK_MODELS`).

## 실측

- 2026-11-12 `claude-fable-5-2` — 위 꼴 그대로(대체 베타 없이) 됨: 작은 스키마 한 번 6.8초. 이관 2단계 실측(자리 연결 검토 5단위 38초 · 빈 자리 검토 7단위 15초 · 표 대응 3표 25초 — 병렬 4자리)에서 답이 모두 스키마에 맞았다.
- 2026-11-12 `claude-fable-5-2` 생각(thinking)은 늘 켜져 있고 **`max_tokens` 안에서 생각과 답을 같이 센다** — 입력 약 2.8만 토큰·코드 구현 요청을 `effort: high`·`max_tokens: 32000` 으로 보냈더니
  출력 32,000 토큰이 모두 생각에 쓰이고 `stop_reason: max_tokens` · **text 블록 없음**(빈 답, 비용은 그대로 약 $1.5). 같은 요청을 `effort: medium`·`max_tokens: 64000` 으로 다시 보내니 출력 33,422 토큰(답 약 2.6만 자)·`end_turn`.
  긴 답(코드 여러 파일)을 받을 일이면 `max_tokens` 를 6.4만 이상으로 두고, 구조화 출력처럼 짧은 답이어도 `stop_reason == "max_tokens"` 이면 text 가 비었을 수 있다고 보고 실패로 다룬다.
