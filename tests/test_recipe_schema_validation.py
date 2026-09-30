"""Phase 10.6 — validate recipe JSON shape on load.

The Showcase_Basic1.json mentioned in the plan does not exist in the
repo, so the happy-path recipe is synthesized inline here. The tests
exercise:
  - P1: a minimal-but-valid recipe passes :func:`validate_recipe`.
  - N1: unsupported schema_version raises :class:`RecipeError`.
  - N2: missing required region key (NODES / CONNECTIONS) raises.
  - N3: a CONNECTIONS endpoint references a node not in NODES.
  - N4: malformed JSON file raises :class:`RecipeError` via
        :func:`load_recipe`, with the underlying JSONDecodeError chained.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from glados_pycromanager.autonomous.recipe_io import (
    RECIPE_SCHEMA_VERSION,
    RECIPE_SCHEMA_VERSION_KEY,
    REQUIRED_RECIPE_KEYS,
    load_recipe,
    validate_recipe,
)
from glados_pycromanager.errors import RecipeError


def _minimal_valid_recipe() -> dict:
    return {
        RECIPE_SCHEMA_VERSION_KEY: RECIPE_SCHEMA_VERSION,
        "NODES": {
            "InitNode_1": {"preset": "node_preset_pink"},
            "AnalysisNode_1": {"preset": "node_preset_green"},
        },
        "CONNECTIONS": [
            ["InitNode_1.outAttr", "AnalysisNode_1.inAttr"],
        ],
    }


def test_minimal_recipe_validates() -> None:
    recipe = _minimal_valid_recipe()
    assert validate_recipe(recipe) is recipe


def test_legacy_recipe_without_version_accepted() -> None:
    recipe = _minimal_valid_recipe()
    del recipe[RECIPE_SCHEMA_VERSION_KEY]
    # legacy mode (strict=False default) tolerates a missing version
    assert validate_recipe(recipe) is recipe


def test_strict_missing_version_raises() -> None:
    recipe = _minimal_valid_recipe()
    del recipe[RECIPE_SCHEMA_VERSION_KEY]
    with pytest.raises(RecipeError, match=RECIPE_SCHEMA_VERSION_KEY):
        validate_recipe(recipe, strict=True)


def test_future_schema_version_raises() -> None:
    recipe = _minimal_valid_recipe()
    recipe[RECIPE_SCHEMA_VERSION_KEY] = RECIPE_SCHEMA_VERSION + 5
    with pytest.raises(RecipeError, match="unsupported"):
        validate_recipe(recipe)


@pytest.mark.parametrize("missing_key", REQUIRED_RECIPE_KEYS)
def test_missing_required_region_raises(missing_key: str) -> None:
    recipe = _minimal_valid_recipe()
    del recipe[missing_key]
    with pytest.raises(RecipeError, match=missing_key):
        validate_recipe(recipe)


def test_connections_reference_unknown_node_raises() -> None:
    recipe = _minimal_valid_recipe()
    recipe["CONNECTIONS"].append(
        ["GhostNode_99.out", "AnalysisNode_1.in"],
    )
    with pytest.raises(RecipeError, match="GhostNode_99"):
        validate_recipe(recipe)


def test_connections_malformed_endpoint_raises() -> None:
    recipe = _minimal_valid_recipe()
    recipe["CONNECTIONS"].append(["no-dot-here", "AnalysisNode_1.in"])
    with pytest.raises(RecipeError, match="no-dot-here"):
        validate_recipe(recipe)


def test_connections_wrong_arity_raises() -> None:
    recipe = _minimal_valid_recipe()
    recipe["CONNECTIONS"].append(["A.out"])
    with pytest.raises(RecipeError, match="2-element"):
        validate_recipe(recipe)


def test_top_level_not_object_raises() -> None:
    with pytest.raises(RecipeError, match="JSON object"):
        validate_recipe([1, 2, 3])


def test_nodes_not_object_raises() -> None:
    recipe = _minimal_valid_recipe()
    recipe["NODES"] = ["node1"]
    with pytest.raises(RecipeError, match="'NODES'"):
        validate_recipe(recipe)


def test_connections_not_list_raises() -> None:
    recipe = _minimal_valid_recipe()
    recipe["CONNECTIONS"] = "oops"
    with pytest.raises(RecipeError, match="'CONNECTIONS'"):
        validate_recipe(recipe)


def test_load_recipe_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "recipe.json"
    target.write_text(json.dumps(_minimal_valid_recipe()), encoding="utf-8")
    out = load_recipe(target)
    assert out["NODES"]["InitNode_1"]["preset"] == "node_preset_pink"


def test_load_recipe_malformed_json_chains(tmp_path: Path) -> None:
    target = tmp_path / "broken.json"
    target.write_text("{not-json{{", encoding="utf-8")
    with pytest.raises(RecipeError) as info:
        load_recipe(target)
    assert isinstance(info.value.__cause__, (OSError, json.JSONDecodeError))


def test_load_recipe_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(RecipeError):
        load_recipe(tmp_path / "does_not_exist.json")
