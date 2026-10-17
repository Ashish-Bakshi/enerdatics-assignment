import pytest

from watcher.source import discover_file

Landing_URL = "https://example.com/reports/"

def test_discovers_utility_month_link():
    html = """ 
    <a href="/files/unitil-march">
        Unitil (March 2026)
    </a>
    <a href="/files/unitil-april">
        Unitil (April 2026)
    </a>
    """

    result = discover_file(html, Landing_URL, "Unitil", "2026-03")
    assert result == "https://example.com/files/unitil-march"

def test_ignores_other_utilities():
    html = """
    <a href="/files/other">
        Eversource East (March 2026)
    </a>
    """

    with pytest.raises(LookupError, match="No report found"):
        discover_file(html, Landing_URL, "Unitil", "2026-03")

def test_rejects_ambiguous_links():
    html = """
    <a href="/files/one">Unitil (March 2026)</a>
    <a href="/files/two">Unitil (March 2026)</a>
    """

    with pytest.raises(LookupError, match="Multiple reports"):
        discover_file(html, Landing_URL, "Unitil", "2026-03")

def test_rejects_invalid_month():
    with pytest.raises(ValueError, match="YYYY-MM"):
        discover_file(
            "",
            Landing_URL,
            "Unitil",
            "March 2026",
        )