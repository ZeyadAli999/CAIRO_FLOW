"""CairoFlow Windows runtime stability tweaks.

Some Windows environments can hang when Python libraries ask
``platform.machine()`` and the stdlib falls through to a WMI query.  CairoFlow
does not need live WMI metadata, so keep imports deterministic for demos/tests.
"""

from __future__ import annotations

import os
import platform

if os.name == "nt":
    platform.machine = lambda: "AMD64"  # type: ignore[assignment]
