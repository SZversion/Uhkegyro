# 외부 MCP client 호출 증거 (작업 16)

## 검증 범위와 현재 상태

- 2026-09-29, Windows / Python 3.14, `main` 기준 `75b749d`에서 별도 프로세스의 MCP Python SDK client가 Streamable HTTP `/mcp`에 접속했다.
- 로컬 FastMCP 단독 실행: tool 목록, 활성 카드 `found`, 미등록 카드 `not_found` 검증 **통과**.
- 배포 IAM 접근 제어: **미검증**. `gcloud run services list --region=asia-northeast3 --project=proj2-509406` 결과 서비스가 없고 `mcp` describe는 `Cannot find service [mcp]`였다. 배포 서비스·호출자 권한이 준비되면 아래 절차를 실행해야 AC-04의 배포 증거가 완성된다.
- 현재 `backend.mcp.main:app` 실행은 `/mcp` 초기화 요청에서 HTTP 500(`Task group is not initialized. Make sure to use run().`)이다. 로컬 성공 결과는 `FastMCP.run(transport="streamable-http")`의 결과이며 이 마운트 오류나 Cloud Run 경로의 성공을 뜻하지 않는다.

## 로컬 재현

저장소 루트에서 터미널 두 개를 사용한다. 첫 터미널:

```powershell
python -c "from backend.mcp.server import mcp; mcp.settings.host='127.0.0.1'; mcp.settings.port=8765; mcp.run(transport='streamable-http')"
```

둘째 터미널 (서버 코드 내부 함수가 아닌 별도 MCP client 프로세스):

```powershell
python scripts/mcp_client_evidence.py
```

2026-09-29 실행 출력 (`8765` 포트가 점유되어 당시에는 `8766`을 사용):

```json
{
  "tools": ["get_active_term_card"],
  "found": {
    "status": "found",
    "catalog_version": "0.8-json-runtime-catalog-reviewed",
    "term_id": "pose_contrapposto",
    "role": "pose"
  },
  "not_found": {
    "status": "not_found",
    "reason_code": "TERM_NOT_ACTIVE"
  }
}
```

스크립트는 실제 `list_tools`·`call_tool` 결과를 계약 필드와 대조한 뒤 위 최소 결과만 출력한다. 토큰, 세션 ID, 카드의 검색 조각은 출력하지 않는다. 반환 코드 0은 세 검증 통과를 뜻한다.

## Cloud Run 배포 후 접근 제어 재현

`backend.mcp.main:app`의 500 오류를 먼저 수정하고 Cloud Run `mcp` 서비스를 IAM 보호(`--no-allow-unauthenticated`)로 배포해야 한다. 허용 호출자 서비스 계정에는 `roles/run.invoker`가 필요하다. 다음 PowerShell 절차는 허용된 호출자 권한을 가진 운영자가 실행한다.

```powershell
$mcpServiceUrl = gcloud run services describe mcp --region=asia-northeast3 --project=proj2-509406 --format='value(status.url)'
$env:MCP_ID_TOKEN = gcloud auth print-identity-token --impersonate-service-account='mcp-caller@proj2-509406.iam.gserviceaccount.com' --audiences=$mcpServiceUrl
python scripts/mcp_client_evidence.py --url "$mcpServiceUrl/mcp" --check-denied
Remove-Item Env:MCP_ID_TOKEN
```

`--check-denied`는 **무인증 초기화 요청이 401 또는 403**인지 먼저 확인하고, 같은 endpoint에 ID token을 넣어 도구 목록·`found`·`not_found`를 호출한다. 성공하면 출력에 `anonymous_http_status`가 추가된다. 실제 운영 실행 날짜, 서비스 URL, 상태 코드와 축약 결과를 이 문서 및 데모에 기록해야 한다. ID token 값과 전체 HTTP 헤더는 기록하지 않는다.

## 연결 정보

| 항목 | 값 |
| --- | --- |
| Transport | Streamable HTTP |
| Endpoint | 로컬 `http://127.0.0.1:8765/mcp`; 운영 `<mcp service URL>/mcp` |
| Tool | `get_active_term_card(term_id: str)` |
| 인증 | 로컬 단독 실행에는 없음; 운영 Cloud Run IAM ID token |
| Client | `scripts/mcp_client_evidence.py` (`mcp` Python SDK의 `ClientSession`) |

브라우저와 Next.js UI는 MCP에 직접 연결하지 않는다. 배포 접근 제어가 검증되기 전에는 로컬 출력만을 운영 증거로 제시하지 않는다.
