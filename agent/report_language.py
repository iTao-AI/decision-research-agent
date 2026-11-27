"""Run-scoped report language for the two interactive research profiles."""
from typing import Literal, Mapping


ReportLanguage = Literal["zh-CN", "en"]


def validate_report_language(value: object) -> ReportLanguage:
    if value == "zh-CN":
        return "zh-CN"
    if value == "en":
        return "en"
    raise ValueError("invalid_report_language")


def run_report_language(profile_id: str, scope: Mapping[str, object]) -> ReportLanguage | None:
    if profile_id in {"generic", "generic-evidence-report"} and "report_language" in scope:
        return validate_report_language(scope["report_language"])
    return None


def report_language_instruction(language: ReportLanguage) -> str:
    selected = "Simplified Chinese (zh-CN)" if language == "zh-CN" else "English (en)"
    return (
        f"Server-owned report language: {selected}. Use it for authored report text, including "
        "the title, conclusions, applicability conditions, unresolved reasons, contradictions, "
        "and limitations. Preserve original source quotations verbatim in their source language. "
        "Keep identifiers, commands, versions, source URLs, and file names unchanged."
    )
