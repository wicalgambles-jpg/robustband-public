# SPDX-License-Identifier: MIT
"""The three local pages must ship together, share one palette and keep working links."""
import pathlib
import re

import pytest

from robustband import report_style

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGES = {name: ROOT / "robustband" / name for name in ("ui.html", "decision.html", "matrix.html")}


@pytest.mark.parametrize("name", sorted(PAGES))
def test_every_page_is_declared_as_package_data(name):
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    section = pyproject.split("[tool.setuptools.package-data]", 1)[1]
    assert '"%s"' % name in section, "%s is missing from package-data and would be absent from the wheel" % name


@pytest.mark.parametrize("name", sorted(PAGES))
def test_page_palette_matches_the_shared_report_layer(name):
    text = PAGES[name].read_text(encoding="utf-8")
    palette = dict(re.findall(r"--(ink|muted|line|accent):\s*(#[0-9a-fA-F]{6})", text))
    assert palette.get("ink", "").lower() == report_style.INK.lower()
    assert palette.get("accent", "").lower() == report_style.ACCENT.lower()
    assert palette.get("line", "").lower() == report_style.LINE.lower()


@pytest.mark.parametrize("name", sorted(PAGES))
def test_pages_reference_the_session_token_and_existing_routes(name):
    text = PAGES[name].read_text(encoding="utf-8")
    assert "location.hash" in text, "%s does not read the session token" % name
    for route in set(re.findall(r"['\"](/(?:api/[a-z/]+|matrix|decision))['\"]", text)):
        assert route.startswith("/matrix") or route.startswith("/decision") or route.startswith("/api/"), route


def test_relative_document_links_resolve():
    missing = []
    for document in [ROOT / "README.md", ROOT / "TUTORIAL.md", ROOT / "CONTRIBUTING.md"] + sorted((ROOT / "docs").glob("*.md")):
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\]\((?!https?:|#|mailto:)([^)\s]+)\)", text):
            path = (document.parent / target.split("#")[0]).resolve()
            if target.endswith("/") or path.is_dir():
                continue
            if not path.exists():
                missing.append("%s -> %s" % (document.relative_to(ROOT), target))
    assert not missing, "Broken relative links: " + "; ".join(missing)


def test_api_reference_lists_every_module():
    script = (ROOT / "docs" / "build_api_docs.py").read_text(encoding="utf-8")
    listed = set(re.findall(r'"(robustband(?:\.\w+)?)"', script))
    modules = {"robustband"} | {"robustband." + path.stem for path in (ROOT / "robustband").glob("*.py")}
    missing = sorted(modules - listed - {"robustband.__init__", "robustband.__main__"})
    assert not missing, "The API builder does not generate pages for: " + ", ".join(missing)
