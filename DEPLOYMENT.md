# 배포 가이드: GCP Cloud Run + Vercel (무료 티어)

## 아키텍처 개요 (무료 티어)

```
┌─────────────┐     HTTPS      ┌──────────────────┐
│   Vercel    │ ─────────────► │  Cloud Run (api) │  --min-instances=0 (유휴 시 $0)
│  (Frontend) │   REST + MCP   │  FastAPI + MCP   │  --max-instances=3
└─────────────┘                └────────┬─────────┘
                                        │ Public Internet + SSL
                                        ▼
                               ┌──────────────────┐
                               │  Neon PostgreSQL │  -- Free Tier: 0.5GB storage
                               │  (Free Tier)     │  -- Auto-suspend 5min 유휴
                               └──────────────────┘
```

- **백엔드**: 단일 Cloud Run 서비스 `api` (FastAPI + MCP 마운트)
- **프론트엔드**: 별도 레포 `proj2-frontend` → Vercel 연동 (Hobby 플랜 무료)
- **DB**: **Neon 무료 PostgreSQL** (Cloud SQL 대신 — 월 $0)
- **시크릿**: Secret Manager
- **CI/CD**: Cloud Build (GitHub push → 빌드 → 배포)
- **예상 월 비용**: **$0** (무료 할당량 내, 초과 시 과금 가능)

---

## 1. 사전 준비

```bash
# GCP 프로젝트 설정 (기존 프로젝트 사용)
gcloud config set project proj2-509406
gcloud auth login
gcloud auth application-default login

# 필요 API 활성화 (Cloud SQL, VPC Access 불필요)
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com
```

---

## 2. Neon 무료 PostgreSQL 생성 (필수)

1. **Neon 가입**: https://neon.tech → GitHub/GitHub으로 로그인
2. **프로젝트 생성**: 프로젝트명 `proj2-4`, 리전 `Asia Pacific (Seoul)` 권장
3. **연결 문자열 복사**: Dashboard → Connection Details → `psql` 탭
   - 형식: `postgresql://user:password@ep-xxx.ap-northeast-1.aws.neon.tech/dbname?sslmode=require`
   - **asyncpg용 변환**: `postgresql+asyncpg://user:password@ep-xxx.ap-northeast-1.aws.neon.tech/dbname?sslmode=require`
4. 이 문자열을 **Secret Manager `DATABASE_URL`에 저장**

> Neon 무료 티어: 0.5GB 스토리지, 5분 유휴 시 자동 일시정지(비용 0), 브랜칭 기능 포함

---

## 3. 인프라 생성 (한 번만 실행)

```bash
# 무료 티어 설정 스크립트 실행
bash scripts/gcp-setup-free.sh
```

스크립트가 생성하는 리소스:
- Artifact Registry: `asia-northeast3-docker.pkg.dev/proj2-509406/docker-repo`
- **Cloud SQL 없음, VPC 커넥터 없음** (비용 절감)
- Secret Manager: 5개 시크릿 생성 안내 (직접 값 입력 필요)

**수동 입력 필요 시크릿 5개** (Secret Manager 콘솔 또는 CLI):
1. `OPENROUTER_API_KEY` — OpenRouter 키
2. `LANGFUSE_PUBLIC_KEY` — Langfuse 공개 키
3. `LANGFUSE_SECRET_KEY` — Langfuse 비밀 키
4. `SESSION_SECRET` — 임의 32자 문자열 (`openssl rand -base64 32 | tr -d "=+/" | cut -c1-32`)
5. `DATABASE_URL` — **Neon 연결 문자열** (`postgresql+asyncpg://...`)

CLI로 한 번에 입력 예시:
```bash
gcloud secrets create OPENROUTER_API_KEY --data-file=- --project=proj2-509406 <<< 'sk-or-xxx'
gcloud secrets create LANGFUSE_PUBLIC_KEY --data-file=- --project=proj2-509406 <<< 'pk-lf-xxx'
gcloud secrets create LANGFUSE_SECRET_KEY --data-file=- --project=proj2-509406 <<< 'sk-lf-xxx'
gcloud secrets create SESSION_SECRET --data-file=- --project=proj2-509406 <<< 'your-32-char-secret'
gcloud secrets create DATABASE_URL --data-file=- --project=proj2-509406 <<< 'postgresql+asyncpg://user:pwd@ep-xxx.neon.tech/db?sslmode=require'
```

---

## 4. Cloud Build 트리거 생성

1. Cloud Build 콘솔 → **트리거** → **저장소 연결**
2. GitHub `aihuman-7th/proj2-4` 선택
3. 트리거 설정:
   - **이름**: `deploy-api`
   - **이벤트**: 브랜치 푸시
   - **브랜치 정규식**: `^main$`
   - **포함된 파일 필터**: `backend/**`
   - **빌드 구성**: `cloudbuild.yaml` (레포 루트)
4. **만들기** 클릭

이제 `main` 브랜치에 `backend/` 변경사항을 푸시하면 자동 빌드·배포 실행.

---

## 5. 로컬 개발

```bash
# .env 파일 생성 (예시)
cp .env.example .env
# .env 편집: OPENROUTER_API_KEY, LANGFUSE_* 등 입력
# DATABASE_URL에는 Neon dev 브랜치 연결 문자열 사용 (운영과 동일 환경)

# 전체 스택 실행 (Neon dev 브랜치 사용)
docker compose up --build

# API 확인
curl http://localhost:8000/health
curl http://localhost:8000/mcp/health
```

- FastAPI: `http://localhost:8000`
- MCP 엔드포인트: `http://localhost:8000/mcp` (Streamable HTTP, `MCP_ENABLED=true` 시에만)
- 로컬 DB: **Neon dev 브랜치** 사용 (운영과 동일 환경, 브랜칭 기능 활용)

---

## 6. 프론트엔드 배포 (Vercel 무료)

### 별도 레포 생성 권장
```bash
gh repo create proj2-frontend --public --clone
cd proj2-frontend
npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
```

### Vercel 연결 (가이드)
1. Vercel 대시보드 → **Add New Project** → GitHub `proj2-frontend` 선택
2. 환경변수 추가:
   - `NEXT_PUBLIC_API_URL` = `https://api-xxx-asia-northeast3.run.app` (Cloud Run URL)
3. 배포 완료 → `https://proj2-frontend.vercel.app` 생성됨 (Hobby 플랜 무료)

> **참고**: 이 문서는 연동 가이드입니다. 실제 프론트엔드 레포(`proj2-frontend`) 생성 및 배포는 별도 진행 필요.

### CORS 허용 (Cloud Run 측)
```bash
gcloud run services update api \
  --region=asia-northeast3 \
  --update-env-vars=ALLOWED_ORIGINS=https://proj2-frontend.vercel.app \
  --project=proj2-509406
```
또는 `cloudbuild.yaml`의 `--set-env-vars`에 추가 후 재배포.

---

## 7. 커스텀 도메인 (선택)

| 서비스 | 명령어 |
|---|---|
| Cloud Run | `gcloud run domain-mappings create --service=api --domain=api.myapp.com --region=asia-northeast3` |
| Vercel | 대시보드 → Project → Settings → Domains → Add |

---

## 8. 주요 명령어 치트시트

```bash
# Cloud Run 로그 확인
gcloud run services logs read api --region=asia-northeast3 --limit=50

# Cloud Run 서비스 업데이트 (환경변수만 변경 시)
gcloud run services update api --region=asia-northeast3 --update-env-vars=KEY=VALUE --project=proj2-509406

# Secret Manager 시크릿 업데이트
echo -n "new-value" | gcloud secrets versions add SECRET_NAME --data-file=- --project=proj2-509406

# Neon 콘솔에서 DB 상태 확인: https://console.neon.tech
```

---

## 9. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| 배포 후 500 에러 | 시크릿 누락 | Secret Manager에 5개 시크릿 모두 버전 확인 |
| DB 연결 실패 | Neon 일시정지 | Neon 콘솔에서 프로젝트 'Resume' 클릭 또는 연결 문자열 재확인 |
| CORS 에러 | ALLOWED_ORIGINS 불일치 | Vercel 도메인 정확히 추가 (프로토콜 `https://` 포함) |
| MCP 엔드포인트 404 | 마운트 경로 틀림 또는 비활성화 | `/mcp` 경로 확인, `MCP_ENABLED=true` 환경변수 설정 필요 (기본값 false) |
| 빌드 실패 | requirements.txt 의존성 | 로컬에서 `docker compose build`로 선검증 |
| Neon SSL 에러 | `sslmode=require` 누락 | 연결 문자열에 `?sslmode=require` 필수 |

---

## 10. 무료 티어 한계 및 대비

| 리소스 | 무료 한계 | 초과 시 |
|---|---|---|
| Cloud Run | 월 200만 요청, 360만 vCPU-초, 180만 GiB-초 | 과금 ($0.000024/vCPU-초) |
| Neon | 0.5GB 스토리지, 1프로젝트 | 유료 플랜($19/월~) 또는 Supabase 무료(500MB) 이전 |
| Cloud Build | 월 120 빌드분 | 초과분 과금 |
| Artifact Registry | 0.5GB 스토리지 무료 | GB당 $0.10/월 |
| Vercel Hobby | 100GB 대역폭, 무제한 개인 프로젝트 | Pro 플랜($20/월) |

**팁**: Neon 대신 **Supabase 무료(500MB, PostgreSQL + Auth + Realtime)**도 대안. 연결 문자열만 바꾸면 됨.