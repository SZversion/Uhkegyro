"""Approved illustration-reference terms used by deterministic validation."""

from dataclasses import dataclass
from typing import Literal

Axis = Literal["body", "pose", "composition"]
Role = Literal["body", "pose", "view", "perspective", "layout"]
CompositionKind = Literal["view", "perspective", "layout"]


@dataclass(frozen=True)
class TermCard:
    term_id: str
    axis: Axis
    role: Role
    label: str
    query_fragment: str
    look_for: str
    kind: CompositionKind | None = None


TERM_CARDS: dict[str, TermCard] = {
    "body_hourglass": TermCard(
        term_id="body_hourglass",
        axis="body",
        role="body",
        label="모래시계형",
        query_fragment="hourglass body silhouette",
        look_for="어깨와 골반의 폭, 허리의 굴곡",
    ),
    "body_inverted_triangle": TermCard(
        term_id="body_inverted_triangle",
        axis="body",
        role="body",
        label="역삼각형 실루엣",
        query_fragment="inverted triangle body silhouette",
        look_for="어깨와 골반의 폭, 상체에서 하체로 좁아지는 윤곽",
    ),
    "body_triangle": TermCard(
        term_id="body_triangle",
        axis="body",
        role="body",
        label="삼각형 실루엣",
        query_fragment="triangle body silhouette",
        look_for="골반과 하체의 폭, 상체와의 비율",
    ),
    "body_slim": TermCard(
        term_id="body_slim",
        axis="body",
        role="body",
        label="슬림 비율",
        query_fragment="slim body proportion",
        look_for="전체 체적과 팔다리의 길이·두께",
    ),
    "body_childlike": TermCard(
        term_id="body_childlike",
        axis="body",
        role="body",
        label="유아형 비율",
        query_fragment="childlike body proportion",
        look_for="머리 대비 몸의 크기와 팔다리 길이",
    ),
    "pose_contrapposto": TermCard(
        term_id="pose_contrapposto",
        axis="pose",
        role="pose",
        label="콘트라포스토",
        query_fragment="contrapposto standing pose",
        look_for="지지 다리와 반대 방향의 어깨·골반 기울기",
    ),
    "pose_weight_shift": TermCard(
        term_id="pose_weight_shift",
        axis="pose",
        role="pose",
        label="체중 이동 스탠딩",
        query_fragment="weight shift standing pose",
        look_for="한쪽으로 이동한 무게중심과 지지 다리",
    ),
    "pose_s_curve": TermCard(
        term_id="pose_s_curve",
        axis="pose",
        role="pose",
        label="S자 흐름",
        query_fragment="s curve standing pose",
        look_for="몸통에서 이어지는 부드러운 S자 흐름",
    ),
    "pose_standing": TermCard(
        term_id="pose_standing",
        axis="pose",
        role="pose",
        label="스탠딩",
        query_fragment="standing character pose",
        look_for="발 간격과 체중 분배",
    ),
    "pose_sitting": TermCard(
        term_id="pose_sitting",
        axis="pose",
        role="pose",
        label="시팅",
        query_fragment="sitting character pose",
        look_for="앉은 면, 골반 접힘, 허벅지 방향",
    ),
    "pose_gesture": TermCard(
        term_id="pose_gesture",
        axis="pose",
        role="pose",
        label="제스처/액션 라인",
        query_fragment="gesture drawing action line",
        look_for="동세와 몸 전체를 잇는 힘의 흐름",
    ),
    "pose_reclining": TermCard(
        term_id="pose_reclining",
        axis="pose",
        role="pose",
        label="리클라이닝",
        query_fragment="reclining character pose",
        look_for="기대는 면과 몸통 기울기",
    ),
    "view_front": TermCard(
        term_id="view_front",
        axis="composition",
        role="view",
        kind="view",
        label="프론트 뷰",
        query_fragment="front view character",
        look_for="얼굴과 몸통의 정면 축",
    ),
    "view_three_quarter": TermCard(
        term_id="view_three_quarter",
        axis="composition",
        role="view",
        kind="view",
        label="3/4뷰",
        query_fragment="three quarter view character",
        look_for="정면과 측면 사이의 면적 차이",
    ),
    "view_high_angle": TermCard(
        term_id="view_high_angle",
        axis="composition",
        role="view",
        kind="view",
        label="하이 앵글",
        query_fragment="high angle character view",
        look_for="위에서 아래로 향하는 시선 높이",
    ),
    "view_low_angle": TermCard(
        term_id="view_low_angle",
        axis="composition",
        role="view",
        kind="view",
        label="로우 앵글",
        query_fragment="low angle character view",
        look_for="아래에서 위로 향하는 시선 높이",
    ),
    "perspective_three_point": TermCard(
        term_id="perspective_three_point",
        axis="composition",
        role="perspective",
        kind="perspective",
        label="3점 투시",
        query_fragment="three point perspective background",
        look_for="수직선까지 향하는 소실점과 공간감",
    ),
    "perspective_foreshortening": TermCard(
        term_id="perspective_foreshortening",
        axis="composition",
        role="perspective",
        kind="perspective",
        label="과투시/단축법",
        query_fragment="foreshortening character pose",
        look_for="가까운 부위의 확대와 먼 부위의 축소",
    ),
    "perspective_vanishing_point": TermCard(
        term_id="perspective_vanishing_point",
        axis="composition",
        role="perspective",
        kind="perspective",
        label="소실점",
        query_fragment="vanishing point background perspective",
        look_for="평행선이 모이는 지점",
    ),
    "composition_rule_of_thirds": TermCard(
        term_id="composition_rule_of_thirds",
        axis="composition",
        role="layout",
        kind="layout",
        label="삼분할 구도",
        query_fragment="rule of thirds character composition",
        look_for="삼등분선과 교차점 부근의 배치",
    ),
}
