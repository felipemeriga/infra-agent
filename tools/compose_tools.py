import json
import logging
from pathlib import Path

from config import Settings

logger = logging.getLogger(__name__)


def _get_compose_dir(compose_dir: str | None = None) -> Path:
    if compose_dir is not None:
        return Path(compose_dir)
    return Path(Settings().compose_dir)


def list_compose_files(compose_dir: str | None = None) -> str:
    """List all .yml/.yaml files in the compose directory."""
    directory = _get_compose_dir(compose_dir)
    if not directory.exists():
        return json.dumps({"error": f"Compose directory '{directory}' not found"})

    files = [f.name for f in directory.iterdir() if f.is_file() and f.suffix in (".yml", ".yaml")]
    return json.dumps(sorted(files), indent=2)


def read_compose_file(filename: str, compose_dir: str | None = None) -> str:
    """Read and return the content of a compose file."""
    directory = _get_compose_dir(compose_dir)

    if ".." in filename or filename.startswith("/"):
        return json.dumps({"error": "Invalid filename: path traversal not allowed"})

    filepath = directory / filename
    if not filepath.exists():
        return json.dumps({"error": f"File '{filename}' not found in compose directory"})

    return filepath.read_text()


def search_compose_files(query: str, compose_dir: str | None = None) -> str:
    """Search across all compose files for a service name, image, or config value."""
    directory = _get_compose_dir(compose_dir)
    if not directory.exists():
        return json.dumps({"error": f"Compose directory '{directory}' not found"})

    results = []
    for filepath in directory.iterdir():
        if not filepath.is_file() or filepath.suffix not in (".yml", ".yaml"):
            continue

        content = filepath.read_text()
        for line_num, line in enumerate(content.splitlines(), start=1):
            if query.lower() in line.lower():
                results.append(
                    {
                        "file": filepath.name,
                        "line": line_num,
                        "content": line.strip(),
                    }
                )

    return json.dumps(results, indent=2)
