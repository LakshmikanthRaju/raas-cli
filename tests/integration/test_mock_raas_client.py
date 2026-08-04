from __future__ import annotations

import json

import httpx

from salt_config_cli.api.client import AriaConfigClient


def make_client(handler) -> AriaConfigClient:
    client = AriaConfigClient(
        server="https://raas.example.test",
        username="automation-user",
        password="secret",
        ssl_verify=True,
        use_cache=False,
    )
    client._client.close()
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    return client


def test_password_login_rpc_fallback_and_job_flow() -> None:
    status_calls = 0
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal status_calls
        if request.method == "GET" and request.url.path == "/account/login":
            return httpx.Response(200, headers={"set-cookie": "_xsrf=xsrf-1; Path=/"})
        if request.url.path == "/account/login":
            body = json.loads(request.content)
            assert body["username"] == "automation-user"
            return httpx.Response(200, json={"jwt": "jwt-1"})

        paths.append(request.url.path)
        if request.url.path == "/rpc":
            return httpx.Response(404, text="not found")

        payload = json.loads(request.content)
        assert request.headers["authorization"] == "JWT jwt-1"
        method = payload["method"]
        if method == "echo":
            ret = payload["kwarg"]["message"]
        elif method == "get_versions":
            ret = "8.17.0"
        elif method == "route_cmd":
            assert payload["kwarg"]["fun"] == "test.ping"
            ret = "202607280001"
        elif method == "get_cmd_status":
            status_calls += 1
            ret = ["running" if status_calls == 1 else "complete"]
        elif method == "get_returns":
            ret = {"results": [{"minion_id": "node-1", "return": True}]}
        else:
            ret = None
        return httpx.Response(200, json={"riq": payload["riq"], "ret": ret})

    client = make_client(handler)
    client.authenticate()
    assert client.rpc_path == "/raas/rpc"
    assert client.get_versions() == "8.17.0"

    submitted = client.call(
        "cmd",
        "route_cmd",
        cmd="local",
        fun="test.ping",
        tgt={"*": {"tgt": "*", "tgt_type": "glob"}},
    )
    assert submitted.ret == "202607280001"
    assert client.call("cmd", "get_cmd_status", jids=[submitted.ret]).ret == ["running"]
    assert client.call("cmd", "get_cmd_status", jids=[submitted.ret]).ret == ["complete"]
    results = client.call("ret", "get_returns", jid=submitted.ret).ret
    assert results["results"][0]["return"] is True
    assert paths[:2] == ["/rpc", "/raas/rpc"]
    client.close()
