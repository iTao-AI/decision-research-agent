from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parents[2]
APPROVED_LINES = (
    "ragflow-sdk 0.13.0 has requirement pytest<9.0.0,>=8.0.0, but you have pytest 9.0.3.",
    "ragflow-sdk 0.13.0 has requirement pytest>=8.0.0,<9.0.0, but you have pytest 9.0.3.",
)


def test_lock_closes_sqlalchemy_greenlet_runtime_dependency():
    constraints = (PROJECT_ROOT / "constraints.txt").read_text(encoding="utf-8")

    assert "greenlet==3.5.4" in constraints.splitlines()


def test_clean_pip_check_is_accepted():
    from scripts.check_dependency_compatibility import parse_pip_check

    assert parse_pip_check("No broken requirements found.\n", "", 0) == ("clean",)


@pytest.mark.parametrize("diagnostic", APPROVED_LINES)
def test_exact_ragflow_pytest_diagnostic_is_accepted(diagnostic):
    from scripts.check_dependency_compatibility import parse_pip_check

    assert parse_pip_check(diagnostic + "\n", "", 1) == (
        "approved_diagnostic",
        "ragflow-sdk",
        "0.13.0",
        "pytest",
        "9.0.3",
    )


@pytest.mark.parametrize(
    ("stdout", "stderr", "returncode"),
    [
        (APPROVED_LINES[0] + "\nsecond diagnostic\n", "", 1),
        ("ragflow-sdk 0.13.1 has requirement pytest<9, but you have pytest 9.0.3.\n", "", 1),
        ("ragflow-sdk 0.13.0 requires missing-package, which is not installed.\n", "", 1),
        (APPROVED_LINES[0] + "\n", "warning", 1),
        (APPROVED_LINES[0].replace("pytest 9.0.3", "pytest 9.0.30") + "\n", "", 1),
        ("", "", 0),
        ("No broken requirements found.\n", "", 1),
        ("No broken requirements found.\n", "", 2),
    ],
)
def test_every_non_approved_pip_check_shape_fails_closed(stdout, stderr, returncode):
    from scripts.check_dependency_compatibility import DependencyCompatibilityError, parse_pip_check

    with pytest.raises(DependencyCompatibilityError):
        parse_pip_check(stdout, stderr, returncode)


def test_invalid_utf8_at_subprocess_boundary_fails_closed():
    from scripts.check_dependency_compatibility import DependencyCompatibilityError, decode_output

    with pytest.raises(DependencyCompatibilityError):
        decode_output(b"\xff")
