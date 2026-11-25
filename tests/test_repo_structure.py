"""Pruebas de integridad de la estructura modular del repositorio."""

from src.config import PROJECT_ROOT


def test_required_directories_exist() -> None:
    required_dirs = [
        "config",
        "data/raw",
        "data/processed",
        "data/external",
        "docker/init",
        "docs",
        "frontend",
        "notebooks",
        "src/api",
        "src/pipeline",
        "tests",
    ]
    for rel in required_dirs:
        assert (PROJECT_ROOT / rel).is_dir(), f"Falta directorio requerido: {rel}"


def test_required_base_files_exist() -> None:
    required_files = [
        ".gitignore",
        ".env.example",
        "LICENSE",
        "README.md",
        "pyproject.toml",
        "requirements.txt",
        "docker-compose.yml",
        "docker/init/01-init-postgis.sql",
        "config/settings.yaml",
        "data/raw/.gitkeep",
        "data/processed/.gitkeep",
        "data/external/.gitkeep",
        "notebooks/01_starter_and_baseline.ipynb",
    ]
    for rel in required_files:
        assert (PROJECT_ROOT / rel).is_file(), f"Falta archivo base requerido: {rel}"
