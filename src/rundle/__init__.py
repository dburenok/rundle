"""rundle: tiered fallback for inference workloads."""

from .fleet import Fleet, ensure
from .providers.base import Job, Provider
from .router import Handle, JobFailed, Race, Result, Router, Sequential
from .spec import GPU, GPUS, Deployment, Endpoint, Registry, Scaling

__version__ = "0.0.2"
__all__ = [
    "GPU",
    "GPUS",
    "Deployment",
    "Endpoint",
    "Fleet",
    "Handle",
    "Job",
    "JobFailed",
    "Provider",
    "Race",
    "Registry",
    "Result",
    "Router",
    "Scaling",
    "Sequential",
    "ensure",
]
