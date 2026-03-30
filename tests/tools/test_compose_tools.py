import json

import pytest


@pytest.fixture()
def compose_dir(tmp_path):
    rag = tmp_path / "rag-docker-compose.yml"
    rag.write_text(
        """services:
  rag-backend:
    image: felipemeriga1/rag-backend:latest
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgres://db:5432/rag
  rag-frontend:
    image: felipemeriga1/rag-frontend:latest
    ports:
      - "3000:3000"
"""
    )

    monitoring = tmp_path / "monitoring-compose.yaml"
    monitoring.write_text(
        """services:
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
"""
    )

    return str(tmp_path)


def test_list_compose_files(compose_dir):
    from tools.compose_tools import list_compose_files

    result = json.loads(list_compose_files(compose_dir=compose_dir))
    filenames = sorted(result)
    assert "monitoring-compose.yaml" in filenames
    assert "rag-docker-compose.yml" in filenames


def test_read_compose_file(compose_dir):
    from tools.compose_tools import read_compose_file

    result = read_compose_file("rag-docker-compose.yml", compose_dir=compose_dir)
    assert "rag-backend" in result
    assert "felipemeriga1/rag-backend:latest" in result


def test_read_compose_file_not_found(compose_dir):
    from tools.compose_tools import read_compose_file

    result = read_compose_file("nonexistent.yml", compose_dir=compose_dir)
    assert "not found" in result.lower() or "error" in result.lower()


def test_read_compose_file_rejects_path_traversal(compose_dir):
    from tools.compose_tools import read_compose_file

    result = read_compose_file("../../etc/passwd", compose_dir=compose_dir)
    assert "error" in result.lower()


def test_search_compose_files(compose_dir):
    from tools.compose_tools import search_compose_files

    result = json.loads(search_compose_files("rag-backend", compose_dir=compose_dir))
    assert len(result) >= 1
    assert any("rag-docker-compose.yml" in match["file"] for match in result)


def test_search_compose_files_no_match(compose_dir):
    from tools.compose_tools import search_compose_files

    result = json.loads(search_compose_files("nonexistent-service", compose_dir=compose_dir))
    assert len(result) == 0
