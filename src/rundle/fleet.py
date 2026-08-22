import asyncio
import logging
from dataclasses import dataclass, field

from .providers.base import Provider
from .spec import Deployment, Endpoint

log = logging.getLogger("rundle")


@dataclass
class Fleet:
    """The same Deployment, live on several providers."""

    spec: Deployment
    endpoints: list[Endpoint]
    providers: dict[str, Provider]
    failed: dict[str, Exception] = field(default_factory=dict)

    def provider_for(self, endpoint: Endpoint) -> Provider:
        return self.providers[endpoint.provider]

    def __repr__(self):
        up = [e.provider for e in self.endpoints]
        return f"Fleet({self.spec.slug}: up={up} failed={list(self.failed)})"


async def ensure(spec: Deployment, providers: list[Provider]) -> Fleet:
    """Deploy `spec` to every provider at once. A provider that can't host it
    is recorded in `Fleet.failed`."""
    results = await asyncio.gather(
        *(p.ensure(spec) for p in providers), return_exceptions=True
    )
    fleet = Fleet(spec, [], {p.name: p for p in providers})
    for provider, result in zip(providers, results):
        if isinstance(result, Exception):
            log.warning("%s could not host %s: %s", provider.name, spec.slug, result)
            fleet.failed[provider.name] = result
        else:
            fleet.endpoints.append(result)
    if not fleet.endpoints:
        raise RuntimeError(f"no provider could host {spec.slug}: {fleet.failed}")
    return fleet
