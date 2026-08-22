from dataclasses import dataclass, field
from typing import Literal, get_args


GPU = Literal["16GB", "24GB", "32GB", "48GB", "80GB", "96GB", "141GB", "180GB"]
GPUS = get_args(GPU)


def vram_gb(tier: GPU) -> int:
    return int(tier[:-2])


@dataclass
class Scaling:
    min: int = 0
    max: int = 3
    idle_timeout: int = 2  # seconds


@dataclass
class Registry:
    """A Docker Hub credential, referenced by the name it has on each provider.
    Providing only the name assumes it already exists on the provider. Add
    username + password (a read-only access token, not your password) to
    have rundle create it when missing. Rundle never stores either."""

    name: str
    username: str | None = None
    password: str | None = field(default=None, repr=False)

    def __post_init__(self):
        if (self.username is None) != (self.password is None):
            raise ValueError("registry needs both username and password, or neither")


@dataclass
class Deployment:
    gpu: GPU | list[GPU]  # one tier, or several to fall back through in order
    image: str | None = (
        None  # default image; a provider may override with Provider(image=...)
    )
    gpu_count: int = 1  # cards per worker, leave at 1 unless you know what you're doing
    name: str | None = None  # defaults to a slug of the image
    env: dict[str, str] = field(default_factory=dict, repr=False)  # often holds secrets
    scaling: Scaling = field(default_factory=Scaling)
    disk_gb: int = 5
    timeout_ms: int = 30_000

    def __post_init__(self):
        if isinstance(self.gpu, str):
            self.gpu = [self.gpu]
        bad = [g for g in self.gpu if g not in GPUS]
        if not self.gpu or bad:
            raise ValueError(f"gpu must be one of {list(GPUS)}, got {bad or self.gpu}")
        if self.gpu_count < 1:
            raise ValueError("gpu_count must be >= 1")
        if not self.name and not self.image:
            raise ValueError("name is required when image is not set")

    @property
    def slug(self):
        if self.name:
            return self.name
        # "you/worker:1.0.2" -> "you-worker-1-0-2"
        return "".join(c if c.isalnum() else "-" for c in self.image).strip("-")


@dataclass(frozen=True)
class Endpoint:
    id: str
    provider: str
    name: str
    url: str  # where to send jobs
    created: bool = False  # True if ensure() had to create it
    changed: tuple[str, ...] = ()  # fields ensure() had to update on an existing one
