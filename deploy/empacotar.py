"""Cria um ZIP de código e imagens, sem segredos nem banco local."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIRECTORIES = ("app", "migrations", "deploy")
FILES = ("run.py", "requirements.txt", "README.md", "AGENTS.md", ".env.example")


def build_package(project_root, destination):
    candidates = [project_root / name for name in FILES]
    for name in DIRECTORIES:
        candidates.extend((project_root / name).rglob("*"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as package:
        for path in sorted(candidates):
            relative = path.relative_to(project_root)
            if path.is_symlink() or not path.is_file() or "__pycache__" in relative.parts:
                continue
            if (path.name.startswith(".env") and path.name != ".env.example") or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".pyc", ".pyo"}:
                continue
            package.write(path, "project-casamento/" + relative.as_posix())
    return destination


if __name__ == "__main__":
    output = build_package(PROJECT_ROOT, PROJECT_ROOT / "dist" / "pythonanywhere-casamento.zip")
    print(f"Pacote criado: {output}")
    print(f"Tamanho: {output.stat().st_size / 1024 / 1024:.1f} MB. Não contém .env, banco, backups ou confirmações locais.")
