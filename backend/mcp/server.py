"""MCP 서버: FastMCP(v1.x) 기반 도구 노출.
FastAPI 앱에 마운트되어 `/mcp` 경로로 서비스됨.
"""
import json
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP
from backend.shared.config import get_settings, resolve_term_cards_dir

settings = get_settings()

# TERM_CARD 카탈로그 경로 (환경변수/Docker/로컬 자동 해결)
CATALOG_DIR = resolve_term_cards_dir(settings)

# 전역 카탈로그 상태
_catalog: dict[str, Any] = {}
_catalog_valid = False


def load_catalog() -> None:
    """TERM_CARD 카탈로그 로드 및 검증 (시작 시 1회 실행).
    
    검증 실패 시 RuntimeError 발생 → MCP 서비스 시작 실패 (fail-closed)
    """
    global _catalog, _catalog_valid

    # index.json 로드
    index_path = CATALOG_DIR / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"index.json not found at {index_path}")

    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)

    # 역할별 JSON 파일 로드
    categories = index_data.get("categories", [])
    active_cards: dict[str, dict] = {}

    for cat in categories:
        role = cat["role"]
        file_name = cat["file"]
        file_path = CATALOG_DIR / file_name

        if not file_path.exists():
            raise FileNotFoundError(f"Role file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            role_data = json.load(f)

        # 활성 카드만 필터링
        for card in role_data.get("cards", []):
            if card.get("runtime_eligible", False) and card.get("mvp_status") == "active_in_current_contract":
                term_id = card["term_id"]
                if term_id in active_cards:
                    raise ValueError(f"Duplicate term_id: {term_id}")
                active_cards[term_id] = card

    # 카탈로그 검증: 필수 필드 확인
    required_fields = [
        "term_id", "role", "label_ko", "label_en",
        "query_fragments", "look_for", "confidence_gate",
        "requires_all_of", "requires_any_of",
        "runtime_eligible", "mvp_status"
    ]

    for term_id, card in active_cards.items():
        for field in required_fields:
            if field not in card:
                raise ValueError(f"Missing required field '{field}' in term_id={term_id}")

        if not card.get("query_fragments"):
            raise ValueError(f"Empty query_fragments in term_id={term_id}")

        if not card.get("source_answer_draft") or not card.get("look_for"):
            raise ValueError(f"Missing source_answer_draft or look_for in term_id={term_id}")

    # 피드백 검증
    feedback = index_data.get("active_term_feedback", {})
    for term_id, fb in feedback.items():
        if term_id not in active_cards:
            raise ValueError(f"Feedback term_id not in active cards: {term_id}")
        for fb_field in ["plain_meaning_ko", "selection_reason_template_ko", "reference_checkpoints_ko"]:
            if not fb.get(fb_field):
                raise ValueError(f"Missing feedback field '{fb_field}' for term_id={term_id}")

    _catalog = {
        "dataset_version": index_data.get("dataset_version", "unknown"),
        "active_cards": active_cards,
        "feedback": feedback,
    }
    _catalog_valid = True


# 시작 시 카탈로그 로드 (실패 시 예외 전파 → 프로세스 크래시)
load_catalog()


mcp = FastMCP("illustration-reference-mcp")


@mcp.tool()
async def get_active_term_card(term_id: str) -> dict:
    """Pydantic 검증 뒤의 활성 term ID에 대한 팀 검수 설명·검색 조각이 필요할 때 사용한다.

    Args:
        term_id: 활성 TERM_CARD ID (예: pose_contrapposto)

    Returns:
        found: 활성 카드 정보 / not_found: TERM_NOT_ACTIVE
    """
    # 카탈로그 검증 실패 시 (이론상 도달 불가 - 시작 시 크래시)
    if not _catalog_valid:
        return {
            "status": "not_found",
            "reason_code": "CATALOG_INVALID_AT_STARTUP",
            "message": "TERM_CARD catalog failed validation at startup"
        }

    active_cards = _catalog.get("active_cards", {})

    # 활성 카드 조회
    card = active_cards.get(term_id)
    if not card:
        return {
            "status": "not_found",
            "reason_code": "TERM_NOT_ACTIVE"
        }

    # 성공 응답: 문서 계약에 따른 found 구조
    return {
        "status": "found",
        "catalog_version": _catalog.get("dataset_version", "unknown"),
        "term": {
            "term_id": card["term_id"],
            "role": card["role"],
            "label_ko": card["label_ko"],
            "label_en": card["label_en"],
            "query_fragments": card["query_fragments"],
            "look_for": card["look_for"],
        }
    }


def create_mcp_app():
    """FastMCP를 FastAPI 앱에 마운트하여 반환."""
    from fastapi import FastAPI

    mcp_app = FastAPI(title="MCP Server")

    @mcp_app.get("/health")
    def health() -> dict:
        return {
            "status": "ok" if _catalog_valid else "error",
            "service": "mcp",
            "catalog_valid": _catalog_valid,
            "active_cards_count": len(_catalog.get("active_cards", {})) if _catalog_valid else 0,
        }

    mcp_app.mount("/", mcp.streamable_http_app())
    return mcp_app


app = create_mcp_app()