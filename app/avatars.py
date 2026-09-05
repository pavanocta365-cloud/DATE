"""Deterministic SVG avatars, generated offline so seed data needs no network."""
from __future__ import annotations

import hashlib

_PALETTE = (
    ("#ff7a59", "#ff3d81"), ("#7c5cff", "#22d3ee"), ("#f59e0b", "#ef4444"),
    ("#10b981", "#3b82f6"), ("#ec4899", "#8b5cf6"), ("#06b6d4", "#3b82f6"),
    ("#f43f5e", "#f97316"), ("#14b8a6", "#84cc16"), ("#6366f1", "#ec4899"),
    ("#eab308", "#f43f5e"), ("#0ea5e9", "#6366f1"), ("#a855f7", "#ec4899"),
)


def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


def avatar_url(seed: str) -> str:
    safe = "".join(ch for ch in (seed or "x") if ch.isalnum() or ch in "-_")[:40]
    return "/avatar/%s.svg" % (safe or "x")


def render_svg(seed: str, label: str = "") -> str:
    digest = hashlib.sha256((seed or "x").encode("utf-8")).digest()
    start, end = _PALETTE[digest[0] % len(_PALETTE)]
    angle = digest[1] % 360
    text = initials(label or seed)
    # Two soft blobs keep the tiles from looking like flat colour swatches.
    bx1, by1 = 30 + digest[2] % 40, 25 + digest[3] % 30
    bx2, by2 = 55 + digest[4] % 35, 60 + digest[5] % 30
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        'width="400" height="400" role="img" aria-label="%(text)s">'
        '<defs><linearGradient id="g" gradientTransform="rotate(%(angle)d 0.5 0.5)">'
        '<stop offset="0%%" stop-color="%(start)s"/>'
        '<stop offset="100%%" stop-color="%(end)s"/></linearGradient>'
        '<filter id="b"><feGaussianBlur stdDeviation="9"/></filter></defs>'
        '<rect width="100" height="100" fill="url(#g)"/>'
        '<g filter="url(#b)" opacity="0.35">'
        '<circle cx="%(bx1)d" cy="%(by1)d" r="22" fill="#ffffff"/>'
        '<circle cx="%(bx2)d" cy="%(by2)d" r="18" fill="#000000"/></g>'
        '<text x="50" y="50" font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif" '
        'font-size="34" font-weight="600" fill="#ffffff" fill-opacity="0.92" '
        'text-anchor="middle" dominant-baseline="central">%(text)s</text>'
        "</svg>"
    ) % {"text": text, "angle": angle, "start": start, "end": end,
         "bx1": bx1, "by1": by1, "bx2": bx2, "by2": by2}
