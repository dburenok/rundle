<img src="assets/logo.png" alt="Rundle logo" width="160">

# Rundle

**Deploy once, run on any serverless GPU provider.**

Rundle deploys the same container to every provider you give it, then routes
each job across that fleet — racing them, or falling through rung by rung
when one is throttled, full, or broken.

> [!WARNING]
> Under active development. APIs may change without notice.

## Usage

```python
import rundle
from rundle import Deployment, Race, Registry, Router, Scaling
from rundle.providers import Runpod

spec = Deployment(
    name="whisper",
    gpu="80GB",                       # a VRAM tier, not a card
    env={"MODEL": "large-v3"},
    scaling=Scaling(min=0, max=3),
)

fleet = await rundle.ensure(spec, providers=[
    Runpod(image="you/whisper:1.2", registry=Registry("DockerHub")),
])

router = Router(fleet, policy=Race(stagger=[0]))
result = await router.submit({"audio_url": "..."}).result()
result.output, result.endpoint.provider
```

Your container needs one function; the provider plumbing is Rundle's problem, not yours:

```python
# model.py
def predict(input: dict) -> dict: ...
```

```dockerfile
RUN pip install "rundle[worker]"
CMD ["python", "-m", "rundle.worker", "model:predict"]
```

See [`examples/hello`](examples/hello) for a complete image.

## How it's put together

**`Deployment` is portable; images are set per provider.** A
`Deployment` says what the workload needs — GPU tier, env, scaling. Each
provider gets its own `image` (and registry credential), to allow for varying configurations (ex. weights baked in on one, mounted from a volume
on another).

**GPUs are requested by VRAM tier, not by card.** `gpu="24GB"` means "a GPU
with 24 GB of VRAM, cheapest available." That is what providers actually
sell: Runpod pools several cards of equal VRAM and places you on whichever
has capacity; Modal ranks cards cheapest-first. Tiers fall through in order:
`gpu=["24GB", "48GB"]`.

**`ensure` is declarative, Terraform-style.** It finds the endpoint by
name, diffs the live config against the spec, and patches only what
drifted. Running it twice is a no-op. Changing the image, env, or GPU tier
and running it again applies exactly that change.

**Routing is the heart of Rundle.** Every provider implements `submit`,
`status`, and `cancel`; policies compose them. `Sequential` tries one
provider at a time. `Race(stagger=[0, 0, 45])` submits to each provider
after its delay in seconds, and the first job to start _running_ wins — the
rest are cancelled, and late rungs never submit. That's useful when a cheap
provider is flaky and a pricier one is reliable: give the cheap one a head
start, and pay for the reliable one only when it's needed. A rung whose job
fails before running drops out of the race rather than stalling it.

**One image, thin shims.** Providers speak different worker protocols
(Runpod polls a queue; Modal calls a function). Rather than one image per
provider, your `predict()` stays provider-free and `rundle.worker` wraps it
in whichever protocol the container is running under.

**Secrets pass through, never rest.** A `Registry("DockerHub")` is a
reference to a credential that already exists on the provider. Passing a
username and token lets Rundle create it there when missing; Rundle never
stores them, and they're excluded from every `repr`.

## Providers

|                            | deploy  | jobs    | notes                                      |
| -------------------------- | ------- | ------- | ------------------------------------------ |
| Runpod                     | ✓       | ✓       |                                            |
| SaladCloud                 | planned | planned | REST, any image; cheap interruptible GPUs  |
| Baseten                    | planned | planned | REST, custom Docker server                 |
| Hugging Face               | planned | planned | REST, bring your own container             |
| Vast.ai                    | planned | planned | REST, but the image must run their PyWorker |
| Modal                      | planned | planned | Python SDK, no create-endpoint REST call   |
| fal                        | planned | planned | CLI/SDK; direct server mode proxies HTTP   |
| Cerebrium                  | planned | planned | CLI + toml, custom Dockerfiles             |
| Beam                       | planned | planned | Python SDK                                 |

## License

Apache-2.0 — see [LICENSE](LICENSE).
