# Pin 검색 엔진 장애 복구

## Why
- 팀 시연자는 Google Images가 403을 반환할 때 모든 Pin 검색을 잃는다.
- 지표: 실제 Pin 반환, 엔진별 장애/정상 빈 결과 구분, 호출 수 상한.
## Goal
- Google Images 장애 시 SearXNG DuckDuckGo Images, Pinterest 엔진을 순차 fallback으로 사용한다.
- 범위 밖: 차단/CAPTCHA 우회, 이미지 저장, URL 검증 완화, 결과 조작.
## What
- 기본 Google 결과에 유효 Pin이 있으면 반환한다.
- Google HTTP/엔진 장애 또는 유효 Pin 0건이면 DuckDuckGo Images, 이어서 Pinterest 엔진을 각 1회 호출한다. 유효 Pin이 발견되면 즉시 종료한다.
- 정상 응답이 하나라도 있고 전체 유효 Pin 0건이면 PIN_RESULTS_EMPTY, 모두 장애이면 PIN_SEARCH_UNAVAILABLE.
- 장애 엔진에서 유효 Pin이 왔으면 보존하되 unavailable 표시를 유지한다.
## How
- `!goi` 다음 `!ddi`, `!pin`, images/json/en과 기존 suffix·site 제한·HTTPS Pinterest 숫자 Pin 정규화를 유지한다. 공식 SearXNG 엔진만 사용한다.
- 엔진당 timeout 15초, provider 호출당 최대 3회. worker의 기존 재시도 상한 유지.
- SearXNG settings에서 세 엔진을 활성화하고 sidecar 내부 요청임을 나타내는 loopback X-Forwarded-For/X-Real-IP를 보낸다. limiter 보호는 해제하지 않는다.
## AC
- Given Google 장애와 DuckDuckGo 유효 Pin, When 검색, Then 두 번 이하 호출로 실제 Pin을 반환한다.
- Given Google 유효 Pin, When 검색, Then DuckDuckGo 호출이 없다.
- Given Google와 DuckDuckGo 장애, When Pinterest 엔진이 유효 Pin을 반환, Then 3회 이하 호출로 정상 Pin을 반환한다.
- Given 모두 장애/정상 빈 결과, When 검색, Then 각각 unavailable/empty를 반환한다.
- Given 외부/중복/비정상 Pin URL, When 어느 엔진에서 반환, Then 기존 필터·8개 상한이 유지된다.

엔진 선택 문법은 [SearXNG 공식 엔진 목록](https://docs.searxng.org/user/configured_engines.html)의 goi/ddi/pin을 따른다.

- Given term-search HTTP 테스트가 모든 엔진 장애를 모사, When fallback 검색 실행, Then 세 엔진 모두 unresponsive로 지정되어 PIN_SEARCH_UNAVAILABLE을 검증한다.
