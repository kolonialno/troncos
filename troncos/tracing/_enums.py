from enum import Enum


class ExporterType(Enum):
    HTTP = "http"
    GRPC = "grpc"


class Exporter:
    HTTP: "Exporter" = None  # type: ignore[assignment]
    GRPC: "Exporter" = None  # type: ignore[assignment]

    def __init__(
        self, exporter_type: ExporterType, headers: dict[str, str] | None = None
    ) -> None:
        self.exporter_type = exporter_type
        self.headers = headers


Exporter.HTTP = Exporter(ExporterType.HTTP)
Exporter.GRPC = Exporter(ExporterType.GRPC)
