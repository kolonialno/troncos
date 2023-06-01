from django.http import HttpRequest, HttpResponse

from troncos.profiling.bootstrap.profile import get_profile


def profiling_view(request: HttpRequest) -> HttpResponse:
    profile, headers = get_profile()

    return HttpResponse(profile, headers=headers)
