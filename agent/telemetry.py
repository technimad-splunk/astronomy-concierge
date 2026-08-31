"""The keystone: instrument the agent ONCE, fan telemetry out to BOTH backends.

This is design §3. A single OpenTelemetry ``TracerProvider`` (spans) plus a
single ``MeterProvider`` (GenAI metrics) carry the agent's telemetry, and one
LangChain/LangGraph instrumentor captures every reasoning step (LLM calls, tool
calls, agent/workflow nodes) using the **OpenTelemetry GenAI semantic
conventions** (``gen_ai.*``). From that one instrumentation we fan out to both
backends.

**Why this instrumentor.** Splunk *AI Agent Monitoring* (APM -> AI agents / AI
trace data) keys off the OTel GenAI semantic conventions (``gen_ai.*`` span
attributes) **and** GenAI metrics (token-usage / operation-duration histograms).
OpenInference attributes (``llm.*``) are NOT recognized by those pages, so we use
the OpenLLMetry / Traceloop ``opentelemetry-instrumentation-langchain``
instrumentor, which Splunk lists as a supported "third-party instrumentation"
source to translate. Critically, unlike the official OTel-contrib LangChain
instrumentation (which only emits ``gen_ai.*`` for ``ChatOpenAI``/``ChatBedrock``
and silently skips other providers), the Traceloop instrumentor hooks the
LangChain callback-manager layer and populates ``gen_ai.*`` for **this** stack
too — ``ChatOllama`` (default) and ``ChatOpenAI`` alike — and emits the GenAI
client histograms Splunk requires. See ``agent/README.md``.

**Splunk (operational / infra lens)** — a ``BatchSpanProcessor`` (spans) and a
``PeriodicExportingMetricReader`` (metrics) with OTLP/gRPC exporters to the LOCAL
Splunk OpenTelemetry Collector (default ``localhost:4317``), which forwards to
Splunk Observability. OTLP only — never ``sapm``. Metrics use **delta**
temporality (required by Splunk AI Agent Monitoring).

**Galileo (AI / agent lens)** — two supported paths, selected by env:

- ``callback`` (default): Galileo's first-class ``GalileoCallback`` for
  LangChain/LangGraph. It uses the authenticated Galileo SDK and is the path
  Galileo's docs recommend for agent-level Sessions -> Traces -> Spans + metrics.
  Robust across enterprise/multitenant deployments. It is INDEPENDENT of the OTel
  GenAI conventions, so swapping the OTel/Splunk instrumentor does not affect it.
- ``otlp`` (opt-in via ``GALILEO_OTEL_EXPORT=1``): the pure "instrument once ->
  two OTLP exporters" path using ``galileo.otel.GalileoSpanProcessor`` on the same
  provider. Preferred conceptually, but its derived OTLP endpoint can 404 on some
  enterprise/multitenant tenants, so it is not the default.

Either way the SAME agent run is observed; both backends receive rich data.
No secrets are logged — only which backends were enabled and where.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace as trace_api
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

DEFAULT_SERVICE_NAME = "astronomy-concierge"
DEFAULT_DEPLOYMENT_ENV = "local-agent-galileo"
DEFAULT_OTLP_ENDPOINT = "http://localhost:4317"
SERVICE_VERSION = "0.1.0"
_LOGGER = logging.getLogger(__name__)

_TRUE = {"1", "true", "True", "yes", "on"}

# Splunk-documented GenAI knobs. These are the OpenTelemetry GenAI utility env
# vars the Splunk "Set up AI Agent Monitoring" doc prescribes. They are applied
# as process defaults (real .env values still win) so intent is explicit and the
# config also fits the Splunk SDOT GenAI-utility path if one switches to it.
#   span_metric -> emit BOTH spans and metrics
#   SPAN_ONLY   -> capture message content on spans (not events)
#   delta       -> metric temporality required by AI Agent Monitoring
#
# TRACELOOP_TRACE_CONTENT=true is the lever that makes the Traceloop LangChain
# instrumentor put the actual prompt/completion content on LLM spans. Without it,
# LLM spans carry no message content and Splunk AI Agent Monitoring reports
# "No parsable message event found". With it on, the Traceloop->GenAI translator
# (registered below) reconstructs gen_ai.input.messages / gen_ai.output.messages
# in the schema the AI Agent Monitoring UI parses. setdefault keeps .env wins.
_GENAI_ENV_DEFAULTS = {
    "OTEL_INSTRUMENTATION_GENAI_EMITTERS": "span_metric",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "SPAN_ONLY",
    "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "delta",
    "TRACELOOP_TRACE_CONTENT": "true",
}


@dataclass
class TelemetryStatus:
    """What actually got wired up — surfaced to the user, no secrets."""

    service_name: str
    deployment_environment: str
    galileo_enabled: bool
    galileo_mode: str
    galileo_detail: str
    splunk_enabled: bool
    splunk_endpoint: str
    splunk_detail: str
    instrumentation: str
    translator_enabled: bool
    translator_detail: str
    metrics_enabled: bool
    metrics_detail: str


@dataclass
class Telemetry:
    """Handle returned by :func:`setup_telemetry` — holds the trace + meter
    providers, the optional Galileo logger/callback, and lifecycle helpers."""

    status: TelemetryStatus
    _provider: TracerProvider
    _meter_provider: Any = None
    _galileo_logger: Any = None
    _galileo_project_id: str | None = None
    _galileo_log_stream_id: str | None = None
    callbacks: list = field(default_factory=list)

    def start_session(self, session_id: str) -> None:
        """Group this conversation's traces under a Galileo session."""
        if self._galileo_logger is not None:
            try:
                self._galileo_logger.start_session(name=session_id, external_id=session_id)
            except Exception:  # pragma: no cover - non-fatal
                pass

    def flush_galileo(self, conclude: bool = False) -> None:
        """Flush Galileo callback-mode buffers and optionally conclude session.

        `conclude` is best-effort and only invoked when the underlying Galileo
        logger exposes a compatible `conclude()` API.
        """
        if self._galileo_logger is None:
            return
        try:
            self._galileo_logger.flush()
        except Exception:  # pragma: no cover
            pass
        if conclude:
            conclude_fn = getattr(self._galileo_logger, "conclude", None)
            if callable(conclude_fn):
                try:
                    conclude_fn()
                except Exception:  # pragma: no cover
                    pass

    def new_galileo_session(self, session_id: str) -> tuple[Any, list]:
        """Create an isolated per-conversation Galileo callback logger.

        In callback mode each conversation gets its own logger instance to avoid
        cross-conversation serialization/crosstalk while preserving the shared
        startup logger path used by the CLI.
        """
        if self.status.galileo_mode != "callback":
            return None, []
        if not self._galileo_project_id or not self._galileo_log_stream_id:
            _LOGGER.warning(
                "Galileo session logger unavailable for session_id=%s: missing "
                "resolved IDs (project_id=%r, log_stream_id=%r); running without "
                "Galileo callback for this session.",
                session_id,
                self._galileo_project_id,
                self._galileo_log_stream_id,
            )
            return None, []
        try:
            from galileo import GalileoLogger
            from galileo.handlers.langchain import GalileoCallback

            logger = GalileoLogger(
                project_id=self._galileo_project_id,
                log_stream_id=self._galileo_log_stream_id,
            )
            callback = GalileoCallback(galileo_logger=logger, flush_on_chain_end=True)
            logger.start_session(name=session_id, external_id=session_id)
            return logger, [callback]
        except Exception as exc:  # pragma: no cover - defensive
            _LOGGER.warning(
                "Galileo session logger creation failed for session_id=%s: %s; "
                "running without Galileo callback for this session.",
                session_id,
                exc,
            )
            return None, []

    def flush(self) -> None:
        self.flush_galileo()
        try:
            self._provider.force_flush()
        except Exception:  # pragma: no cover
            pass
        if self._meter_provider is not None:
            try:
                self._meter_provider.force_flush()
            except Exception:  # pragma: no cover
                pass

    def shutdown(self) -> None:
        self.flush()
        terminate_fn = getattr(self._galileo_logger, "terminate", None)
        if callable(terminate_fn):
            try:
                terminate_fn()
            except Exception:  # pragma: no cover
                pass
        try:
            self._provider.shutdown()
        except Exception:  # pragma: no cover
            pass
        if self._meter_provider is not None:
            try:
                self._meter_provider.shutdown()
            except Exception:  # pragma: no cover
                pass


def setup_telemetry() -> Telemetry:
    """Configure the single tracer provider + meter provider + dual fan-out.
    Returns a handle with status, Galileo callback(s), and flush/shutdown
    helpers."""
    # Apply the Splunk-documented GenAI defaults before any exporter/instrumentor
    # reads them. setdefault keeps real .env values authoritative.
    for key, value in _GENAI_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)

    service_name = os.getenv("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME)
    deployment_env = os.getenv("DEPLOYMENT_ENVIRONMENT", DEFAULT_DEPLOYMENT_ENV)

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": SERVICE_VERSION,
            "deployment.environment": deployment_env,
        }
    )
    provider = TracerProvider(resource=resource)

    # --- Splunk AI Agent Monitoring: Traceloop -> GenAI entity-model translator
    # The Traceloop LangChain instrumentor emits gen_ai.* on LLM spans, but keeps
    # the agent/workflow structure in its own traceloop.* shape (traceloop.span.kind,
    # traceloop.entity.*, traceloop.workflow.*), which Splunk AI Agent Monitoring
    # does not render. Splunk's Traceloop translator is a SpanProcessor that
    # promotes that shape into the OTel GenAI ENTITY model
    # (gen_ai.agent.*/gen_ai.workflow.*, invoke_agent/create_agent operations) and
    # reconstructs gen_ai.input.messages / gen_ai.output.messages from the captured
    # content. It MUTATES spans in place, so it MUST run before the export
    # BatchSpanProcessor; we register it FIRST. (It does NOT map ls_model_name ->
    # gen_ai.request.model, so the model name is corrected collector-side; see
    # stage/splunk-otel/otelcol-config-extras.yml.) Disable with
    # SPLUNK_GENAI_TRANSLATOR=0.
    translator_enabled = False
    translator_detail = "disabled (SPLUNK_GENAI_TRANSLATOR=0)"
    translator_on = os.getenv("SPLUNK_GENAI_TRANSLATOR", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    if translator_on:
        try:
            import opentelemetry.util.genai.traceloop as _tl_translator
            from opentelemetry.util.genai.processor.traceloop_span_processor import (
                TraceloopSpanProcessor,
            )

            provider.add_span_processor(
                TraceloopSpanProcessor(
                    attribute_transformations=_tl_translator._DEFAULT_ATTR_TRANSFORMATIONS,
                    name_transformations=_tl_translator._DEFAULT_NAME_TRANSFORMATIONS,
                    mutate_original_span=True,
                )
            )
            # We register the processor ourselves (first, before the exporter) for
            # deterministic ordering. Importing the package above also armed its
            # import-time auto-enable hook, which re-registers on the next
            # set_tracer_provider() call; its per-provider dedup checks an attribute
            # name this SDK version does not use, so without this it adds a DUPLICATE
            # processor. Setting the module's global registered-flag makes that hook
            # a no-op (it checks this flag first). Disable the whole feature with
            # SPLUNK_GENAI_TRANSLATOR=0.
            _tl_translator._PROCESSOR_REGISTERED = True
            translator_enabled = True
            translator_detail = (
                "splunk traceloop->genai translator: entity model + message "
                "reconstruction (span processor)"
            )
        except Exception as exc:  # pragma: no cover - defensive
            translator_detail = f"FAILED to initialize: {exc}"
    else:
        # The package ships a .pth that imports its module at interpreter startup,
        # arming a hook that auto-registers the translator on the next
        # set_tracer_provider() call. That fires before our runtime code (and before
        # .env is loaded), so the public env-var disable cannot win at runtime here.
        # Neutralize the armed hook for this process by marking it already-registered
        # so it becomes a no-op, leaving zero translator processors attached.
        try:
            import opentelemetry.util.genai.traceloop as _tl_translator

            _tl_translator._PROCESSOR_REGISTERED = True
        except Exception:  # pragma: no cover - defensive
            pass

    galileo_logger = None
    galileo_project_id: str | None = None
    galileo_log_stream_id: str | None = None
    callbacks: list = []
    galileo_enabled = False
    galileo_mode = "off"
    galileo_detail = "disabled (GALILEO_API_KEY not set)"

    # --- Galileo fan-out ---------------------------------------------------
    if os.getenv("GALILEO_API_KEY"):
        use_otlp = os.getenv("GALILEO_OTEL_EXPORT", "").strip() in _TRUE
        if use_otlp:
            try:
                from galileo import otel as galileo_otel

                processor = galileo_otel.GalileoSpanProcessor(
                    project=os.getenv("GALILEO_PROJECT"),
                    logstream=os.getenv("GALILEO_LOG_STREAM"),
                )
                galileo_otel.add_galileo_span_processor(provider, processor)
                galileo_enabled = True
                galileo_mode = "otlp"
                galileo_detail = (
                    f"OTLP span processor; project={os.getenv('GALILEO_PROJECT')!r} "
                    f"log_stream={os.getenv('GALILEO_LOG_STREAM')!r}"
                )
            except Exception as exc:  # pragma: no cover - defensive
                galileo_detail = f"OTLP path FAILED to initialize: {exc}"
        else:
            try:
                from galileo import GalileoLogger
                from galileo.handlers.langchain import GalileoCallback

                galileo_logger = GalileoLogger(
                    project=os.getenv("GALILEO_PROJECT"),
                    log_stream=os.getenv("GALILEO_LOG_STREAM"),
                )
                galileo_project_id = getattr(galileo_logger, "project_id", None)
                galileo_log_stream_id = getattr(galileo_logger, "log_stream_id", None)
                callbacks.append(
                    GalileoCallback(galileo_logger=galileo_logger, flush_on_chain_end=True)
                )
                galileo_enabled = True
                galileo_mode = "callback"
                galileo_detail = (
                    f"GalileoCallback; project={os.getenv('GALILEO_PROJECT')!r} "
                    f"log_stream={os.getenv('GALILEO_LOG_STREAM')!r}"
                )
                if not galileo_project_id or not galileo_log_stream_id:
                    galileo_detail += (
                        " (WARNING: startup logger resolved without project/log-stream IDs; "
                        "per-session logger creation may fail)"
                    )
                    _LOGGER.warning(
                        "Galileo callback startup logger resolved without IDs "
                        "(project_id=%r, log_stream_id=%r).",
                        galileo_project_id,
                        galileo_log_stream_id,
                    )
            except Exception as exc:  # pragma: no cover - defensive
                galileo_detail = f"callback path FAILED to initialize: {exc}"

    # --- Splunk fan-out (OTLP/gRPC -> local Splunk collector) --------------
    # The same local collector receives BOTH spans (traces) and GenAI metrics
    # (histograms). The collector forwards them to Splunk Observability; AI Agent
    # Monitoring needs the gen_ai.* spans AND the GenAI histogram metrics.
    splunk_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_OTLP_ENDPOINT)
    splunk_enabled = False
    splunk_detail = "disabled (SPLUNK_OTLP_DISABLED=1)"
    meter_provider = None
    metrics_enabled = False
    metrics_detail = "disabled (SPLUNK_OTLP_DISABLED=1)"
    if os.getenv("SPLUNK_OTLP_DISABLED", "").strip() not in _TRUE:
        insecure = splunk_endpoint.startswith("http://")
        # Spans
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=splunk_endpoint, insecure=insecure)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            splunk_enabled = True
            splunk_detail = "OTLP/gRPC spans -> local Splunk OTel Collector"
        except Exception as exc:  # pragma: no cover - defensive
            splunk_detail = f"FAILED to initialize: {exc}"

        # GenAI metrics (delta-temporality histograms -> same collector).
        try:
            from opentelemetry import metrics as metrics_api
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.metrics.export import AggregationTemporality
            from opentelemetry.sdk.metrics import Counter, Histogram, ObservableCounter
            from opentelemetry.sdk.metrics import (
                ObservableGauge,
                ObservableUpDownCounter,
                UpDownCounter,
            )

            # Splunk AI Agent Monitoring requires DELTA temporality (and
            # send_otlp_histograms: true on the collector's signalfx exporter,
            # which forwards the native OTLP histograms). We set delta EXPLICITLY
            # per instrument kind rather than relying solely on
            # OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta, so the
            # OTLP->collector exporter is guaranteed delta regardless of env. (The
            # GENAI_METRICS_CONSOLE_DEBUG reader is separate and prints cumulative
            # because ConsoleMetricExporter ignores that preference — it does NOT
            # reflect this exporter.)
            _delta = AggregationTemporality.DELTA
            _cumulative = AggregationTemporality.CUMULATIVE
            preferred_temporality = {
                Counter: _delta,
                UpDownCounter: _cumulative,
                Histogram: _delta,
                ObservableCounter: _delta,
                ObservableUpDownCounter: _cumulative,
                ObservableGauge: _cumulative,
            }
            metric_exporter = OTLPMetricExporter(
                endpoint=splunk_endpoint,
                insecure=insecure,
                preferred_temporality=preferred_temporality,
            )
            readers = [PeriodicExportingMetricReader(metric_exporter)]

            # Off-by-default diagnostic: set GENAI_METRICS_CONSOLE_DEBUG=1 to also
            # dump every metric data point (incl. the gen_ai.client.token.usage /
            # gen_ai.client.operation.duration histograms) to stdout on a short
            # interval. Lets an operator PROVE the agent actually produces and
            # flushes the GenAI histograms without needing the collector. No
            # effect on the normal OTLP export path; never enabled by default.
            console_debug = os.getenv("GENAI_METRICS_CONSOLE_DEBUG", "").strip() in _TRUE
            if console_debug:
                from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

                readers.append(
                    PeriodicExportingMetricReader(
                        ConsoleMetricExporter(), export_interval_millis=5000
                    )
                )

            meter_provider = MeterProvider(resource=resource, metric_readers=readers)
            metrics_api.set_meter_provider(meter_provider)
            metrics_enabled = True
            metrics_detail = (
                "OTLP/gRPC GenAI metrics (delta) -> local Splunk OTel Collector"
            )
            if console_debug:
                metrics_detail += " (+console debug dump)"
        except Exception as exc:  # pragma: no cover - defensive
            metrics_detail = f"FAILED to initialize: {exc}"

    trace_api.set_tracer_provider(provider)

    # --- single instrumentation feeding the providers (-> Splunk, + Galileo OTLP)
    # OpenLLMetry / Traceloop LangChain instrumentor: emits OTel GenAI semantic
    # conventions (gen_ai.* spans) AND the GenAI client histograms
    # (gen_ai.client.token.usage, gen_ai.client.operation.duration) for ALL
    # LangChain chat models — including ChatOllama, our default — which the
    # official OTel-contrib instrumentor does not. This is what lights up Splunk
    # AI Agent Monitoring. Galileo is unaffected (its GalileoCallback is separate).
    instrumentation = "traceloop:opentelemetry-instrumentation-langchain"
    try:
        from opentelemetry.instrumentation.langchain import LangchainInstrumentor

        LangchainInstrumentor().instrument(
            tracer_provider=provider, meter_provider=meter_provider
        )
    except Exception as exc:  # pragma: no cover - defensive
        instrumentation = f"FAILED to initialize: {exc}"

    status = TelemetryStatus(
        service_name=service_name,
        deployment_environment=deployment_env,
        galileo_enabled=galileo_enabled,
        galileo_mode=galileo_mode,
        galileo_detail=galileo_detail,
        splunk_enabled=splunk_enabled,
        splunk_endpoint=splunk_endpoint,
        splunk_detail=splunk_detail,
        instrumentation=instrumentation,
        translator_enabled=translator_enabled,
        translator_detail=translator_detail,
        metrics_enabled=metrics_enabled,
        metrics_detail=metrics_detail,
    )
    return Telemetry(
        status=status,
        _provider=provider,
        _meter_provider=meter_provider,
        _galileo_logger=galileo_logger,
        _galileo_project_id=galileo_project_id,
        _galileo_log_stream_id=galileo_log_stream_id,
        callbacks=callbacks,
    )
