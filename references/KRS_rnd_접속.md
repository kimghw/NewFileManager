# rnd.krs.co.kr 접속 경로

2026-11-18 실측(이 PC = Azure VM — IP 10.0.0.5 · DNS 168.63.129.16 · 공인 IP 20.196.66.231).

## 두 길

| 길 | 주소 | 이 VM 에서 |
|---|---|---|
| 사내 | 10.200.90.40 — 사내 안내대로 hosts 에 `10.200.90.40 rnd.krs.co.kr` 를 넣어 씀 | 닿지 않음(ping · 80 · 443 모두 시간 초과, tracert 첫 홉부터 응답 없음) — 사내망 · VPN 이 있어야 함 |
| 공개 | 공개 DNS: `rnd.krs.co.kr` → CNAME `prod-int-…a01.azurefd.net`(Azure Front Door) → 150.171.110.x | 연결은 되나 **403 「The request is blocked.」**(Front Door WAF — 허용 목록에 없는 IP 를 막는 것으로 보임) |

- hosts 항목이 있으면 공개 길은 쓰이지 않는다 — 공개 길을 쓰려면 그 줄을 지운다(백업 `C:\Windows\System32\drivers\etc\hosts.bak_2026-11-18` = 넣기 전 파일).
- hosts 를 건드리지 않고 공개 길만 시험: `curl.exe -k --resolve rnd.krs.co.kr:443:150.171.110.135 https://rnd.krs.co.kr/`.
- VPN 없이 이 VM 에서 쓰려면: IT 에 Front Door WAF 허용 목록에 이 VM 공인 IP 추가를 청하거나(공인 IP 가 고정인지 먼저 확인), Azure VNet ↔ 사내망 연결(사이트 간 VPN · ExpressRoute)을 청한다.
