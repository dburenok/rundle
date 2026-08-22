"""Send jobs to a Fleet according to a Policy.

router = Router(fleet, policy=Race(stagger=[0, 0, 45]))
handle = router.submit(payload)
result = await handle.result()
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .fleet import Fleet
from .providers.base import Job
from .spec import Endpoint

log = logging.getLogger("rundle.router")

POLL_INTERVAL = 1.0


@dataclass(frozen=True)
class Attempt:
    endpoint: Endpoint
    job_id: str
    state: str  # final state this attempt reached


@dataclass(frozen=True)
class Result:
    output: Any
    endpoint: Endpoint  # who actually served it
    attempts: tuple[Attempt, ...] = ()


class JobFailed(Exception):
    def __init__(self, attempts):
        self.attempts = attempts
        super().__init__(
            "; ".join(f"{a.endpoint.provider}:{a.job_id}={a.state}" for a in attempts)
        )


# ── policies ──────────────────────────────────────────────────────────────


class Policy:
    async def run(self, fleet: Fleet, payload: Any) -> Result:
        raise NotImplementedError

    @staticmethod
    async def _wait(fleet, endpoint, job_id, until=("done", "failed", "cancelled")):
        """Poll until the job reaches one of `until`; return the Job."""
        provider = fleet.provider_for(endpoint)
        while True:
            job = await provider.status(endpoint, job_id)
            if job.state in until:
                return job
            await asyncio.sleep(POLL_INTERVAL)


class Sequential(Policy):
    """One endpoint at a time, in fleet order. Move on if it fails or exceeds `timeout`."""

    def __init__(self, timeout: float = 300.0):
        self.timeout = timeout

    async def run(self, fleet, payload):
        attempts = []
        for ep in fleet.endpoints:
            provider = fleet.provider_for(ep)
            job_id = await provider.submit(ep, payload)
            try:
                job = await asyncio.wait_for(
                    self._wait(fleet, ep, job_id), self.timeout
                )
            except asyncio.TimeoutError:
                await provider.cancel(ep, job_id)
                attempts.append(Attempt(ep, job_id, "timeout"))
                continue
            attempts.append(Attempt(ep, job_id, job.state))
            if job.state == "done":
                return Result(job.output, ep, tuple(attempts))
        raise JobFailed(attempts)


class Race(Policy):
    """Submit to endpoint i after `stagger[i]` seconds. The first job to start
    running wins; every other job is cancelled. Then wait for the winner.
    A contender whose job fails before running drops out; if all drop out,
    JobFailed is raised."""

    def __init__(self, stagger: list[float]):
        if not stagger or any(s < 0 for s in stagger):
            raise ValueError("stagger must be a non-empty list of seconds >= 0")
        self.stagger = stagger

    async def run(self, fleet, payload):
        eps = fleet.endpoints
        if len(self.stagger) != len(eps):
            raise ValueError("stagger length must match the number of fleet endpoints")
        submitted: dict[Endpoint, str] = {}
        dropped: dict[Endpoint, str] = {}  # failed before running -> final state

        async def contender(ep, delay):
            await asyncio.sleep(delay)
            submitted[ep] = job_id = await fleet.provider_for(ep).submit(ep, payload)
            log.info("race: submitted to %s (%s)", ep.provider, job_id)
            job = await self._wait(
                fleet, ep, job_id, until=("running", "done", "failed", "cancelled")
            )
            if job.state in ("failed", "cancelled"):
                dropped[ep] = job.state
                log.info("race: %s dropped out (%s)", ep.provider, job.state)
                raise JobFailed([Attempt(ep, job_id, job.state)])
            return ep

        pending = {
            asyncio.create_task(contender(ep, d)) for ep, d in zip(eps, self.stagger)
        }
        winner = None
        while pending and winner is None:
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED
            )
            for t in done:
                if t.exception() is None:
                    winner = t.result()
                    break
        for t in pending:
            t.cancel()

        def attempts(winner_state=None):
            return tuple(
                Attempt(
                    ep,
                    jid,
                    dropped.get(ep) or (winner_state if ep is winner else "cancelled"),
                )
                for ep, jid in submitted.items()
            )

        if winner is None:
            raise JobFailed(attempts())

        losers = [
            asyncio.create_task(fleet.provider_for(ep).cancel(ep, jid))
            for ep, jid in submitted.items()
            if ep is not winner and ep not in dropped
        ]
        if losers:
            await asyncio.gather(*losers, return_exceptions=True)
        log.info("race: %s won, cancelled %d", winner.provider, len(losers))

        job = await self._wait(fleet, winner, submitted[winner])
        if job.state != "done":
            raise JobFailed(attempts(job.state))
        return Result(job.output, winner, attempts(job.state))


# ── router ────────────────────────────────────────────────────────────────


class Handle:
    def __init__(self, task: asyncio.Task):
        self._task = task

    async def result(self) -> Result:
        return await self._task

    def cancel(self):
        self._task.cancel()


class Router:
    def __init__(self, fleet: Fleet, policy: Policy | None = None):
        self.fleet = fleet
        self.policy = policy or Sequential()

    def submit(self, payload: Any) -> Handle:
        """Start a job under the policy. Returns at once; await handle.result()."""
        # TODO: files={...} -- providers take JSON only; needs an upload step
        return Handle(asyncio.create_task(self.policy.run(self.fleet, payload)))
