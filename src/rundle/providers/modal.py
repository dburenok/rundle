from ..spec import vram_gb
from .base import Provider

# Modal sells cards, not tiers: (modal gpu string, VRAM GB, list $/h when written).
CARDS = [
    ("T4", 16, 0.59),
    ("L4", 24, 0.80),
    ("A10", 24, 1.10),
    ("L40S", 48, 1.95),
    ("A100-40GB", 40, 2.10),
    ("A100-80GB", 80, 2.50),
    ("RTX-PRO-6000", 96, 3.03),
    ("H100", 80, 3.95),
    ("H200", 141, 4.54),
    ("B200", 180, 6.25),
    ("B300", 288, 7.10),
]


class Modal(Provider):
    name = "modal"

    def __init__(self, image=None, registry=None):
        self.image = image
        self.registry = registry

    def _gpu(self, spec):
        """Modal honours list order, so a tier becomes every card with at least
        that much VRAM, cheapest first. Tiers in `spec.gpu` are tried in order."""
        out = []
        for tier in spec.gpu:
            need = vram_gb(tier)
            for card, vram, _ in sorted(CARDS, key=lambda c: c[2]):
                if vram >= need and card not in out:
                    out.append(card)
        if spec.gpu_count > 1:
            out = [f"{card}:{spec.gpu_count}" for card in out]
        return out

    async def ensure(self, spec):
        # TODO: build a modal.App from spec (image, gpu=self._gpu(spec), env, scaling) and deploy it
        raise NotImplementedError

    # TODO: submit/status/cancel via modal.Function.from_name(...).spawn() / FunctionCall.get()
