"""CairoFlow package initialization."""

from __future__ import annotations

import os
import platform

if os.name == "nt":
    # Avoid stdlib WMI probes that can hang during heavy third-party imports.
    platform.machine = lambda: "AMD64"  # type: ignore[assignment]
