"""Safe, explicit Earth Engine initialization for FuegoPA.

This module deliberately does not authenticate, persist tokens, activate
billing, or store the project identifier.  Callers must provide
``EARTH_ENGINE_PROJECT`` in the process environment.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Mapping


SENTINEL2_SR_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
CLOUD_SCORE_PLUS_COLLECTION = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"


class EarthEngineConfigurationError(RuntimeError):
    """Raised when the local Earth Engine configuration is incomplete."""


class EarthEngineQueryError(RuntimeError):
    """Raised when an Earth Engine operation cannot be completed.

    The original exception is retained as ``__cause__`` and in the diagnostic
    attributes.  Callers can redact those attributes for logs without losing
    the original exception chain in memory or during debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str = "",
        error_stage: str = "query",
        event_id: str | None = None,
        aoi_id: str | None = None,
        window_id: str | None = None,
        attempt: int | None = None,
        retry_count: int | None = None,
        max_retries: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.operation = operation
        self.error_stage = error_stage
        self.event_id = event_id
        self.aoi_id = aoi_id
        self.window_id = window_id
        self.attempt = attempt
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.original_cause = cause
        self.cause_type = type(cause).__name__ if cause is not None else ""
        self.cause_message = str(cause) if cause is not None else ""
        self.wrapper_message = message
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        context = []
        if self.operation:
            context.append(f"operation={self.operation}")
        if self.event_id:
            context.append(f"event_id={self.event_id}")
        if self.aoi_id:
            context.append(f"aoi_id={self.aoi_id}")
        if self.window_id:
            context.append(f"window_id={self.window_id}")
        if self.attempt is not None:
            context.append(f"attempt={self.attempt}")
        if self.retry_count is not None:
            context.append(f"retry_count={self.retry_count}")
        prefix = f"{self.wrapper_message} ({', '.join(context)})" if context else self.wrapper_message
        if self.cause_type:
            return f"{prefix}; cause={self.cause_type}: {self.cause_message}"
        return prefix

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        *,
        operation: str,
        error_stage: str,
        event_id: str | None = None,
        aoi_id: str | None = None,
        window_id: str | None = None,
        attempt: int | None = None,
        retry_count: int | None = None,
        max_retries: int | None = None,
    ) -> "EarthEngineQueryError":
        if isinstance(exc, cls):
            return exc
        return cls(
            f"Falló la consulta Earth Engine: {operation}",
            operation=operation,
            error_stage=error_stage,
            event_id=event_id,
            aoi_id=aoi_id,
            window_id=window_id,
            attempt=attempt,
            retry_count=retry_count,
            max_retries=max_retries,
            cause=exc,
        )


def exception_diagnostics(exc: BaseException) -> dict[str, Any]:
    """Return structured exception metadata; callers sanitize before persistence."""

    current = exc.original_cause if isinstance(exc, EarthEngineQueryError) and exc.original_cause is not None else exc
    seen: set[int] = set()
    while current.__cause__ is not None and id(current) not in seen:
        seen.add(id(current))
        current = current.__cause__
    if isinstance(exc, EarthEngineQueryError):
        return {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "error_stage": exc.error_stage,
            "operation": exc.operation,
            "event_id": exc.event_id or "",
            "aoi_id": exc.aoi_id or "",
            "window_id": exc.window_id or "",
            "attempt": exc.attempt,
            "retry_count": exc.retry_count,
            "max_retries": exc.max_retries,
            "cause_type": type(current).__name__,
            "cause_message": str(current),
        }
    return {
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "error_stage": "runner",
        "operation": "",
        "event_id": "",
        "aoi_id": "",
        "window_id": "",
        "attempt": None,
        "retry_count": None,
        "max_retries": None,
        "cause_type": type(current).__name__,
        "cause_message": str(current),
    }


@dataclass(frozen=True)
class EarthEngineClient:
    """Initialized Earth Engine module plus the non-persisted project value."""

    ee_module: Any
    project: str

    @classmethod
    def initialize(
        cls,
        environ: Mapping[str, str] | None = None,
        ee_module: Any | None = None,
    ) -> "EarthEngineClient":
        env = os.environ if environ is None else environ
        project = str(env.get("EARTH_ENGINE_PROJECT", "")).strip()
        if not project:
            raise EarthEngineConfigurationError(
                "Falta EARTH_ENGINE_PROJECT. Configure el Cloud Project en el "
                "entorno antes de ejecutar Earth Engine; no se inferirá ni se hardcodeará."
            )

        module = ee_module
        if module is None:
            try:
                module = importlib.import_module("ee")
            except ImportError as exc:
                raise EarthEngineConfigurationError(
                    "No está instalado earthengine-api. Instale el extra de Earth Engine."
                ) from exc
        try:
            module.Initialize(project=project)
        except Exception as exc:  # Earth Engine exposes several auth/runtime exception types.
            raise EarthEngineConfigurationError(
                "No se pudo inicializar Earth Engine con EARTH_ENGINE_PROJECT. "
                "La autenticación debe hacerse previamente; este pipeline no ejecuta ee.Authenticate()."
            ) from exc
        return cls(module, project)

    def image_collection(self, collection_id: str) -> Any:
        return self.ee_module.ImageCollection(collection_id)

    def get_info(
        self,
        server_object: Any,
        description: str,
        *,
        error_stage: str = "get_info",
        event_id: str | None = None,
        aoi_id: str | None = None,
        window_id: str | None = None,
        attempt: int | None = None,
        retry_count: int | None = None,
        max_retries: int | None = None,
    ) -> Any:
        """Resolve one aggregated server-side object with a useful error."""

        try:
            return server_object.getInfo()
        except Exception as exc:
            raise EarthEngineQueryError.from_exception(
                exc,
                operation=description,
                error_stage=error_stage,
                event_id=event_id,
                aoi_id=aoi_id,
                window_id=window_id,
                attempt=attempt,
                retry_count=retry_count,
                max_retries=max_retries,
            ) from exc


def initialize_earth_engine(
    environ: Mapping[str, str] | None = None,
    ee_module: Any | None = None,
) -> EarthEngineClient:
    """Initialize Earth Engine without authenticating or exposing credentials."""

    return EarthEngineClient.initialize(environ=environ, ee_module=ee_module)


def smoke_test(client: EarthEngineClient) -> dict[str, Any]:
    """Confirm access to both required collections with minimal operations."""

    collection_results: dict[str, dict[str, Any]] = {}
    for collection_id in (SENTINEL2_SR_COLLECTION, CLOUD_SCORE_PLUS_COLLECTION):
        collection = client.image_collection(collection_id).limit(1)
        sample_count = client.get_info(collection.size(), f"acceso a {collection_id}")
        collection_results[collection_id] = {
            "accessible": True,
            "sample_size": int(sample_count or 0),
        }
    return {
        "earth_engine_initialized": True,
        "collections": collection_results,
        "scientific_results_written": False,
        "project_id_stored": False,
        "authentication_called": False,
    }
