from dataclasses import dataclass
from typing import Any, Literal

from ..spec import Deployment, Endpoint, Registry

JobState = Literal["queued", "running", "done", "failed", "cancelled"]


@dataclass(frozen=True)
class Job:
    """Provider-neutral view of one submitted job."""

    id: str
    state: JobState
    output: Any = None  # set when state == "done"
    error: str | None = None  # set when state == "failed"


class Provider:
    name: str
    image: str | None = None  # overrides Deployment.image for this provider only
    registry: Registry | None = (
        None  # credential for a private image; None = don't manage
    )

    def resolve_image(self, spec: Deployment) -> str:
        image = self.image or spec.image
        if not image:
            raise ValueError(
                f"{self.name}: no image -- set Deployment(image=...) "
                f"or {type(self).__name__}(image=...)"
            )
        return image

    async def ensure(self, spec: Deployment) -> Endpoint:
        raise NotImplementedError

    # ── job primitives the Router builds policies on ──────────────────────

    async def submit(self, endpoint: Endpoint, payload: Any) -> str:
        """Enqueue `payload`; return the provider's job id."""
        raise NotImplementedError

    async def status(self, endpoint: Endpoint, job_id: str) -> Job:
        raise NotImplementedError

    async def cancel(self, endpoint: Endpoint, job_id: str) -> None:
        raise NotImplementedError
