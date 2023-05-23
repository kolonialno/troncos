from starlette.requests import Request
from starlette.responses import Response

from troncos.profiling.bootstrap.profile import get_profile


async def profiling_view(request: Request) -> Response:
    profile, headers = get_profile()

    return Response(content=profile, headers=headers)
