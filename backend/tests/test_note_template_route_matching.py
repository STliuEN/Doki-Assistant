from fastapi.routing import Match

from app.router.note_template_router import note_template_router


def test_reorder_route_precedes_template_id_route() -> None:
    scope = {
        "type": "http",
        "path": "/note-template/reorder",
        "method": "PUT",
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": [],
        "client": ("test", 1),
        "server": ("test", 1),
    }

    matches = [
        (route.name, route.matches(scope)[0], route.matches(scope)[1])
        for route in note_template_router.routes
    ]

    first_full = next(match for match in matches if match[1] is Match.FULL)
    assert first_full[0] == "reorder_templates"
    assert first_full[2]["path_params"] == {}
