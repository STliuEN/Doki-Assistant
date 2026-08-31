from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobRuntimeConfig:
    lease_seconds: int = 60
    heartbeat_seconds: int = 15
    poll_seconds: float = 1.0
    shutdown_drain_seconds: int = 30
    max_attempts: int = 5
    global_backpressure: int = 1000
    owner_type_backpressure: int = 100
    payload_max_bytes: int = 256 * 1024
    result_max_bytes: int = 256 * 1024
    worker_metadata_max_bytes: int = 64 * 1024
    error_detail_max_bytes: int = 16 * 1024
    audit_json_max_bytes: int = 256 * 1024
    audit_reason_max_bytes: int = 4 * 1024
    retry_delays_seconds: tuple[int, ...] = (5, 30, 120, 600)

    def __post_init__(self) -> None:
        positive = (
            self.lease_seconds,
            self.heartbeat_seconds,
            self.poll_seconds,
            self.shutdown_drain_seconds,
            self.max_attempts,
            self.global_backpressure,
            self.owner_type_backpressure,
            self.payload_max_bytes,
            self.result_max_bytes,
            self.worker_metadata_max_bytes,
            self.error_detail_max_bytes,
            self.audit_json_max_bytes,
            self.audit_reason_max_bytes,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("job runtime limits must be positive")
        if self.heartbeat_seconds * 2 >= self.lease_seconds:
            raise ValueError("heartbeat interval must leave at least two renewal opportunities per lease")
        if self.owner_type_backpressure > self.global_backpressure:
            raise ValueError("owner/type backpressure cannot exceed the global limit")
        if len(self.retry_delays_seconds) != self.max_attempts - 1:
            raise ValueError("retry delays must cover every retry before max attempts")
        if any(value <= 0 for value in self.retry_delays_seconds):
            raise ValueError("retry delays must be positive")

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> JobRuntimeConfig:
        """Build limits from an explicit environment snapshot when supplied.

        E2 captures its process variables before the application's dotenv
        loaders run.  Accepting that snapshot here prevents a later dotenv
        load from changing a live runner's lease or retry contract.
        """
        values_source = environ if environ is not None else os.environ
        values = {
            "lease_seconds": int(values_source.get("JOB_LEASE_SECONDS", "60")),
            "heartbeat_seconds": int(values_source.get("JOB_HEARTBEAT_SECONDS", "15")),
            "poll_seconds": float(values_source.get("JOB_POLL_SECONDS", "1")),
            "shutdown_drain_seconds": int(values_source.get("JOB_SHUTDOWN_DRAIN_SECONDS", "30")),
            "max_attempts": int(values_source.get("JOB_MAX_ATTEMPTS", "5")),
            "global_backpressure": int(values_source.get("JOB_GLOBAL_BACKPRESSURE", "1000")),
            "owner_type_backpressure": int(values_source.get("JOB_OWNER_TYPE_BACKPRESSURE", "100")),
        }
        return cls(**values)
