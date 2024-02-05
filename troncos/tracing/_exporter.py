from enum import Enum


class ExporterType(Enum):
    HTTP = "http"
    GRPC = "grpc"


class Exporter:
    def __init__(
        self,
        *,
        scheme: str = "http",
        host: str = "localhost",
        port: str = "4318",
        path: str | None = None,
        exporter_type: ExporterType | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.headers = headers

        if not path:
            if port == "4317":
                path = "/"
            elif port == "4318":
                path = "/v1/traces"
        assert path, "You have to specify 'path'"
        assert path.startswith("/"), "'path' has to start with '/'"

        if not exporter_type:
            if port == "4317":
                exporter_type = ExporterType.GRPC
            elif port == "4318":
                exporter_type = ExporterType.HTTP
        assert exporter_type, "You have to specify 'exporter_type'"

        self.endpoint = f"{scheme}://{host}:{port}{path}"
        self.exporter_type = exporter_type
