"""Isolate kanidm CLI token files between concurrent subprocesses.

Kanidm 1.10.x stores CLI session tokens at ``~/.cache/kanidm_tokens``, expanding
``~`` from ``$HOME``. Multiple ``kanidm login`` processes writing the same file
can corrupt JSON and break later commands. Give each CLI user its own ``HOME``.
"""

from __future__ import annotations

import os
import tempfile
from typing import MutableMapping


def isolated_kanidm_cli_env(
    base: MutableMapping[str, str] | None = None,
) -> tuple[dict[str, str], tempfile.TemporaryDirectory[str]]:
    """Build subprocess env with a private token cache directory.

    Returns ``(env, holder)``. Keep ``holder`` referenced until all kanidm CLI
    subprocesses for this env have finished.
    """
    holder = tempfile.TemporaryDirectory(prefix="kanidm-cli-cache-")
    env = dict(base if base is not None else os.environ)
    env["HOME"] = holder.name
    return env, holder
