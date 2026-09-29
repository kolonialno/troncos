import builtins
from typing import Any

import pytest
from ddtrace import config
from ddtrace.trace import tracer

from troncos.profiling import Exporter, configure_profiler

from tests.profiling.conftest import Configured

pytest.importorskip("pyroscope", reason="needs the 'profiling' extra")


def test_defaults_to_local_pyroscope(configured: Configured) -> None:
    configure_profiler(service_name="svc")

    assert configured[0]["server_address"] == "http://localhost:4040"
    assert configured[0]["application_name"] == "svc"


def test_endpoint_from_environment(
    configured: Configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYROSCOPE_HOST", "pyroscope.monitoring.svc.cluster.local")
    monkeypatch.setenv("PYROSCOPE_PORT", "4041")

    configure_profiler(service_name="svc")

    assert (
        configured[0]["server_address"]
        == "http://pyroscope.monitoring.svc.cluster.local:4041"
    )


def test_exporter_carries_credentials(configured: Configured) -> None:
    configure_profiler(
        service_name="svc",
        exporter=Exporter(
            scheme="https",
            host="profiles.example.com",
            port="443",
            basic_auth_username="user",
            basic_auth_password="secret",
            tenant_id="tenant",
            headers={"X-Scope-OrgID": "tenant"},
        ),
    )

    call = configured[0]
    assert call["server_address"] == "https://profiles.example.com:443"
    assert call["basic_auth_username"] == "user"
    assert call["basic_auth_password"] == "secret"
    assert call["tenant_id"] == "tenant"
    assert call["http_headers"] == {"X-Scope-OrgID": "tenant"}


def test_service_name_falls_back_to_ddtrace(configured: Configured) -> None:
    config.service = "from-ddtrace"

    configure_profiler()

    assert configured[0]["application_name"] == "from-ddtrace"


def test_service_name_is_required(configured: Configured) -> None:
    """Pyroscope groups by this name, so a placeholder would pool every service."""
    config.service = None

    with pytest.raises(ValueError, match="needs a service name"):
        configure_profiler()

    assert configured == []


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_service_name_is_rejected(configured: Configured, blank: str) -> None:
    """Even with a fallback available: a blank override is a mistake, not a request
    for the ddtrace name, and answering it silently would hide it."""
    config.service = "from-ddtrace"

    with pytest.raises(ValueError, match="needs a service name"):
        configure_profiler(service_name=blank)

    assert configured == []


def test_surrounding_whitespace_is_trimmed(configured: Configured) -> None:
    configure_profiler(service_name="  svc  ")

    assert configured[0]["application_name"] == "svc"


def test_tags_describe_the_deployment(configured: Configured) -> None:
    config.env = "prod"
    config.version = "1.2.3"

    configure_profiler(service_name="svc")

    tags = configured[0]["tags"]
    assert tags["app"] == "svc"
    assert tags["env"] == "prod"
    assert tags["version"] == "1.2.3"
    assert tags["instance"], "the hostname identifies which replica a profile came from"


def test_unset_ddtrace_fields_are_omitted(configured: Configured) -> None:
    config.env = None
    config.version = None

    configure_profiler(service_name="svc")

    tags = configured[0]["tags"]
    assert "env" not in tags, "an empty tag is worse than an absent one to group by"
    assert "version" not in tags


def test_tracer_tags_are_inherited(configured: Configured) -> None:
    tracer.set_tags({"owner": "team-a"})

    configure_profiler(service_name="svc")

    assert configured[0]["tags"]["owner"] == "team-a"


def test_explicit_tags_win(configured: Configured) -> None:
    tracer.set_tags({"owner": "team-a"})

    configure_profiler(service_name="svc", tags={"owner": "team-b", "role": "worker"})

    tags = configured[0]["tags"]
    assert tags["owner"] == "team-b"
    assert tags["role"] == "worker"


def test_disabled_starts_nothing(configured: Configured) -> None:
    configure_profiler(service_name="svc", enabled=False)

    assert configured == []


def test_disabled_does_not_need_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """A service gated on an env flag must import and run without pyroscope."""
    monkeypatch.setattr(builtins, "__import__", _refusing_to_import("pyroscope"))

    configure_profiler(service_name="svc", enabled=False)


def test_missing_extra_says_how_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "__import__", _refusing_to_import("pyroscope"))

    with pytest.raises(ImportError, match=r"troncos\[profiling\]"):
        configure_profiler(service_name="svc")


def _refusing_to_import(name: str) -> Any:
    real = builtins.__import__

    def guarded(module: str, *args: Any, **kwargs: Any) -> Any:
        if module == name:
            raise ImportError(f"No module named {name!r}")
        return real(module, *args, **kwargs)

    return guarded
