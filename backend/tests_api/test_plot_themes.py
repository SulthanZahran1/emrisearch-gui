"""The API theme table must stay identical to the prototype recipes."""

from __future__ import annotations

import ast
from pathlib import Path

from backend.emri.plot_themes import THEMES


RC_KEYS = {
    "figure.facecolor",
    "axes.facecolor",
    "text.color",
    "axes.labelcolor",
    "xtick.color",
    "ytick.color",
    "grid.color",
    "axes.edgecolor",
}


def _prototype_themes() -> dict:
    source_path = Path(__file__).resolve().parents[2] / "prototype" / "make_figs.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "THEMES"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("prototype/make_figs.py does not define THEMES")


def test_theme_keys_and_rc_shape_match_the_documented_contract():
    assert set(THEMES) == {"default", "dark", "paper"}
    for recipe in THEMES.values():
        assert set(recipe) == {"rc", "accent", "truth", "secondary", "grid"}
        assert set(recipe["rc"]) == RC_KEYS
        assert isinstance(recipe["grid"], bool)
        for color_name in ("accent", "truth", "secondary"):
            assert isinstance(recipe[color_name], str)


def test_backend_theme_recipes_equal_the_prototype_source_recipes():
    assert THEMES == _prototype_themes()
