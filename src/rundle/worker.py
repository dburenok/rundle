"""Serve a plain `predict(input) -> output` function as a serverless worker.

In your image:

    CMD ["python", "-m", "rundle.worker", "model:predict"]

`model.py` holds the real code and knows nothing about any provider. This
module is the shim: it speaks the provider's worker protocol and hands each
job's input to `predict`. Requires `pip install "rundle[worker]"`.
"""

import importlib
import inspect
import sys


def load(target: str):
    """Resolve "module:function" to the function."""
    module, _, fn = target.partition(":")
    if not module or not fn:
        raise ValueError(f"expected module:function, got {target!r}")
    return getattr(importlib.import_module(module), fn)


def serve_runpod(predict):
    import runpod  # optional dep; only needed inside the image

    if inspect.iscoroutinefunction(predict):

        async def handler(job):
            return await predict(job["input"])

    else:

        def handler(job):
            return predict(job["input"])

    runpod.serverless.start({"handler": handler})


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        sys.exit("usage: python -m rundle.worker module:function")
    serve_runpod(load(argv[0]))


if __name__ == "__main__":
    main()
