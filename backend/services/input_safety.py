"""Deterministic, side-effect-free input safety gate."""

from __future__ import annotations

import re
import unicodedata


_SPACE = re.compile(r"\s+")
_KOREAN_OVERRIDE = re.compile(
    r"(?:이전|앞선|앞의|위|상기|기존|시스템|개발자).{0,24}"
    r"(?:지시|명령|규칙|안내|정책|프롬프트|제한).{0,24}"
    r"(?:무시|잊어|덮어|따르지\s*말|바꿔|변경|해제|제거|건너뛰)"
)
_ENGLISH_OVERRIDE = re.compile(
    r"(?:ignore|disregard|override|bypass|forget).{0,48}"
    r"(?:previous|prior|above|earlier|system|developer).{0,24}"
    r"(?:instruction|prompt|rule|guidance|policy)|"
    r"(?:do\s+not|don't)\s+(?:follow|obey).{0,48}"
    r"(?:previous|prior|above|earlier|system|developer).{0,24}"
    r"(?:instruction|prompt|rule|guidance|policy)"
)
_SENSITIVE_TARGET = re.compile(
    r"system\s*(?:prompt|message)|developer\s*(?:message|instruction)|"
    r"시스템\s*(?:프롬프트|지시)|개발자\s*(?:메시지|지시)|"
    r"api\s*(?:key|키)|secret|비밀(?:값|키)?|password|암호|token|토큰|credential|"
    r"(?:다른|타인의|other)\s*(?:사용자|user).{0,16}(?:검색\s*기록|history|session|data)"
)
_DISCLOSURE = re.compile(
    r"보여\s*줘|알려\s*줘|공개|출력|나열|제공|reveal|show|give|list|print|expose|return"
)
_LITERAL_SENSITIVE_REFERENCE = re.compile(
    r"(?:api\s*(?:key|키)|secret|비밀(?:값|키)?|password|암호|token|토큰|credential)"
    r".{0,12}(?:라는\s*)?(?:문구|글자)"
)
_HARMFUL_EXECUTION = re.compile(
    r"(?:폭발물|폭탄|사제\s*무기|악성\s*코드|랜섬웨어|피싱|계정\s*탈취|불법\s*침입|"
    r"bomb|explosives?|weapon|malware|ransomware|phishing|credential\s*theft|illegal\s*intrusion).{0,32}"
    r"(?:제작|만들|작성|실행|방법|절차|코드)|"
    r"(?:how\s+(?:to|do\s+i)|build|make|write|execute).{0,32}"
    r"(?:bomb|explosives?|weapon|malware|ransomware|phishing|credential\s*theft|illegal\s*intrusion)"
)


def normalize_input_text(request_text: str) -> str:
    """Normalize user text for deterministic safety and evidence checks."""
    normalized = unicodedata.normalize("NFKC", request_text).casefold()
    without_format_controls = "".join(
        char for char in normalized if unicodedata.category(char) != "Cf"
    )
    return _SPACE.sub(" ", without_format_controls).strip()


def _requests_sensitive_disclosure(text: str) -> bool:
    non_literal_text = _LITERAL_SENSITIVE_REFERENCE.sub("", text)
    return bool(_SENSITIVE_TARGET.search(non_literal_text) and _DISCLOSURE.search(text))


def is_unsafe_input(request_text: str) -> bool:
    """Return whether a request matches the deterministic unsafe-input policy."""
    text = normalize_input_text(request_text)
    return bool(
        _KOREAN_OVERRIDE.search(text)
        or _ENGLISH_OVERRIDE.search(text)
        or _requests_sensitive_disclosure(text)
        or _HARMFUL_EXECUTION.search(text)
    )
