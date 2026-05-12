"""Color and spacing tokens. Kept in Python so any component can access
them programmatically (e.g. for inline Leaflet styles), and mirrored in
assets/style.css for static styling.
"""
from __future__ import annotations

COLORS = {
    "bg_primary":     "#0e0e10",
    "bg_secondary":   "#18181b",
    "bg_tertiary":    "#27272a",
    "border":         "#2a2a2e",
    "text_primary":   "#fafafa",
    "text_secondary": "#a1a1aa",
    "text_muted":     "#71717a",
    "accent":         "#00E5FF",
    "accent_warm":    "#FFB800",
    "danger":         "#ef4444",
    "success":        "#22c55e",
    "road":           "#3a3a3a",
}

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
}

RADIUS = {
    "sm": 6,
    "md": 8,
    "lg": 12,
    "pill": 999,
}

FONT_STACK = (
    "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', "
    "Roboto, Oxygen, Ubuntu, sans-serif"
)
