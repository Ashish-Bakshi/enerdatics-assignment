import pytest

from watcher.recipe import get_utility_config, load_recipe


def test_load_recipe_reads_landing_url(tmp_path):
    recipe_file = tmp_path / "recipe.yaml"
    recipe_file.write_text(
        """
landing_url: https://example.com/reports
utilities:
  Unitil:
    sheet: Sheet1
    id_column: Facility ID
    required_columns:
      - City/Town
""",
        encoding="utf-8",
    )

    recipe = load_recipe(recipe_file)

    assert recipe["landing_url"] == "https://example.com/reports"


def test_select_unitil_configuration():
    recipe = load_recipe("recipe.yaml")

    config = get_utility_config(recipe, "Unitil")

    assert config["sheet"] == "Sheet1"
    assert config["id_column"] == "Facility ID (if any)"
    assert len(config["required_columns"]) == 4


def test_select_eversource_configuration():
    recipe = load_recipe("recipe.yaml")

    config = get_utility_config(recipe, "Eversource East")

    assert config["sheet"] == "Tracking Sheet"
    assert config["id_column"] == "Facility ID (if any)"
    assert len(config["required_columns"]) == 4


def test_unknown_utility_raises_clear_error():
    recipe = load_recipe("recipe.yaml")

    with pytest.raises(ValueError, match="Unknown utility"):
        get_utility_config(recipe, "Unknown Utility")


def test_invalid_recipe_structure_is_rejected(tmp_path):
    recipe_file = tmp_path / "invalid.yaml"
    recipe_file.write_text(
        "landing_url: https://example.com/reports\nutilities: []\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="at least one utility"):
        load_recipe(recipe_file)
