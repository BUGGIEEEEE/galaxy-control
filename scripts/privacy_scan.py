#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///

"""Scan release files and Git patches for common private Galaxy artifacts."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

MAX_FILE_BYTES: Final = 2_097_152
MAX_HISTORY_BYTES: Final = 33_554_432
RULES: Final = (
    ("absolute_macos_home", re.compile(r"/" r"Users/[^/\s]+")),
    (
        "literal_pairing_code",
        re.compile(
            r"pair(?:ing)?[_ -]?code[^\n:=]{0,20}[:=]\s*[\"']?[0-9]{6}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "literal_bridge_token",
        re.compile(r"OPENMINIS_BRIDGE_TOKEN\s*=\s*[\"']?[0-9a-f]{64}\b"),
    ),
)


@dataclass(frozen=True, slots=True)
class ScanFinding:
    """One redacted privacy finding."""

    path: str
    line: int
    rule: str


@dataclass(frozen=True, slots=True)
class PrivacyScanError(Exception):
    """Git-backed privacy scan failure."""

    message: str

    def __str__(self) -> str:
        return self.message


def _scan_text(text: str, label: str) -> tuple[ScanFinding, ...]:
    findings: list[ScanFinding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in RULES:
            if pattern.search(line) is not None:
                findings.append(ScanFinding(label, line_number, rule))
    return tuple(findings)


def scan_files(paths: tuple[Path, ...]) -> tuple[ScanFinding, ...]:
    """Scan bounded regular text files without returning matched private content."""
    findings: list[ScanFinding] = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            findings.append(ScanFinding(str(path), 0, "untrusted_file"))
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            findings.append(ScanFinding(str(path), 0, "file_too_large"))
            continue
        try:
            content = path.read_text(errors="strict")
        except UnicodeDecodeError:
            continue
        findings.extend(_scan_text(content, str(path)))
    return tuple(findings)


def _git(repository: Path, argv: tuple[str, ...]) -> bytes:
    completed = subprocess.run(
        ("/usr/bin/git", "-C", str(repository), *argv),
        capture_output=True,
        check=False,
        shell=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise PrivacyScanError("git privacy scan command failed")
    return completed.stdout


def tracked_files(repository: Path) -> tuple[Path, ...]:
    """Return exact Git-tracked paths."""
    raw = _git(repository, ("ls-files", "-z"))
    return tuple(repository / item.decode() for item in raw.split(b"\0") if item)


def scan_history(repository: Path) -> tuple[ScanFinding, ...]:
    """Scan all bounded Git patches, including deleted private content."""
    raw = _git(repository, ("log", "--all", "--format=commit:%H", "--patch", "--no-ext-diff"))
    if len(raw) > MAX_HISTORY_BYTES:
        return (ScanFinding("git-history", 0, "history_too_large"),)
    return _scan_text(raw.decode(errors="replace"), "git-history")


def main(argv: tuple[str, ...] | None = None) -> int:
    """Scan the current repository and print one non-sensitive JSON envelope."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    if args not in {(), ("--history",)}:
        findings = (ScanFinding("arguments", 0, "invalid_request"),)
    else:
        repository = Path(__file__).resolve().parent.parent
        findings = scan_files(tracked_files(repository))
        if args == ("--history",):
            findings += scan_history(repository)
    envelope = {
        "ok": not findings,
        "action": "privacy_scan",
        "result": {
            "history_scanned": args == ("--history",),
            "finding_count": len(findings),
            "findings": [asdict(finding) for finding in findings],
            "matched_content_redacted": True,
        },
    }
    _ = sys.stdout.write(json.dumps(envelope, separators=(",", ":")) + "\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
