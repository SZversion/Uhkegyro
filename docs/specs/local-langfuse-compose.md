# Local Langfuse Compose

## Why

로컬 개발자가 Docker Compose에서 Langfuse UI를 사용해 LLM 관측 데이터를 확인할 수 있어야 한다.

## Goal

- Compose로 애플리케이션과 로컬 Langfuse를 실행한다.
- Langfuse UI는 `http://localhost:3000`에서 연다.
- Langfuse 저장 서비스는 앱의 Neon `DATABASE_URL`과 분리한다.
- Out of Scope: worker trace lifecycle, 운영 배포, 원격 Prompt·Dataset 설정.

## What

- Langfuse web·worker와 구동에 필요한 PostgreSQL, ClickHouse, Redis, MinIO만 로컬 서비스로 실행한다.
- Langfuse 데이터는 named volume에 보관한다.
- 애플리케이션 API는 Compose 내부 주소 `http://langfuse-web:3000`을 사용한다.

## How

- Langfuse v4 공식 컨테이너 이미지와 해당 버전의 필수 저장 서비스만 사용한다.
- Langfuse 앱의 내부 인증값은 `.env.example`에 명시하고 `.env`에서 제공한다.
- 호스트에 공개하는 Langfuse UI는 `127.0.0.1:3000`으로 제한한다. MinIO는 로컬 브라우저 업로드 URL인 `127.0.0.1:9090`만 공개한다.
- API Dockerfile은 기존 requirements에서 이미 Langfuse SDK를 설치하므로 변경하지 않는다.

## AC

- GIVEN: Docker Compose와 필수 `.env` 값이 준비되어 있다. WHEN: `docker compose config --quiet`를 실행한다. THEN: 구성 검증이 통과한다.
- GIVEN: Compose 서비스가 정상 기동했다. WHEN: 호스트에서 `http://localhost:3000`을 연다. THEN: Langfuse UI가 표시된다.
- GIVEN: Compose의 API 서비스가 실행 중이다. WHEN: API가 `LANGFUSE_HOST`를 읽는다. THEN: `http://langfuse-web:3000`에 연결한다.
- GIVEN: `docker compose down`으로 서비스를 중지한다. WHEN: named volume을 확인한다. THEN: Langfuse 저장 데이터가 유지된다.
