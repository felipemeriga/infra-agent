import json

import httpx
import respx


@respx.mock
def test_portainer_stacks(settings):
    respx.get("http://portainer:9000/api/stacks").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"Id": 1, "Name": "rag-stack", "Status": 1, "Type": 2},
                {"Id": 2, "Name": "monitoring", "Status": 1, "Type": 2},
            ],
        )
    )

    from tools.portainer_tools import portainer_stacks

    result = json.loads(portainer_stacks(settings=settings))
    assert len(result) == 2
    assert result[0]["Name"] == "rag-stack"


@respx.mock
def test_portainer_endpoints(settings):
    respx.get("http://portainer:9000/api/endpoints").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"Id": 1, "Name": "local", "Type": 1, "URL": "unix:///var/run/docker.sock"},
            ],
        )
    )

    from tools.portainer_tools import portainer_endpoints

    result = json.loads(portainer_endpoints(settings=settings))
    assert len(result) == 1
    assert result[0]["Name"] == "local"


@respx.mock
def test_portainer_stacks_with_api_key(monkeypatch, settings):
    monkeypatch.setattr(settings, "portainer_api_key", "my-portainer-key")

    route = respx.get("http://portainer:9000/api/stacks").mock(
        return_value=httpx.Response(200, json=[])
    )

    from tools.portainer_tools import portainer_stacks

    portainer_stacks(settings=settings)
    request = route.calls[0].request
    assert request.headers["x-api-key"] == "my-portainer-key"


@respx.mock
def test_portainer_stacks_handles_connection_error(settings):
    respx.get("http://portainer:9000/api/stacks").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    from tools.portainer_tools import portainer_stacks

    result = json.loads(portainer_stacks(settings=settings))
    assert "error" in result
