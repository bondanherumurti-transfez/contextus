import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

tracer = trace.get_tracer(__name__)


def init_telemetry():
    honeycomb_key = os.getenv("HONEYCOMB_API_KEY")

    if not honeycomb_key:
        logger.info("[telemetry] No HONEYCOMB_API_KEY found — telemetry disabled")
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "contextus-api")

    resource = Resource.create({"service.name": service_name})

    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(
        endpoint="https://api.honeycomb.io/v1/traces",
        headers={"x-honeycomb-team": honeycomb_key},
    )

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    logger.info(f"[telemetry] Initialized with service.name={service_name}")


def instrument_app(app):
    if os.getenv("HONEYCOMB_API_KEY"):
        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        logger.info("[telemetry] Instrumented FastAPI + httpx")
