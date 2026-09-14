"""Real authenticated E5 HTTP checks; credentials and response bodies stay private."""

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ops.e5.acceptance_env import save  # noqa: E402 - standalone CLI backend path bootstrap


def client(directory):
    auth = json.loads((directory / "auth.private.json").read_text())
    c = httpx.Client(base_url="http://127.0.0.1:18050", timeout=120, trust_env=False)
    response = c.post("/user/login/", json={"username": auth["login_name"], "password": auth["password"]})
    if response.status_code != 200:
        response = c.post(
            "/user/register/",
            json={
                "username": auth["login_name"],
                "email": auth["login_name"] + "@example.test",
                "password": auth["password"],
                "confirm_password": auth["password"],
            },
        )
    assert response.status_code == 200, (response.status_code, response.json().get("message"))
    value = response.json()["data"]
    c.headers["Authorization"] = "Bearer " + value["token"]
    save(directory / "api.private.json", value)
    save(
        directory / "browser.private.json",
        {
            "cookies": [
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": "127.0.0.1",
                    "path": cookie.path,
                    "expires": cookie.expires or -1,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Strict",
                }
                for cookie in c.cookies.jar
            ],
            "origins": [],
        },
    )
    return c, value["user"]["id"]


def setup(directory):
    with_client, owner = client(directory)
    with closing(with_client) as c:
        result = {"owner": owner, "checks": []}

        def check(name, response, expected):
            result["checks"].append({"case": name, "http": response.status_code, "passed": response.status_code == expected})
            assert response.status_code == expected, (name, response.status_code, response.json())
            return response.json().get("data")

        check("unauthenticated status", httpx.get("http://127.0.0.1:18050/knowledge/rag/status", trust_env=False), 401)
        state = check("initial status", c.get("/knowledge/rag/status"), 200)
        config = {**state["query_config"], "rerank": False, "top_k": 5}
        state = check(
            "save query without rebuilding",
            c.put("/knowledge/rag/query-config", json={"config": config, "expected_revision": state["query_revision"]}),
            200,
        )
        assert state["job_id"] is None
        content = "E5验收文档。独立数据库和独立向量目录中的紫色水獭计划采用三个阶段：准备、执行、验证。\n".encode("utf-8")
        check("upload accepted", c.post("/knowledge/add/multiple", files=[("files", ("e5-acceptance.txt", content, "text/plain"))]), 200)
        state = check("queued status", c.get("/knowledge/rag/status"), 200)
        assert state["status"] == "queued"
        for name, method, url, kw in (
            ("chat building 503", "post", "/chat/rag/query", {"json": {"query": "紫色水獭"}}),
            ("note search building 503", "get", "/note/search", {"params": {"q": "紫色水獭"}}),
            ("chunks building 503", "get", "/knowledge/chunks", {"params": {"filename": "e5-acceptance.txt"}}),
        ):
            data = check(name, getattr(c, method)(url, **kw), 503)
            assert data["status"] == "degraded" and data["job_id"] == state["job_id"]
        for path in ("/user/detail/", "/knowledge/list", "/note/list"):
            check("core API available " + path, c.get(path), 200)
        check("original available while building", c.get("/knowledge/detail", params={"filename": "e5-acceptance.txt"}), 200)
        check(
            "index mutation rejected while building",
            c.put(
                "/knowledge/rag/index-config", json={"config": {**state["index_config"], "chunk_size": 850}, "expected_revision": state["revision"]}
            ),
            409,
        )
        result["passed"] = all(row["passed"] for row in result["checks"])
        save(directory / "http-queued.json", result)
        print(json.dumps({"passed": result["passed"], "checks": len(result["checks"]), "owner": owner}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    setup(parser.parse_args().directory.resolve())
