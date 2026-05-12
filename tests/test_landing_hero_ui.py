"""Landing hero UI contract tests."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERO = ROOT / "assets" / "hero.html"


def _hero() -> str:
    return HERO.read_text(encoding="utf-8")


def test_explore_algorithms_opens_mission_briefing_not_map():
    html = _hero()

    assert 'id="ctos-explore"' in html
    assert 'aria-controls="algorithm-briefing"' in html
    assert 'exploreButton.addEventListener("click", () => setBriefing(true))' in html
    assert 'document.getElementById("ctos-explore").addEventListener("click", () => dismiss("explore"))' not in html
    assert 'class="briefing" id="algorithm-briefing"' in html
    assert "Algorithm Mission Briefing" in html


def test_hero_preserves_start_and_trace_message_actions():
    html = _hero()

    assert 'document.getElementById("ctos-start").addEventListener("click", () => dismiss("start"))' in html
    assert 'briefingStart.addEventListener("click", () => dismiss("start"))' in html
    assert 'briefingTrace.addEventListener("click", () => dismiss("explore"))' in html
    assert 'window.parent.postMessage({ type: "ctos-hero-dismiss", action }, "*")' in html
    assert "Open Trace Mode" in html


def test_mission_briefing_contains_viva_ready_algorithm_cards():
    html = _hero()

    required_copy = [
        "Dijkstra",
        "route planning and baseline shortest paths",
        "A*",
        "emergency routing and Dijkstra vs A* Race Lab",
        "Kruskal / Prim",
        "Network mode for cost-aware road expansion planning",
        "Greedy",
        "signal allocation and emergency preemption choices",
        "Dynamic Programming",
        "maintenance budgets, bus allocation, and metro scheduling",
        "Smart-city value",
    ]
    for text in required_copy:
        assert text in html

    assert html.count('class="briefing-card') == 5
    assert "briefing-visual" in html
    assert "briefing-badge" in html


def test_hero_accessibility_motion_and_no_emoji_icons():
    html = _hero()

    assert ":focus-visible" in html
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert 'aria-expanded="false"' in html
    assert 'aria-hidden="true"' in html
    assert 'aria-label="Close algorithm mission briefing"' in html

    emoji_ranges = (
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F900-\U0001F9FF"
    )
    import re

    assert re.search(f"[{emoji_ranges}]", html) is None
