#!/usr/bin/env python3
"""
Data Flow Tracing System
Provides comprehensive instrumentation for tracking all input/output transformations
"""

import json
import logging
import time
import uuid
import functools
import threading
import inspect
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable, Union
from enum import Enum

# Thread-local storage for correlation IDs
_thread_local = threading.local()


class TraceLevel(Enum):
    """Tracing verbosity levels"""

    OFF = 0
    ERROR = 1
    WARN = 2
    INFO = 3
    DEBUG = 4
    TRACE = 5


class DataFlowTracer:
    """Main tracing system for data flow operations"""

    def __init__(
        self,
        name: str = "data_flow",
        level: TraceLevel = TraceLevel.INFO,
        structured: bool = True,
        include_timing: bool = True,
        include_data: bool = False,
        max_data_length: int = 1000,
    ):
        """
        Initialize the data flow tracer

        Args:
            name: Tracer name for logging
            level: Minimum trace level to log
            structured: Use structured JSON logging
            include_timing: Include performance timing
            include_data: Include actual data in traces (be careful with sensitive data)
            max_data_length: Maximum length of data to log
        """
        self.name = name
        self.level = level
        self.structured = structured
        self.include_timing = include_timing
        self.include_data = include_data
        self.max_data_length = max_data_length

        # Configure logger
        self.logger = logging.getLogger(f"trace.{name}")
        self.logger.setLevel(self._trace_level_to_logging_level(level))

        # Set up structured logging if requested
        if structured:
            formatter = JsonFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        # Only add handler if none exists to avoid duplicates
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _trace_level_to_logging_level(self, trace_level: TraceLevel) -> int:
        """Convert TraceLevel to logging level"""
        mapping = {
            TraceLevel.OFF: logging.CRITICAL + 10,
            TraceLevel.ERROR: logging.ERROR,
            TraceLevel.WARN: logging.WARNING,
            TraceLevel.INFO: logging.INFO,
            TraceLevel.DEBUG: logging.DEBUG,
            TraceLevel.TRACE: logging.DEBUG - 5,
        }
        return mapping.get(trace_level, logging.INFO)

    def _sanitize_data(self, data: Any) -> Any:
        """Sanitize data for logging"""
        if not self.include_data:
            return "[DATA_HIDDEN]"

        try:
            # Convert to string and truncate if needed
            data_str = str(data)
            if len(data_str) > self.max_data_length:
                return data_str[: self.max_data_length] + "...[TRUNCATED]"
            return data_str
        except Exception:
            return "[DATA_NOT_SERIALIZABLE]"

    def _get_correlation_id(self) -> str:
        """Get or create correlation ID for current thread"""
        if not hasattr(_thread_local, "correlation_id"):
            _thread_local.correlation_id = str(uuid.uuid4())[:8]
        return _thread_local.correlation_id

    def _log_trace(self, level: TraceLevel, message: str, **kwargs):
        """Log a trace message with structured data"""
        if level.value > self.level.value:
            return

        trace_data = {
            "correlation_id": self._get_correlation_id(),
            "timestamp": datetime.utcnow().isoformat(),
            "tracer": self.name,
            "level": level.name,
            "message": message,
            **kwargs,
        }

        logging_level = self._trace_level_to_logging_level(level)

        if self.structured:
            self.logger.log(logging_level, json.dumps(trace_data, default=str))
        else:
            self.logger.log(
                logging_level, f"[{trace_data['correlation_id']}] {message}"
            )

    def trace_input(self, component: str, operation: str, data: Any, **metadata):
        """Trace data input to a component"""
        self._log_trace(
            TraceLevel.TRACE,
            f"INPUT -> {component}.{operation}",
            component=component,
            operation=operation,
            input_data=self._sanitize_data(data),
            metadata=metadata,
        )

    def trace_output(self, component: str, operation: str, data: Any, **metadata):
        """Trace data output from a component"""
        self._log_trace(
            TraceLevel.TRACE,
            f"OUTPUT <- {component}.{operation}",
            component=component,
            operation=operation,
            output_data=self._sanitize_data(data),
            metadata=metadata,
        )

    def trace_transformation(
        self,
        component: str,
        operation: str,
        input_data: Any,
        output_data: Any,
        duration: Optional[float] = None,
        **metadata,
    ):
        """Trace a complete transformation"""
        trace_data = {
            "component": component,
            "operation": operation,
            "input_data": self._sanitize_data(input_data),
            "output_data": self._sanitize_data(output_data),
            "metadata": metadata,
        }

        if duration is not None and self.include_timing:
            trace_data["duration_ms"] = round(duration * 1000, 3)

        self._log_trace(
            TraceLevel.DEBUG, f"TRANSFORM: {component}.{operation}", **trace_data
        )

    def trace_error(
        self,
        component: str,
        operation: str,
        error: Exception,
        input_data: Any = None,
        **metadata,
    ):
        """Trace an error with context"""
        self._log_trace(
            TraceLevel.ERROR,
            f"ERROR in {component}.{operation}: {str(error)}",
            component=component,
            operation=operation,
            error_type=type(error).__name__,
            error_message=str(error),
            input_data=(
                self._sanitize_data(input_data) if input_data is not None else None
            ),
            metadata=metadata,
        )

    def trace_performance(
        self, component: str, operation: str, duration: float, **metadata
    ):
        """Trace performance metrics"""
        self._log_trace(
            TraceLevel.INFO,
            f"PERF: {component}.{operation} took {duration*1000:.3f}ms",
            component=component,
            operation=operation,
            duration_ms=round(duration * 1000, 3),
            metadata=metadata,
        )

    @contextmanager
    def trace_operation(self, component: str, operation: str, **metadata):
        """Context manager for tracing complete operations"""
        start_time = time.time()
        correlation_id = self._get_correlation_id()

        self._log_trace(
            TraceLevel.DEBUG,
            f"START: {component}.{operation}",
            component=component,
            operation=operation,
            metadata=metadata,
        )

        try:
            yield correlation_id
            duration = time.time() - start_time

            self._log_trace(
                TraceLevel.DEBUG,
                f"SUCCESS: {component}.{operation}",
                component=component,
                operation=operation,
                duration_ms=round(duration * 1000, 3),
                metadata=metadata,
            )

            if self.include_timing and duration > 0.1:  # Log slow operations
                self.trace_performance(component, operation, duration, **metadata)

        except Exception as e:
            duration = time.time() - start_time
            self.trace_error(component, operation, e, **metadata)

            self._log_trace(
                TraceLevel.ERROR,
                f"FAILED: {component}.{operation}",
                component=component,
                operation=operation,
                duration_ms=round(duration * 1000, 3),
                error_type=type(e).__name__,
                error_message=str(e),
                metadata=metadata,
            )
            raise


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging"""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


# Global tracer instance
_global_tracer = DataFlowTracer("global", TraceLevel.INFO)


def set_global_tracer(tracer: DataFlowTracer):
    """Set the global tracer instance"""
    global _global_tracer
    _global_tracer = tracer


def get_global_tracer() -> DataFlowTracer:
    """Get the global tracer instance"""
    return _global_tracer


def trace_function(
    component: str = None,
    operation: str = None,
    include_args: bool = False,
    include_result: bool = False,
    tracer: DataFlowTracer = None,
):
    """
    Decorator to trace function calls

    Args:
        component: Component name (defaults to module name)
        operation: Operation name (defaults to function name)
        include_args: Include function arguments in trace
        include_result: Include function result in trace
        tracer: Tracer instance to use (defaults to global)
    """

    def decorator(func: Callable) -> Callable:
        nonlocal component, operation, tracer

        if component is None:
            component = func.__module__.split(".")[-1]
        if operation is None:
            operation = func.__name__
        if tracer is None:
            tracer = get_global_tracer()

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            metadata = {}
            if include_args:
                metadata["args"] = tracer._sanitize_data(args)
                metadata["kwargs"] = tracer._sanitize_data(kwargs)

            with tracer.trace_operation(component, operation, **metadata):
                if include_args:
                    tracer.trace_input(
                        component, operation, {"args": args, "kwargs": kwargs}
                    )

                result = func(*args, **kwargs)

                if include_result:
                    tracer.trace_output(component, operation, result)

                return result

        return wrapper

    return decorator


def trace_data_flow(
    input_data: Any,
    output_data: Any,
    component: str,
    operation: str,
    tracer: DataFlowTracer = None,
    **metadata,
):
    """Utility function to trace data transformations"""
    if tracer is None:
        tracer = get_global_tracer()

    tracer.trace_transformation(
        component, operation, input_data, output_data, **metadata
    )


@contextmanager
def correlation_context(correlation_id: str = None):
    """Set correlation ID for current thread context"""
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())[:8]

    old_id = getattr(_thread_local, "correlation_id", None)
    _thread_local.correlation_id = correlation_id

    try:
        yield correlation_id
    finally:
        if old_id is not None:
            _thread_local.correlation_id = old_id
        else:
            delattr(_thread_local, "correlation_id")


class TracingConfig:
    """Configuration for tracing system"""

    def __init__(self):
        self.enabled = True
        self.level = TraceLevel.INFO
        self.structured = True
        self.include_timing = True
        self.include_data = False
        self.max_data_length = 1000
        self.components = {}  # Component-specific settings

    def set_component_level(self, component: str, level: TraceLevel):
        """Set tracing level for specific component"""
        self.components[component] = {"level": level}

    def get_component_level(self, component: str) -> TraceLevel:
        """Get tracing level for specific component"""
        return self.components.get(component, {}).get("level", self.level)


# Example usage and instrumentation helpers
class InstrumentedMemoryAPI:
    """Example of how to instrument the PostgresMemoryAPI with tracing"""

    def __init__(self, api_instance, tracer: DataFlowTracer = None):
        self.api = api_instance
        self.tracer = tracer or get_global_tracer()

    @trace_function(
        component="memory_api",
        operation="store_memory",
        include_args=True,
        include_result=True,
    )
    def store_memory(self, content: str, **kwargs):
        """Instrumented store_memory with full tracing"""
        start_time = time.time()

        # Trace input
        self.tracer.trace_input(
            "memory_api",
            "store_memory",
            {
                "content_length": len(content),
                "content_preview": content[:100],
                "kwargs": kwargs,
            },
        )

        try:
            # Call original method
            result = self.api.store_memory(content, **kwargs)
            duration = time.time() - start_time

            # Trace successful transformation
            self.tracer.trace_transformation(
                "memory_api",
                "store_memory",
                input_data={"content": content, **kwargs},
                output_data={"memory_id": result},
                duration=duration,
            )

            # Trace output
            self.tracer.trace_output("memory_api", "store_memory", result)

            return result

        except Exception as e:
            # Trace error with context
            self.tracer.trace_error(
                "memory_api",
                "store_memory",
                e,
                input_data={"content": content, **kwargs},
            )
            raise

    @trace_function(component="memory_api", operation="retrieve_memories")
    def retrieve_memories(self, query: str, **kwargs):
        """Instrumented retrieve_memories with tracing"""
        with self.tracer.trace_operation(
            "memory_api", "retrieve_memories"
        ) as correlation_id:
            # Trace query processing
            self.tracer.trace_input(
                "memory_api",
                "retrieve_memories",
                {"query": query, "query_length": len(query), "kwargs": kwargs},
            )

            # Call original method
            results = self.api.retrieve_memories(query, **kwargs)

            # Trace results
            self.tracer.trace_output(
                "memory_api",
                "retrieve_memories",
                {
                    "result_count": len(results),
                    "results_preview": [r.get("content", "")[:50] for r in results[:3]],
                },
            )

            return results


def create_component_tracer(
    component_name: str, level: TraceLevel = TraceLevel.INFO, **kwargs
) -> DataFlowTracer:
    """Create a tracer for a specific component"""
    return DataFlowTracer(name=component_name, level=level, **kwargs)


# Pre-configured tracers for common components
embedding_tracer = create_component_tracer("embeddings", TraceLevel.DEBUG)
database_tracer = create_component_tracer("database", TraceLevel.INFO)
hook_tracer = create_component_tracer("hooks", TraceLevel.DEBUG)
validation_tracer = create_component_tracer("validation", TraceLevel.WARN)


if __name__ == "__main__":
    # Demo usage
    print("=== Data Flow Tracing System Demo ===")

    # Configure tracing
    tracer = DataFlowTracer(
        name="demo",
        level=TraceLevel.TRACE,
        structured=False,  # Human-readable for demo
        include_timing=True,
        include_data=True,
        max_data_length=200,
    )

    # Demo 1: Basic tracing
    with tracer.trace_operation("demo_component", "test_operation") as correlation_id:
        tracer.trace_input("demo_component", "test_operation", "Hello World")

        # Simulate processing
        time.sleep(0.1)

        tracer.trace_output("demo_component", "test_operation", "HELLO WORLD")

    # Demo 2: Function decorator
    @trace_function(
        component="demo",
        operation="string_transform",
        include_args=True,
        include_result=True,
        tracer=tracer,
    )
    def transform_string(text: str, upper: bool = True):
        time.sleep(0.05)  # Simulate processing
        return text.upper() if upper else text.lower()

    result = transform_string("Hello Tracing World")
    print(f"Result: {result}")

    # Demo 3: Error tracing
    try:
        with tracer.trace_operation("demo_component", "failing_operation"):
            tracer.trace_input("demo_component", "failing_operation", "bad input")
            raise ValueError("Simulated error for tracing demo")
    except ValueError:
        print("Error traced successfully")

    print("=== Demo Complete ===")
