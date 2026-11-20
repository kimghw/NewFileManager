# Microsoft Graph — 부서 메일(공유 사서함·그룹·배포 목록) 읽기

2026-11-18 조회. 「부서 메일」은 Exchange 에서 셋 중 하나이고 읽는 길이 다르다.

| 부서 메일의 정체 | Graph 경로 | 위임 권한(사용자 로그인) | Exchange 쪽 조건 |
|---|---|---|---|
| **공유 사서함**(가장 흔함) | `GET /users/{공유 사서함 주소}/messages` · `/users/{주소}/mailFolders/inbox/messages` | `Mail.Read.Shared`(쓰기 `Mail.ReadWrite.Shared` · 보내기 `Mail.Send.Shared`) | 로그인한 사람에게 그 사서함의 **전체 액세스**(또는 폴더 읽기) 권한이 있어야 한다 — 없으면 403 `ErrorAccessDenied`. `/me` 로는 못 읽는다 |
| **Microsoft 365 그룹**(팀 메일) | `GET /groups/{그룹 id}/conversations` · `/threads/{id}/posts` | `Group.Read.All` | 그룹 구성원 |
| **배포 목록**(DL)·메일 사용 보안 그룹 | 사서함이 없다 — 메일은 구성원 각자의 받은 편지함에 들어간다 | `Mail.Read`(본인 메일함) | 본인 메일함에서 `$search="to:{DL 주소}"` 로 찾는다 |

- 실측(2026-11-18): 위임 `Mail.Read.Shared` 가 든 토큰으로 `GET /users/{공유 사서함 주소}/mailFolders/inbox/messages` → 200. 로그인 계정이 그 사서함 권한을 가진 경우.
- 앱 권한(`Mail.Read` application · 관리자 동의)이면 어느 사서함이든 읽을 수 있지만, 테넌트 관리자가 Application Access Policy 로 범위를 묶는 경우가 많다.
- 토큰을 `https://graph.microsoft.com/.default` 로 받으면 앱 등록에 동의된 권한이 전부 토큰의 `scp` 에 들어온다 — 무엇이 되는지는 JWT 의 `scp` 클레임을 보면 안다.
