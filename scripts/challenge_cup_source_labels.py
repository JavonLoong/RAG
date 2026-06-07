from __future__ import annotations

import re


RISKY_SOURCE_LABEL_FRAGMENT = (
    r"z[\s_-]*library|z[\s_-]*lib|1lib|libgen|sci[\s_-]*hub|"
    r"anna'?s[\s_-]*archive|annas[\s_-]*archive|盗版|pirat"
)
FORBIDDEN_VISIBLE_SOURCE_LABEL_RE = re.compile(RISKY_SOURCE_LABEL_FRAGMENT, re.IGNORECASE)
RISKY_SOURCE_PAREN_RE = re.compile(
    rf"\s*[\(\[][^)\]]*(?:{RISKY_SOURCE_LABEL_FRAGMENT})[^)\]]*[\)\]]",
    re.IGNORECASE,
)
RISKY_SOURCE_TOKEN_RE = re.compile(
    rf"(?:{RISKY_SOURCE_LABEL_FRAGMENT})[^\s,;)\]]*",
    re.IGNORECASE,
)


def sanitize_visible_source_label(value: str) -> str:
    sanitized = RISKY_SOURCE_PAREN_RE.sub("", value)
    sanitized = RISKY_SOURCE_TOKEN_RE.sub("source-label-redacted", sanitized)
    sanitized = re.sub(r"\s{2,}", " ", sanitized)
    sanitized = re.sub(r"\s+(\.[A-Za-z0-9]+)$", r"\1", sanitized)
    return sanitized.strip()
