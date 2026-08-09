"""The harness pin must match the Home Assistant version the live box runs.

`requirements-dev.txt` pins pytest-homeassistant-custom-component, and the
comment on that line records which Home Assistant release the pin maps to.
`ha-version.txt` records what the box actually runs. When the two diverge the
suite is validating automations against a schema the box no longer has.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PIN_LINE = re.compile(
    r"^pytest-homeassistant-custom-component==(?P<pin>[\d.]+)"
    r"\s+#\s*→\s*HA\s+(?P<ha>[\d.]+)\s*$",
    re.MULTILINE,
)
BARE_VERSION = re.compile(r"\d{4}\.\d+\.\d+")


def _ha_version_file() -> str:
    return (REPO_ROOT / "ha-version.txt").read_text()


def test_ha_version_file_holds_a_bare_version():
    raw = _ha_version_file()
    assert raw.strip(), "ha-version.txt is empty"
    assert len(raw.strip().splitlines()) == 1, (
        "ha-version.txt holds one line and nothing else — no key, no comment"
    )
    assert BARE_VERSION.fullmatch(raw.strip()), (
        f"ha-version.txt must be a bare version like 2026.8.1, "
        f"got {raw.strip()!r}"
    )


def test_requirements_pin_line_is_parseable():
    text = (REPO_ROOT / "requirements-dev.txt").read_text()
    assert PIN_LINE.search(text), (
        "requirements-dev.txt needs a line of exactly this shape:\n"
        "  pytest-homeassistant-custom-component==<pin>  # → HA <version>\n"
        "The comment is parsed by this test; reformatting it disables the "
        "drift check."
    )


def test_pin_matches_the_live_ha_version():
    match = PIN_LINE.search((REPO_ROOT / "requirements-dev.txt").read_text())
    assert match is not None, "pin line unparseable; see the previous test"
    live = _ha_version_file().strip()
    assert match.group("ha") == live, (
        f"requirements-dev.txt pins {match.group('pin')} "
        f"(HA {match.group('ha')}) but ha-version.txt says the box runs "
        f"HA {live}. Bump the pin to the matching release and update its "
        f"comment, or update ha-version.txt if the box was upgraded."
    )
