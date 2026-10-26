"""The API must not load the worker executor: the workers are an external process (ADR 0014).

The catalogue already avoids importing a worker at boot (spaCy alone is ~1.7 s); the removal of the
in-process executor must not be undone by an import. The suite cannot see this in process — other
tests import the runner — so the check runs in a fresh interpreter.
"""

import subprocess
import sys

#: A fresh interpreter that imports the application module and nothing of the worker runtime.
_CODE = """
import sys

import scrinalia.asgi  # noqa: F401 - the import is the subject of the test

forbidden = [
    name
    for name in (
        "scrinalia.api.worker_runtime",
        "scrinalia.api.lifespan",
        "scrinalia.domains.archive.workers.runner",
        "scrinalia.domains.archive.workers.runner_daemon",
        "torch",
        "spacy",
    )
    if name in sys.modules
]
assert not forbidden, forbidden
print("ok")
"""


def test_the_api_does_not_load_the_worker_executor() -> None:
    result = subprocess.run([sys.executable, "-c", _CODE], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
