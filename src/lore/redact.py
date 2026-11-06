"""Redação de segredos antes de envio remoto (spec §12.2).

recall > precisão: dúvida bloqueia o envio e pede decisão humana.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private-key", re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("generic-token", re.compile(
        r"(?i)\b(?:token|secret|api[_-]?key|bearer)\b\s*[:=]\s*\S{8,}")),
    ("password-assign", re.compile(
        r"(?i)\b(?:senha|password|passwd|pwd)\b\s*[:=]\s*\S+")),
    ("cookie", re.compile(
        r"(?i)\b(?:cookie|sessionid|sessão)\b\s*[:=]\s*\S+")),
    ("url-credentials", re.compile(
        r"[a-zA-Z][a-zA-Z0-9+.-]*://[^/\s:]+:[^/\s@]+@")),
    ("xox-slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
]


@dataclass
class RedactResult:
    text: str
    found: list[str]


def compile_extra(patterns: list[str]) -> list[tuple[str, re.Pattern]]:
    compiled = []
    for pos, raw in enumerate(patterns):
        try:
            compiled.append((f"extra-{pos}", re.compile(raw)))
        except re.error:
            continue
    return compiled


def scan(text: str, extra: list[str] | None = None) -> RedactResult:
    """Detecta segredos. Retorna texto redigido + tipos encontrados."""
    found: list[str] = []
    redacted = text
    for name, pattern in PATTERNS + compile_extra(extra or []):
        if pattern.search(redacted):
            found.append(name)
            redacted = pattern.sub("[REDIGIDO]", redacted)
    return RedactResult(text=redacted, found=sorted(set(found)))
