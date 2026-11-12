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
