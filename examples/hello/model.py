import platform
import shutil
import subprocess


def predict(input: dict) -> dict:
    gpu = "none"
    if shutil.which("nvidia-smi"):
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
        ).stdout.strip()
    return {
        "echo": input.get("prompt", "hello"),
        "gpu": gpu,
        "python": platform.python_version(),
    }
