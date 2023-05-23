from typing import Any

from troncos.profiling.bootstrap.profile import get_profile


async def profiling_asgi_app(scope: Any, receive: Any, send: Any) -> None:
    profile, headers = get_profile()

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [header.lower().encode(), value.encode()]
                for header, value in headers.items()
            ],
        }
    )

    await send(
        {
            "type": "http.response.body",
            "body": profile,
        }
    )
