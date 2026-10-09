#!/usr/bin/env python3
"""Render a terminal-session GIF from captured output of the repo's own sample run.

Does not fabricate output: the three `CAPTURES` blocks below are the real stdout
this repo's real `demo/build_sample_report.py` and test suite produced when run
against the fictional "home-fitness-gear-review" demo vertical this repo ships
at the root (`competitors.csv`, `config.yaml`, `calendar.yaml`, `keywords.txt`,
`config/taxonomy.yml` -- see `demo/README.md`). The only edits made to any
captured line: the sandbox's incidental absolute temp-dir path was swapped for
the same repo-relative path a real run from the repo root would print, and the
verbose-vs-plain test runner flag was fixed at plain (`-m unittest discover -s
tests`, no `-v`) for a shorter, equally real summary instead of 66 per-test
lines. Nothing is shortened, reworded, or invented beyond that. This script
only does the typing/scrolling animation and rendering.

Usage: python3 docs/demo/make_terminal_gif.py
Requires: Pillow (pip install Pillow). No network, no repo code imported.
"""

import pathlib

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
OUT_GIF = HERE / "swipe_demo.gif"

# Exact captured stdout of each command, from a real run against the fictional
# demo vertical (reproduce with `python3 -m demo.build_sample_report` then
# `python3 -m unittest discover -s tests`, both from the repo root).
CAPTURES = [
    (
        "python3 -m demo.build_sample_report",
        """Wrote reports/2026-10-09_daily.md
Ledger rows added: 12 (data/history.csv)
Flags exercised in this sample: BREAKOUT, CALENDAR, CONVERGENCE, HOT_ENGAGEMENT""",
    ),
    (
        "head -n 32 reports/2026-10-09_daily.md",
        """HOMERACK DAILY SWIPE  -  2026-10-09  (lookback 24h, 48h grace)
Generated 2026-10-09 19:16 IST.
Sources: YouTube Data API live (0 units); vidIQ not run (synthetic demo data); community not run (synthetic demo data); thumbnails n/a (synthetic demo data); clustering local.

----------------------------------------------------------
PREFACE: WHAT THIS RUN DID
----------------------------------------------------------
> SYNTHETIC DEMO DATA. Every channel, video, and number below is invented
> for this portfolio repo's fictional home-fitness-gear-review vertical -
> no real channel was scanned and no live API was called to produce it.
> Regenerate with `python3 -m demo.build_sample_report`. See demo/README.md.

Scanned 13 competitor channels plus 2 own channel(s) across video - every upload in the window, not a sample.
Searched 15 seed keywords.
Fetched 10 videos and 2 community posts; scored 12 rows on VPH, outlier, engagement velocity, demand gap, convergence and calendar fit.
Outlier logic: vidIQ breakout score where available, else each video's VPH vs its own channel's recent-uploads baseline - so a small channel's hit ranks on merit, not size.
Niche filter: keyword discovery is restricted to home-fitness gear/equipment terms, so literal-'fitness' noise (unrelated wellness content) never reaches this report.
Funnel: 12 candidates -> 5 ranked picks on Page 1. YouTube quota used: 0 of 9000 units.
Ledger: starting fresh - data/history.csv was empty or absent; durable signals (sleepers, outcomes) build from today.
Engines: clustering: local.
Doing this sweep by hand - opening every channel, judging every upload, reading the comments - is roughly 1 hours of work. It was on your desk before the deadline.

==========================================================
PAGE 1  -  TODAY'S TOP PICKS  (the only page you must read)
==========================================================

1. [SHORT] Remix as a Short: packaging is over-indexing for the channel
   Title: We Did Not Expect This Kettlebell To Win
   GearHead Fitness Lab (direct, channel, 412K subs)
   VPH 9,000 | Outlier 20.0x | Flags: BREAKOUT, HOT_ENGAGEMENT
   Link: https://www.youtube.com/watch?v=demoGH03xyz
   Strategist take: Make a 60s Short on the HomeRack Fitness EN (direct head-to-head). Route to Strength Gear.""",
    ),
    (
        "python3 -m unittest discover -s tests",
        """..................................................................
----------------------------------------------------------------------
Ran 66 tests in 0.407s

OK""",
    ),
]

INTRO = "# fictional demo vertical (home-fitness-gear-review) -- not a live scan of a real channel"

# --- layout ---
COLS, ROWS = 108, 34
FONT_SIZE = 15
PAD_X, PAD_Y = 18, 16
BG = (13, 17, 23)
TITLEBAR = (22, 27, 34)
FG = (201, 209, 217)
GREEN = (63, 185, 80)
CYAN = (88, 166, 255)
YELLOW = (210, 153, 34)
DIM = (125, 133, 144)

font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
bold_font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", FONT_SIZE
)
ascent, descent = font.getmetrics()
line_h = ascent + descent + 6
char_w = font.getlength("M")

TITLEBAR_H = 34
W = int(PAD_X * 2 + COLS * char_w)
H = int(TITLEBAR_H + PAD_Y * 2 + ROWS * line_h)


def line_color(text):
    stripped = text.strip()
    if stripped == "OK" or ("Ran " in text and " tests in " in text):
        return GREEN
    if stripped.startswith(">"):
        return DIM
    if (
        text.startswith("====")
        or text.startswith("----")
        or text.startswith("Wrote ")
        or text.startswith("Ledger rows added")
        or text.startswith("Flags exercised")
        or stripped.startswith("..")
    ):
        return CYAN
    if text.startswith("#"):
        return DIM
    return FG


def render_frame(visible_lines, cursor_on=False, cursor_line_idx=None, cursor_text=""):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, TITLEBAR_H], fill=TITLEBAR)
    for i, c in enumerate((0xFF5F56, 0xFFBD2E, 0x27C93F)):
        draw.ellipse(
            [16 + i * 22, TITLEBAR_H // 2 - 6, 16 + i * 22 + 12, TITLEBAR_H // 2 + 6],
            fill=f"#{c:06x}",
        )
    draw.text(
        (W / 2, TITLEBAR_H / 2),
        "yt-competitor-swipe -- sample run",
        font=font,
        fill=(140, 148, 158),
        anchor="mm",
    )

    y = TITLEBAR_H + PAD_Y
    for idx, raw in enumerate(visible_lines):
        is_prompt = raw.startswith("$ ")
        if is_prompt:
            draw.text((PAD_X, y), "$", font=bold_font, fill=GREEN)
            draw.text((PAD_X + char_w * 2, y), raw[2:], font=bold_font, fill=(230, 237, 243))
        else:
            draw.text((PAD_X, y), raw, font=font, fill=line_color(raw))
        y += line_h

    if cursor_on:
        cy = TITLEBAR_H + PAD_Y + cursor_line_idx * line_h
        cx = PAD_X + char_w * 2 + font.getlength(cursor_text)
        draw.rectangle([cx, cy, cx + char_w * 0.6, cy + line_h - 6], fill=(230, 237, 243))
    return img


def wrap_line(text, width=COLS - 2):
    """Soft-wrap a long captured line for display; never drops or alters characters."""
    if len(text) <= width:
        return [text]
    indent = "   " if not text.startswith(" ") else "     "
    out = [text[:width]]
    rest = text[width:]
    cont_width = width - len(indent)
    while rest:
        out.append(indent + rest[:cont_width])
        rest = rest[cont_width:]
    return out


def build():
    buf = [INTRO, ""]
    frames = []
    durations = []

    def push(cursor=None):
        view = buf[-ROWS:] if len(buf) > ROWS else buf[:] + [""] * (ROWS - len(buf))
        cur_idx = None
        cur_text = ""
        if cursor is not None:
            rel = len(buf) - 1 - (len(buf) - ROWS if len(buf) > ROWS else 0)
            cur_idx = rel
            cur_text = cursor
        frames.append(render_frame(view, cursor is not None, cur_idx, cur_text))

    push()
    durations.append(900)

    for cmd, output in CAPTURES:
        # type the command character by character
        typed = ""
        prompt_prefix = "$ "
        buf.append(prompt_prefix)
        for ch in cmd:
            typed += ch
            buf[-1] = prompt_prefix + typed
            push(cursor=typed)
            durations.append(18)
        push()
        durations.append(500)

        for line in output.split("\n"):
            for physical in wrap_line(line):
                buf.append(physical)
                push()
                durations.append(70)
        buf.append("")
        push()
        durations.append(650)

    # final hold
    durations[-1] = 3200

    return frames, durations


def main():
    frames, durations = build()
    frames[0].save(
        OUT_GIF,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"wrote {OUT_GIF} ({len(frames)} frames, {OUT_GIF.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
