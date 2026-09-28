"""LLM 호출은 이 파일 하나로 모읍니다.

라우터나 UI 코드가 openai를 직접 import하지 않게 하세요.
3차에서 이 파일 내부만 갈아끼우면 나머지는 그대로 돌아갑니다.

여기서 책임지는 것:
  - 출력 계약 검증 (Pydantic)
  - LLM 오류 분류와 구조화 출력 검증
  - 현재 job trace에 LLM 호출 observation 남기기

재시도·lease·backoff·최종 failure code는 worker가 책임진다. 이 파일은 현재 구현 전 경계만 선언하며, 다음 작업자는
`job_id`, `session_id`, `attempt`, `max_attempts` 관측 context를 받아 job당 trace에 연결해야 한다.
"""
# TODO: 구현
