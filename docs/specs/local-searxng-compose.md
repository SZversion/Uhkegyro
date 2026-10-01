# 로컬 SearXNG Compose 서비스

## Why

- **페르소나·상황**: 로컬 개발 환경에서 검색 provider를 확인하는 백엔드 개발자.
- **문제**: 개발자가 별도 검색 서버를 준비하지 않으면 Compose 환경에서 SearXNG 연결을 검증할 수 없다.
- **측정 지표**: Docker Compose만으로 로컬 SearXNG Search API에 접근할 수 있다.

## Goal

- Compose에 로컬 SearXNG 서비스를 추가하고 MCP 서버가 사용할 내부 주소를 `http://searxng:8080`으로 고정한다.
- JSON Search API와 Google Images 엔진 설정을 제공한다.
- **범위 밖**: SearXNG 외부 배포, 검색 품질 보장, Pinterest 검색 pipeline 연결 자체.

## What

1. Compose가 SearXNG 서비스를 시작한다.
2. MCP 서버는 Compose 네트워크에서 `http://searxng:8080`으로 서비스에 접근한다.
3. 호스트에서는 loopback의 `http://localhost:8080`으로 SearXNG를 확인할 수 있다.
4. 로컬 `.env`의 `SEARXNG_SECRET`으로 인스턴스 비밀값을 전달한다.

## How

- 설정 파일: `searxng/settings.yml`; 기본 설정을 유지하면서 JSON format과 `google images` 엔진을 활성화한다.
- 컨테이너 image: `docker.io/searxng/searxng:latest`.
- 포트 공개: `127.0.0.1:8080:8080`.
- 비밀값은 저장소에 기록하지 않고 `.env`에서만 읽는다.

## AC

- **Given** `.env`에 `SEARXNG_SECRET`과 나머지 Compose 필수값이 설정되어 있을 때, **When** `docker compose config --quiet`를 실행하면, **Then** Compose 설정 검증이 통과한다.
- **Given** Compose 서비스를 시작했을 때, **When** 호스트에서 `http://localhost:8080/search?q=test&format=json`을 요청하면, **Then** SearXNG JSON 응답을 받을 수 있다.
- **Given** Compose 네트워크에 있는 MCP 컨테이너일 때, **When** SearXNG 주소를 사용하면, **Then** `http://searxng:8080`으로 접근한다.
