#!/usr/bin/env bash
# GCP 완전 무료 설정 스크립트 (Neon PostgreSQL + Cloud Run)
# 실행 전: gcloud auth login, gcloud config set project <PROJECT_ID>, billing 활성화 필수
# Neon: https://neon.tech 에서 프로젝트 생성 후 연결 문자열 준비

set -euo pipefail

PROJECT_ID="proj2-509406"
REGION="asia-northeast3"
SERVICE_NAME="api"
ARTIFACT_REPO="docker-repo"

echo "=== 1. 필요 API 활성화 (무료 티어용) ==="
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  --project="${PROJECT_ID}"

echo "=== 2. Artifact Registry 리포지토리 생성 ==="
gcloud artifacts repositories create "${ARTIFACT_REPO}" \
  --repository-format=DOCKER \
  --location="${REGION}" \
  --description="Docker images for proj2-4" \
  --project="${PROJECT_ID}" || echo "이미 존재함"

echo "=== 3. Secret Manager에 시크릿 생성 ==="
# 시크릿 생성 함수
create_secret() {
  local name=$1
  local value=$2
  echo -n "${value}" | gcloud secrets create "${name}" --data-file=- --project="${PROJECT_ID}" 2>/dev/null \
    || echo -n "${value}" | gcloud secrets versions add "${name}" --data-file=- --project="${PROJECT_ID}"
}

# DATABASE_URL은 Neon 연결 문자열로 별도 입력 필요 (아래 안내 참조)
# create_secret "DATABASE_URL" "postgresql+asyncpg://user:pass@ep-xxx.ap-northeast-1.aws.neon.tech/db?sslmode=require"

echo ">>> 다음 시크릿 값들을 직접 입력하세요 (Secret Manager 콘솔 또는 아래 gcloud 명령어):"
echo "1. OPENROUTER_API_KEY:"
echo "   gcloud secrets create OPENROUTER_API_KEY --data-file=- --project=${PROJECT_ID} <<< 'your-openrouter-key'"
echo ""
echo "2. LANGFUSE_PUBLIC_KEY:"
echo "   gcloud secrets create LANGFUSE_PUBLIC_KEY --data-file=- --project=${PROJECT_ID} <<< 'your-langfuse-public-key'"
echo ""
echo "3. LANGFUSE_SECRET_KEY:"
echo "   gcloud secrets create LANGFUSE_SECRET_KEY --data-file=- --project=${PROJECT_ID} <<< 'your-langfuse-secret-key'"
echo ""
echo "4. SESSION_SECRET (임의 32자):"
echo "   gcloud secrets create SESSION_SECRET --data-file=- --project=${PROJECT_ID} <<< '\$(openssl rand -base64 32 | tr -d \"=+/\" | cut -c1-32)'"
echo ""
echo "5. DATABASE_URL (Neon PostgreSQL, 필수):"
echo "   Neon 콘솔(https://console.neon.tech) > 프로젝트 선택 > Connection Details > psql 탭"
echo "   형식: postgresql+asyncpg://user:password@ep-xxx.ap-northeast-1.aws.neon.tech/dbname?sslmode=require"
echo "   gcloud secrets create DATABASE_URL --data-file=- --project=${PROJECT_ID} <<< 'postgresql+asyncpg://...'"
echo ""

echo "=== 4. Cloud Run 서비스 최초 배포 (수동) ==="
echo "첫 배포는 Cloud Build 트리거가 수행합니다."
echo "수동 배포 시:"
echo "gcloud run deploy ${SERVICE_NAME} \\"
echo "  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${SERVICE_NAME}:latest \\"
echo "  --region=${REGION} --platform=managed --allow-unauthenticated \\"
echo "  --port=8000 --cpu=1 --memory=512Mi --min-instances=0 --max-instances=3 \\"
echo "  --set-env-vars=ENVIRONMENT=production \\"
echo "  --set-secrets=OPENROUTER_API_KEY=OPENROUTER_API_KEY:latest \\"
echo "  --set-secrets=LANGFUSE_PUBLIC_KEY=LANGFUSE_PUBLIC_KEY:latest \\"
echo "  --set-secrets=LANGFUSE_SECRET_KEY=LANGFUSE_SECRET_KEY:latest \\"
echo "  --set-secrets=DATABASE_URL=DATABASE_URL:latest \\"
echo "  --set-secrets=SESSION_SECRET=SESSION_SECRET:latest"

echo ""
echo "=== 5. Cloud Build 트리거 생성 (GitHub 연결 필요) ==="
echo "콘솔에서 수동 생성: Cloud Build > 트리거 > 저장소 연결 (aihuman-7th/proj2-4)"
echo "설정:"
echo "  - 이름: deploy-api"
echo "  - 이벤트: 브랜치 푸시"
echo "  - 브랜치: ^main\$"
echo "  - 포함된 파일 필터: backend/**"
echo "  - 빌드 구성: cloudbuild.yaml (레포 루트)"

echo ""
echo "=== 무료 티어 아키텍처 (Neon PostgreSQL + Cloud Run) ==="
echo "┌─────────────┐     HTTPS      ┌──────────────────┐"
echo "│   Vercel    │ ─────────────► │  Cloud Run (api) │  --min-instances=0 (유휴 시 \$0)"
echo "│  (Frontend) │   REST + MCP   │  FastAPI + MCP   │  --max-instances=3"
echo "└─────────────┘                └────────┬─────────┘"
echo "                                        │ Public Internet + SSL"
echo "                                        ▼"
echo "                               ┌──────────────────┐"
echo "                               │  Neon PostgreSQL │  -- Free Tier: 0.5GB storage"
echo "                               │  (Free Tier)     │  -- Auto-suspend 5min 유휴"
echo "                               └──────────────────┘"
echo ""
echo "✅ Neon 무료 티어: 0.5GB 스토리지, 5분 유휴 시 자동 일시정지(비용 0), 브랜칭 기능 포함"
echo "✅ 로컬 개발도 Neon dev branch 사용 권장 (운영과 동일 환경)"
echo ""
echo "예상 월 비용: \$0 (Cloud Run/Neon 무료 할당량 내, 초과 시 과금 가능)"
echo ""
echo "다음 단계:"
echo "1. 위 5개 시크릿 값 모두 입력 (DATABASE_URL 필수)"
echo "2. GitHub 저장소를 Cloud Build에 연결하고 트리거 생성"
echo "3. main 브랜치에 push하면 자동 빌드·배포 시작"
echo "4. 앱 코드는 DATABASE_URL을 postgresql+asyncpg://...로 사용 (SQLite 사용 안 함)"