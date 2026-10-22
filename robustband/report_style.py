# SPDX-License-Identifier: MIT
"""Shared, dependency-free visual layer for every standalone report.

Reports are the artifact that travels: they are opened offline, attached to papers
and archived next to a result. They therefore carry the same design language as the
local app (same palette, type scale and verdict colours) but with no external asset,
no script and no network request: one HTML file, inline CSS, inline SVG.

Only the standard library is used, and every user-supplied value goes through
:func:`safe` before it reaches the document.
"""
from html import escape
from fractions import Fraction

# Palette shared with the local app (docs: ui.html). Keep the two in sync.
INK = "#18353b"
MUTED = "#4f6669"
LINE = "#dce6e5"
ACCENT = "#116b60"
SOFT = "#eef7f3"
BG = "#f6f8f7"
WARN = "#8b581a"
WARN_SOFT = "#fff4df"
BAD = "#8b2a1a"
BAD_SOFT = "#fdeceb"

_TONE_NAMES = frozenset(("ok", "warn", "bad", "neutral"))


def safe(value):
    """Escape any value for HTML text and attribute context."""
    return escape(str(value), quote=True)


def styles():
    """One inline stylesheet; no font, image or script is fetched."""
    return (
        "<style>"
        ":root{--ink:%s;--muted:%s;--line:%s;--accent:%s;--soft:%s;--bg:%s;--warn:%s;--warn-soft:%s;--bad:%s;--bad-soft:%s}"
        "*{box-sizing:border-box}"
        "body{margin:0;background:var(--bg);color:var(--ink);"
        "font:16px/1.7 'Segoe UI','Microsoft YaHei','PingFang SC',system-ui,sans-serif}"
        ".wrap{max-width:1100px;margin:0 auto;padding:26px 24px 60px}"
        ".rh{display:flex;flex-wrap:wrap;align-items:center;gap:10px;"
        "padding:6px 0 16px;border-bottom:1px solid var(--line);margin-bottom:24px}"
        ".mark{display:grid;place-items:center;width:28px;height:28px;"
        "border-radius:7px;background:var(--accent);color:#fff;font-weight:750}"
        ".brand{font-size:19px;font-weight:720;letter-spacing:-.4px}"
        ".ver{color:var(--muted);font-size:12px}"
        ".kicker{margin-left:auto;color:var(--muted);font-size:12px;letter-spacing:.4px}"
        "h1{font-size:26px;line-height:1.35;letter-spacing:-.4px;margin:6px 0 4px}"
        "h2{font-size:19px;line-height:1.4;margin:32px 0 10px}"
        "h3{font-size:16px;margin:24px 0 8px}"
        "p{margin:8px 0 12px}"
        ".muted{color:var(--muted)}.small{font-size:13px}"
        ".hero{background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin:16px 0 20px}"
        ".badge{display:inline-block;padding:3px 11px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.3px;"
        "border:1px solid var(--line);background:#fff;color:var(--muted)}"
        ".badge.ok{background:var(--soft);border-color:#bcdccf;color:var(--accent)}"
        ".badge.warn{background:var(--warn-soft);border-color:#ecd3a8;color:var(--warn)}"
        ".badge.bad{background:var(--bad-soft);border-color:#efc4bf;color:var(--bad)}"
        ".bandtext{font-size:30px;font-weight:700;letter-spacing:-.6px;margin:10px 0 2px;overflow-wrap:anywhere}"
        ".lede{font-size:16px;margin:6px 0 0;max-width:74ch}"
        ".stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px;margin:18px 0 6px}"
        ".stat{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px}"
        ".stat b{display:block;font-size:21px;line-height:1.3}"
        ".stat span{color:var(--muted);font-size:12px}"
        "figure{margin:18px 0 6px}"
        "figcaption{color:var(--muted);font-size:12px;margin-top:4px}"
        "table{border-collapse:collapse;width:100%%;font-size:14px;background:#fff}"
        "th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}"
        "th{font-size:12px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted)}"
        "tr:last-child td{border-bottom:0}"
        ".scroll{overflow:auto;border:1px solid var(--line);border-radius:12px;margin:10px 0}"
        ".notice{background:var(--warn-soft);border:1px solid #ecd3a8;border-radius:12px;padding:12px 14px}"
        ".scope{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 18px 6px;margin:12px 0}"
        ".scope ul{margin:6px 0 10px;padding-left:20px}.scope li{margin:4px 0}"
        "code{font-family:ui-monospace,Consolas,monospace;font-size:13px;overflow-wrap:anywhere}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;"
        "border:1px solid var(--line);border-radius:12px;padding:12px}"
        "details{margin:10px 0}summary{cursor:pointer;font-weight:600}"
        "footer{margin-top:40px;border-top:1px solid var(--line);padding-top:14px;color:var(--muted);font-size:12px}"
        "footer p{margin:4px 0}"
        " @media print{body{background:#fff}.wrap{max-width:none;padding:0}"
        ".hero,.stat,.scope,.scroll{break-inside:avoid} .scroll{overflow:visible}}"
        "@media(max-width:640px){h1{font-size:22px}.bandtext{font-size:24px}.wrap{padding:18px 16px 44px}}"
        "</style>"
    ) % (INK, MUTED, LINE, ACCENT, SOFT, BG, WARN, WARN_SOFT, BAD, BAD_SOFT)


def page(title, body, *, lang="en"):
    """Wrap a fragment into a complete, self-contained document."""
    return ("<!doctype html><html lang='" + safe(lang) + "'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>" + safe(title) + "</title>" + styles() + "<body><div class='wrap'>" +
            body + "</div></body></html>")


def badge(text, tone="neutral"):
    """Verdict chip; tone is one of ok / warn / bad / neutral."""
    if tone not in _TONE_NAMES:
        raise ValueError("Unknown badge tone: " + str(tone))
    cls = "badge" if tone == "neutral" else "badge " + tone
    return "<span class='" + cls + "'>" + safe(text) + "</span>"


def table(headers, rows, *, caption=None, scroll=True):
    """Escaped table; wrapped in a scroll container so narrow screens stay usable."""
    head = "<tr>" + "".join("<th>" + safe(h) + "</th>" for h in headers) + "</tr>"
    body = "".join("<tr>" + "".join("<td>" + safe(cell) + "</td>" for cell in row) + "</tr>" for row in rows)
    caption_html = "" if caption is None else "<caption class='small muted'>" + safe(caption) + "</caption>"
    html = "<table>" + caption_html + head + body + "</table>"
    return "<div class='scroll'>" + html + "</div>" if scroll else html


def _float(value):
    """Exact string endpoint to float, for geometry only (labels stay exact)."""
    return float(Fraction(str(value)))


def band_svg(lo, hi, lo_label, hi_label, *, unit="", zero_label="0",
             title="Rule range", positive_means="supports A"):
    """Inline SVG of the rule range with its two witness endpoints.

    Geometry uses floats; the printed labels are the exact endpoints passed in.
    Negative and positive regions differ by both colour and marker shape, so the
    figure stays readable without colour perception.
    """
    low, high = min(_float(lo), 0.0), max(_float(hi), 0.0)
    if low == high:
        high = low + 1.0
    pad = (high - low) * 0.08
    dmin, dmax = low - pad, high + pad
    left, right = 52.0, 668.0

    def x(value):
        return left + (value - dmin) / (dmax - dmin) * (right - left)

    x0, xl, xh = x(0.0), x(_float(lo)), x(_float(hi))
    # The bar covers the observed range only; the zero line is always visible, because
    # "is zero inside the range?" is the whole question the figure answers.
    split = min(max(x0, xl), xh)
    bar = 78.0 - 52.0
    suffix = (" " + unit) if unit else ""
    parts = [
        "<svg viewBox='0 0 720 132' role='img' aria-labelledby='bt bd' "
        "style='width:100%;height:auto;display:block'>",
        f"<title id='bt'>{safe(title)}</title>",
        f"<desc id='bd'>Rule range from {safe(lo_label)}{suffix} to {safe(hi_label)}{suffix}; "
        f"zero is marked so that {safe(positive_means)}.</desc>",
        f"<line x1='{left:.1f}' y1='65' x2='{right:.1f}' y2='65' stroke='{LINE}' stroke-width='2'/>",
        f"<line x1='{x0:.1f}' y1='46' x2='{x0:.1f}' y2='84' stroke='{MUTED}' "
        f"stroke-width='1.5' stroke-dasharray='3 3'/>",
        f"<text x='{x0:.1f}' y='33' text-anchor='middle' font-size='12' fill='{MUTED}'>{safe(zero_label)}</text>",
    ]
    if split > xl:
        parts.append(f"<rect x='{xl:.1f}' y='52' width='{split - xl:.1f}' height='{bar:.1f}' rx='6' fill='{WARN_SOFT}'/>")
    if xh > split:
        parts.append(f"<rect x='{split:.1f}' y='52' width='{xh - split:.1f}' height='{bar:.1f}' rx='6' fill='{SOFT}'/>")
    if xh - xl < 2.0:                                            # degenerate range: keep it visible
        parts.append(f"<rect x='{(xl + xh) / 2 - 1:.1f}' y='52' width='2' height='{bar:.1f}' fill='{MUTED}'/>")
    # witness endpoints: circle = low, triangle = high (shape carries the meaning)
    parts.append(f"<circle cx='{xl:.1f}' cy='65' r='7' fill='{ACCENT}' stroke='#fff' stroke-width='2'/>")
    parts.append(f"<path d='M{xh - 8:.1f} 57 L{xh:.1f} 73 L{xh + 8:.1f} 57 Z' fill='{WARN}' "
                 f"stroke='#fff' stroke-width='1.5'/>")
    if str(lo_label) == str(hi_label):                          # degenerate range: one label, centred
        parts.append(f"<text x='{(xl + xh) / 2:.1f}' y='105' text-anchor='middle' font-size='13' fill='{INK}'>"
                     f"{safe(lo_label)}{safe(suffix)}</text>")
    else:
        parts.append(f"<text x='{max(left, xl - 40):.1f}' y='105' text-anchor='start' font-size='13' fill='{INK}'>"
                     f"{safe(lo_label)}{safe(suffix)}</text>")
        parts.append(f"<text x='{min(right, xh + 40):.1f}' y='105' text-anchor='end' font-size='13' fill='{INK}'>"
                     f"{safe(hi_label)}{safe(suffix)}</text>")
    parts.append("</svg>")
    return ("<figure>" + "".join(parts) +
            f"<figcaption>{safe(title)}: shaded = zero to endpoint, circle = lowest margin, "
            "triangle = highest margin.</figcaption></figure>")
