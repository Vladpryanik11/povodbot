"""Fail closed on credential-shaped literals in tracked text files."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"(?i)\b(?:sk|ghp|xoxb|bot)_[A-Za-z0-9_-]{16,}\b"),
)
ALLOWLIST = {".env.example", "check_secrets.py"}


def tracked_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True, text=False)
    return [Path(item) for item in result.stdout.decode().split("\0") if item]


def run_secret_scan(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if path.name in ALLOWLIST or path.suffix.lower() in {".png", ".jpg", ".pdf"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            lowered = line.lower()
            if any(
                marker in lowered
                for marker in ("fake-", "dummy", "private-", "review-dummy", "test-secret")
            ):
                continue
            if any(pattern.search(line) for pattern in PATTERNS):
                findings.append(f"{path}:{line_number}")
    return findings


if __name__ == "__main__":
    findings = run_secret_scan(tracked_files())
    if findings:
        print("Potential credential-shaped literals:")
        print("\n".join(findings))
        raise SystemExit(1)
    print("Secret scan passed")
