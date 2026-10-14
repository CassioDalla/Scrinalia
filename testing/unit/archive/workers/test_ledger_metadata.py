"""The ledger's own precondition: ``auth_users`` has to be in the metadata.

``archive_worker_runs`` carries a foreign key into ``auth_users``, and SQLAlchemy resolves a foreign
key when it **flushes** the insert, not when it reads. A process that imported only the archive
models could therefore read the ledger and not write it, and the ledger swallows a bookkeeping
failure by design — so a CLI run happened and left no line, while the panel's runs left one. The
run history quietly depended on which button was pressed.

The suite cannot see this in process: ``testing/conftest.py`` imports the identity models for every
test, so the metadata is complete whatever the ledger does. Hence the subprocess — it is the only
place the CLI's import graph is reproduced.
"""

import subprocess
import sys

#: A fresh interpreter that imports the ledger and nothing of identity on its own.
_CODE = """
from scrinalia.core.base import Base
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger

WorkerRunLedger(session_factory=lambda: None)
assert "auth_users" in Base.metadata.tables, sorted(Base.metadata.tables)
print("ok")
"""


def test_a_process_that_imports_only_the_archive_models_can_open_the_ledger() -> None:
    result = subprocess.run([sys.executable, "-c", _CODE], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
