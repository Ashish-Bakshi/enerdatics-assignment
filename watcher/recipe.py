"""Recipe loading, validation, and state versioning."""

from datetime import datetime
from pathlib import Path
import shutil
import yaml


def load_recipe(path: str | Path) -> dict:
    """Load a YAML recipe file and validate its structure."""
    recipe_path = Path(path)

    if not recipe_path.exists():
        raise FileNotFoundError(f"Recipe file not found: {recipe_path}")

    with recipe_path.open("r", encoding="utf-8") as file:
        recipe = yaml.safe_load(file)

    if not isinstance(recipe, dict):
        raise ValueError("Recipe must contain a valid YAML mapping.")

    landing_url = recipe.get("landing_url")
    if not isinstance(landing_url, str) or not landing_url.strip():
        raise ValueError("Recipe must define a non-empty landing_url.")

    utilities = recipe.get("utilities")
    if not isinstance(utilities, dict) or not utilities:
        raise ValueError("Recipe must define at least one utility configuration.")

    return recipe


def get_utility_config(recipe: dict, utility: str) -> dict:
    """Extract and validate the configuration for a given utility."""
    utilities = recipe.get("utilities", {})

    if utility not in utilities:
        available = ", ".join(sorted(utilities.keys()))
        raise ValueError(
            f"Unknown utility {utility!r}. Available utilities: {available}"
        )

    config = utilities[utility]
    if not isinstance(config, dict):
        raise ValueError(f"Configuration for {utility!r} must be a mapping.")

    for field in ("sheet", "id_column", "required_columns"):
        if field not in config:
            raise ValueError(f"Configuration for {utility!r} is missing {field!r}.")

    if not isinstance(config["sheet"], str) or not config["sheet"].strip():
        raise ValueError(f"Invalid sheet name configured for {utility!r}.")

    if not isinstance(config["id_column"], str) or not config["id_column"].strip():
        raise ValueError(f"Invalid ID column configured for {utility!r}.")

    required = config["required_columns"]
    if (
        not isinstance(required, list)
        or not required
        or not all(isinstance(c, str) and c.strip() for c in required)
    ):
        raise ValueError(f"Invalid required_columns configured for {utility!r}.")

    return config


def get_active_recipe_path(state_dir: str | Path, default_recipe_path: str | Path) -> Path:
    """Return the active recipe path in state, copying the initial recipe if needed."""
    state_path = Path(state_dir)
    state_path.mkdir(parents=True, exist_ok=True)
    active_path = state_path / "recipe.yaml"

    if not active_path.exists():
        shutil.copy2(default_recipe_path, active_path)

    return active_path


def update_recipe_column(
    state_dir: str | Path,
    utility: str,
    old_column: str,
    new_column: str,
) -> Path:
    """Safely update a column name in the state recipe and save a new version."""
    state_path = Path(state_dir)
    active_path = state_path / "recipe.yaml"

    recipe = load_recipe(active_path)
    config = get_utility_config(recipe, utility)

    updated_columns = [
        new_column if col == old_column else col
        for col in config["required_columns"]
    ]
    recipe["utilities"][utility]["required_columns"] = updated_columns

    # Save a versioned backup for auditability
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    versioned_backup = state_path / f"recipe.v_{timestamp}.yaml"
    with versioned_backup.open("w", encoding="utf-8") as file:
        yaml.safe_dump(recipe, file, sort_keys=False)

    temp_path = active_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(recipe, file, sort_keys=False)

    temp_path.replace(active_path)
    return active_path
