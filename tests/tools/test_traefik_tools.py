import json

import httpx
import respx


@respx.mock
def test_traefik_routers(settings):
    respx.get("http://traefik:8080/api/http/routers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "name": "rag-backend@docker",
                    "rule": "Host(`api.example.com`)",
                    "status": "enabled",
                    "service": "rag-backend@docker",
                }
            ],
        )
    )

    from tools.traefik_tools import traefik_routers

    result = json.loads(traefik_routers(settings=settings))
    assert len(result) == 1
    assert result[0]["name"] == "rag-backend@docker"


@respx.mock
def test_traefik_services(settings):
    respx.get("http://traefik:8080/api/http/services").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "name": "rag-backend@docker",
                    "status": "enabled",
                    "loadBalancer": {"servers": [{"url": "http://172.18.0.5:8000"}]},
                }
            ],
        )
    )

    from tools.traefik_tools import traefik_services

    result = json.loads(traefik_services(settings=settings))
    assert len(result) == 1
    assert result[0]["status"] == "enabled"


@respx.mock
def test_traefik_entrypoints(settings):
    respx.get("http://traefik:8080/api/entrypoints").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "web", "address": ":80"},
                {"name": "websecure", "address": ":443"},
            ],
        )
    )

    from tools.traefik_tools import traefik_entrypoints

    result = json.loads(traefik_entrypoints(settings=settings))
    assert len(result) == 2


@respx.mock
def test_traefik_routers_handles_connection_error(settings):
    respx.get("http://traefik:8080/api/http/routers").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    from tools.traefik_tools import traefik_routers

    result = json.loads(traefik_routers(settings=settings))
    assert "error" in result
