import os


class Exporter:
    """Where profiles are pushed, and how to authenticate against it."""

    def __init__(
        self,
        *,
        scheme: str = "http",
        host: str | None = None,
        port: str | None = None,
        basic_auth_username: str = "",
        basic_auth_password: str = "",
        tenant_id: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        if host is None:
            host = os.environ.get("PYROSCOPE_HOST", "localhost")
        if port is None:
            port = os.environ.get("PYROSCOPE_PORT", "4040")

        self.endpoint = f"{scheme}://{host}:{port}"
        self.basic_auth_username = basic_auth_username
        self.basic_auth_password = basic_auth_password
        self.tenant_id = tenant_id
        self.headers = headers
