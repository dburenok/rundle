import logging
import os

import httpx

from ..spec import GPU, GPUS, Endpoint
from .base import Job, Provider

log = logging.getLogger("rundle.runpod")

API = "https://api.runpod.io/v2"

MIN_CUDA = "13.0"

POOLS: dict[GPU, list[str]] = {
    "16GB": ["AMPERE_16"],
    "24GB": ["AMPERE_24"],
    "32GB": ["ADA_32_PRO"],
    "48GB": ["AMPERE_48"],
    "80GB": ["AMPERE_80"],
    "96GB": ["BLACKWELL_96"],
    "141GB": ["HOPPER_141"],
    "180GB": ["BLACKWELL_180"],
}
assert set(POOLS) <= set(GPUS), f"POOLS has unknown tiers: {set(POOLS) - set(GPUS)}"


class RunpodError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"runpod {status}: {detail}")


def _check(r: httpx.Response) -> httpx.Response:
    if r.is_error:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise RunpodError(r.status_code, detail)
    return r


def _matches(desired, existing) -> bool:
    """True if every key in `desired` has an equal value in `existing`.
    Runpod responses carry extra keys we never send; those are ignored."""
    if isinstance(desired, dict):
        return isinstance(existing, dict) and all(
            k in existing and _matches(v, existing[k]) for k, v in desired.items()
        )
    return desired == existing


class Runpod(Provider):
    name = "runpod"

    def __init__(self, api_key=None, image=None, registry=None):
        self.api_key = api_key or os.environ["RUNPOD_API_KEY"]
        self.image = image
        self.registry = registry

    def _client(self):
        return httpx.AsyncClient(
            base_url=API,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )

    async def ensure(self, spec):
        """Create or patch endpoint named `spec.slug` to match `spec`.

        Returns the resulting Endpoint."""
        async with self._client() as http:
            desired = self._body(spec)
            if self.registry is not None:
                desired["registry"] = await self._registry_id(http)

            r = _check(await http.get("/serverless"))
            existing = next(
                (ep for ep in r.json()["endpoints"] if ep["name"] == spec.slug), None
            )

            if existing is None:
                r = _check(await http.post("/serverless", json=desired))
                log.info("created endpoint %s (%s)", spec.slug, r.json()["id"])
                return self._endpoint(r.json(), created=True)

            changed = [
                k for k, v in desired.items() if not _matches(v, existing.get(k))
            ]
            if not changed:
                log.info("endpoint %s (%s) up to date", spec.slug, existing["id"])
                return self._endpoint(existing)

            patch = {k: desired[k] for k in changed}
            r = _check(await http.patch(f"/serverless/{existing['id']}", json=patch))
            log.info("updated endpoint %s (%s): %s", spec.slug, existing["id"], changed)
            return self._endpoint(r.json(), changed=tuple(changed))

    async def _registry_id(self, http):
        """Runpod wants a credential ID. Find ours by name; create it only if
        we were given credentials."""
        reg = self.registry
        r = _check(await http.get("/registries"))
        for existing in r.json()["registries"]:
            if existing["name"] == reg.name:
                return existing["id"]
        if reg.username is None:
            raise ValueError(
                f"runpod: no registry credential named {reg.name!r} -- create it in "
                f"the Runpod dashboard, or pass username/password to Registry()"
            )
        r = _check(
            await http.post(
                "/registries",
                json={
                    "name": reg.name,
                    "username": reg.username,
                    "password": reg.password,
                },
            )
        )
        log.info("stored registry credential %r", reg.name)
        return r.json()["id"]

    def _endpoint(self, ep, created=False, changed=()):
        return Endpoint(
            id=ep["id"],
            provider=self.name,
            name=ep["name"],
            url=ep["requestUrls"]["run"],
            created=created,
            changed=changed,
        )

    def _body(self, spec):
        """The create body. Also the source of truth for reconcile: every key
        here is compared against the live endpoint and patched if it drifted.
        `registry` is added by ensure() only when this provider manages one."""
        return {
            "name": spec.slug,
            "image": self.resolve_image(spec),
            "type": "QUEUE",
            "gpu": self._gpu(spec),
            "env": spec.env,
            "disk": spec.disk_gb,
            "workers": {
                "min": spec.scaling.min,
                "max": spec.scaling.max,
                "idleTimeout": spec.scaling.idle_timeout,
            },
            "scaling": {"type": "QUEUE_DELAY", "queueDelay": 2},
            "timeout": spec.timeout_ms,
        }

    def _gpu(self, spec):
        unknown = [t for t in spec.gpu if t not in POOLS]
        if unknown:
            raise ValueError(f"runpod: no serverless pool for {unknown}")
        pools = []
        for tier in spec.gpu:
            for pool in POOLS[tier]:
                if pool not in pools:
                    pools.append(pool)
        return {
            "pools": pools,
            "count": spec.gpu_count,
            "minCudaVersion": MIN_CUDA,
        }

    # ── jobs ──────────────────────────────────────────────────────────────
    # endpoint.url is the /run URL; the others are siblings of it.

    STATES = {
        "IN_QUEUE": "queued",
        "IN_PROGRESS": "running",
        "COMPLETED": "done",
        "FAILED": "failed",
        "TIMED_OUT": "failed",
        "CANCELLED": "cancelled",
    }

    async def submit(self, endpoint, payload):
        async with self._client() as http:
            r = _check(await http.post(endpoint.url, json={"input": payload}))
            return r.json()["id"]

    async def status(self, endpoint, job_id):
        base = endpoint.url.rsplit("/run", 1)[0]
        async with self._client() as http:
            r = _check(await http.get(f"{base}/status/{job_id}"))
        j = r.json()
        return Job(
            id=job_id,
            state=self.STATES.get(j["status"], "failed"),
            output=j.get("output"),
            error=j.get("error"),
        )

    async def cancel(self, endpoint, job_id):
        base = endpoint.url.rsplit("/run", 1)[0]
        async with self._client() as http:
            _check(await http.post(f"{base}/cancel/{job_id}"))
