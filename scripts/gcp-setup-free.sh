#!/usr/bin/env bash
# GCP 완전 무료 설정 스크립트 (Option C: Cloud Run + SQLite)
# 실행 전: gcloud auth login, gcloud config set project <PROJECT_ID>, billing 활성화 필수
# 주의: SQLite 파일은 컨테이너 인스턴스 내에 저장되며, 새 리비전 배포 시 초기화됩니다.
# 영속성이 필요하면 Option A(Neon) 또는 Option B(db-f1-micro) 사용 권장.

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

# SQLite용 DATABASE_URL (컨테이너 내부 경로)
DATABASE_URL="sqlite+aiosqlite:///data/app.db"

create_secret "DATABASE_URL" "${DATABASE_URL}"

echo ">>> 다음 시크릿 값들을 직접 입력하세요 (Secret Manager 콘솔 또는 아래 명령어):"
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
echo "   gcloud secrets create SESSION_SECRET --data-file=- --project=${PROJECT_ID} <<< '$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)'"
echo ""
echo "5. DATABASE_URL (SQLite, 자동 설정됨):"
echo "   이미 저장됨: ${DATABASE_URL}"
echo "   컨테이너 내부 /data/app.db에 저장 (인스턴스 재시작 시 유지, 새 배포 시 초기화)"

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
echo "=== 무료 티어 아키텍처 (Option C: SQLite) ==="
echo "┌─────────────┐     HTTPS      ┌──────────────────┐"
echo "│   Vercel    │ ─────────────► │  Cloud Run (api) │  --min-instances=0 (유휴 시 \$0)"
echo "│  (Frontend) │   REST + MCP   │  FastAPI + MCP   │  --max-instances=3"
echo "└─────────────┘                └────────┬─────────┘"
echo "                                        │"
echo "                                        ▼"
echo "                               ┌──────────────────┐"
echo "                               │  SQLite (/data)  │  -- 컨테이너 로컬 파일"
echo "                               │  (임시 저장소)   │  -- 새 배포 시 데이터 초기화"
echo "                               └──────────────────┘"
echo ""
echo "⚠️  주의: SQLite 데이터는 컨테이너 인스턴스 수명 주기에 종속됩니다."
echo "   - 인스턴스 재시작(자동 스케일링) 시 유지"
echo "   - 새 리비전 배포(gcloud run deploy) 시 초기화"
echo "   - 영속성 필요 시 Option A(Neon) 또는 Option B(db-f1-micro) 사용"
echo ""
echo "예상 월 비용: \$0 (Cloud Run 무료 할당량 내)"
echo ""
echo "다음 단계:"
echo "1. 위 4개 시크릿 값 입력 (DATABASE_URL은 자동 설정됨)"
echo "2. GitHub 저장소를 Cloud Build에 연결하고 트리거 생성"
echo "3. main 브랜치에 push하면 자동 빌드·배포 시작"
echo "4. 앱 코드에서 DATABASE_URL을 sqlite+aiosqlite:///data/app.db로 사용하도록 설정 필요"