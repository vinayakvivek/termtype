#!/usr/bin/env python3
"""TermType — a Monkeytype-style typing test for your terminal."""

import curses
import json
import math
import os
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

DURATIONS = [15, 30, 60]
DIFFICULTIES = ["easy", "medium", "hard"]
MODES = ["classic", "word rain", "time attack", "quotes"]
DATA_DIR = Path.home() / ".termtype"
HISTORY_FILE = DATA_DIR / "history.json"
QUOTES_CACHE_FILE = DATA_DIR / "quotes_cache.json"
WORDS_FILE = Path(__file__).parent / "words.json"
BUNDLED_QUOTES_FILE = Path(__file__).parent / "quotes.json"

COLOR_CORRECT = 1
COLOR_WRONG = 2
COLOR_CURSOR = 3
COLOR_DIM = 4
COLOR_STAT = 5
COLOR_TITLE = 6
COLOR_GRAPH = 7


# ── Data directory ───────────────────────────────────────────────────

def _init_data_dir():
    """Create ~/.termtype/ and migrate old history file if needed."""
    DATA_DIR.mkdir(exist_ok=True)
    old_history = Path.home() / ".termtype_history.json"
    if old_history.exists() and not HISTORY_FILE.exists():
        old_history.rename(HISTORY_FILE)


# ── Word dictionary ──────────────────────────────────────────────────

_word_cache = {}


def load_words(difficulty="easy"):
    if difficulty in _word_cache:
        return _word_cache[difficulty]
    words = json.loads(WORDS_FILE.read_text())
    for k, v in words.items():
        _word_cache[k] = v
    return _word_cache[difficulty]


# ── Quotes ───────────────────────────────────────────────────────────

_quotes_pool = []


def _fetch_quotes_from_api():
    """Fetch quotes from ZenQuotes API, return list of {text, author}."""
    import urllib.request
    try:
        data = json.loads(urllib.request.urlopen(
            "https://zenquotes.io/api/quotes", timeout=5
        ).read())
        quotes = [{"text": q["q"], "author": q["a"]}
                  for q in data if q.get("q") and q["a"] != "zenquotes.io"
                  and 30 <= len(q["q"]) <= 200]
        return quotes
    except Exception:
        return []


def _load_cached_quotes():
    if QUOTES_CACHE_FILE.exists():
        try:
            return json.loads(QUOTES_CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_quotes_cache(quotes):
    try:
        existing = _load_cached_quotes()
        seen = {q["text"] for q in existing}
        for q in quotes:
            if q["text"] not in seen:
                existing.append(q)
                seen.add(q["text"])
        QUOTES_CACHE_FILE.write_text(json.dumps(existing, indent=2))
    except OSError:
        pass


def load_quotes():
    """Load quotes: try API (and cache), fall back to cache, then bundled."""
    global _quotes_pool
    if _quotes_pool:
        return _quotes_pool

    # Try API first
    fresh = _fetch_quotes_from_api()
    if fresh:
        _save_quotes_cache(fresh)

    # Build pool from cache (includes fresh + previously cached)
    pool = _load_cached_quotes()

    # Fall back to bundled if nothing cached
    if not pool:
        try:
            pool = json.loads(BUNDLED_QUOTES_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pool = [{"text": "The quick brown fox jumps over the lazy dog.", "author": "Unknown"}]

    _quotes_pool = pool
    return _quotes_pool


def get_random_quote():
    quotes = load_quotes()
    return random.choice(quotes)


# ── History persistence ──────────────────────────────────────────────

def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_result(wpm, accuracy, duration, difficulty="easy", mode="classic"):
    history = load_history()
    history.append({
        "wpm": wpm,
        "accuracy": accuracy,
        "duration": duration,
        "difficulty": difficulty,
        "mode": mode,
        "date": datetime.now().isoformat(),
    })
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def get_stats(history, duration=None):
    """Compute aggregate stats, optionally filtered by duration."""
    entries = history if duration is None else [e for e in history if e["duration"] == duration]
    if not entries:
        return None
    wpms = [e["wpm"] for e in entries]
    accs = [e["accuracy"] for e in entries]
    last10 = wpms[-10:]
    return {
        "total": len(entries),
        "best_wpm": max(wpms),
        "avg_wpm": round(sum(wpms) / len(wpms), 1),
        "avg_acc": round(sum(accs) / len(accs), 1),
        "last10_avg": round(sum(last10) / len(last10), 1),
        "trend": last10,
        "recent": entries[-10:],
    }


# ── Drawing helpers ──────────────────────────────────────────────────

def generate_text(difficulty="easy", count=60):
    words = load_words(difficulty)
    return " ".join(random.choice(words) for _ in range(count))


def draw_timer(win, remaining, duration, y, x):
    win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    win.addstr(y, x, f" {remaining}s ")
    win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)


def draw_text(win, text, typed, cursor_pos, start_y, start_x, max_w):
    line_w = max_w - start_x

    # Pre-compute (row, col) for each character using word-level wrapping.
    positions = []
    row = start_y
    col = start_x
    words = text.split(" ")
    for wi, word in enumerate(words):
        if wi > 0:
            # Space + upcoming word must fit on this line
            needed = 1 + len(word)
            if col - start_x + needed > line_w:
                # Wrap: place space at end of current line (invisible),
                # then start word on next line
                positions.append((row, col))
                row += 1
                col = start_x
            else:
                # space character on same line
                positions.append((row, col))
                col += 1
        # Word characters
        for ch in word:
            positions.append((row, col))
            col += 1

    for i, ch in enumerate(text):
        if i >= len(positions):
            break
        r, c = positions[i]

        if i < len(typed):
            if typed[i] == ch:
                attr = curses.color_pair(COLOR_CORRECT) | curses.A_BOLD
            else:
                attr = curses.color_pair(COLOR_WRONG) | curses.A_BOLD
        elif i == cursor_pos:
            attr = curses.color_pair(COLOR_CURSOR) | curses.A_UNDERLINE
        else:
            attr = curses.color_pair(COLOR_DIM)

        try:
            win.addch(r, c, ch, attr)
        except curses.error:
            pass


def calc_wpm(typed, text, elapsed):
    if elapsed <= 0:
        return 0, 0
    correct_chars = sum(1 for i in range(len(typed)) if i < len(text) and typed[i] == text[i])
    total = len(typed)
    wpm = (correct_chars / 5) / (elapsed / 60)
    accuracy = (correct_chars / total * 100) if total > 0 else 0
    return round(wpm), round(accuracy, 1)


def draw_live_stats(win, wpm, accuracy, y, x):
    win.attron(curses.color_pair(COLOR_STAT) | curses.A_BOLD)
    win.addstr(y, x, f"wpm: {wpm}")
    win.attroff(curses.color_pair(COLOR_STAT) | curses.A_BOLD)
    win.addstr(y, x + 12, f"acc: {accuracy}%", curses.color_pair(COLOR_DIM))


# ── Braille line graph ───────────────────────────────────────────────

# Braille dot offsets: [col][row] -> bit
_BRAILLE_MAP = {
    (0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (0, 3): 0x40,
    (1, 0): 0x08, (1, 1): 0x10, (1, 2): 0x20, (1, 3): 0x80,
}


def _draw_line_graph(win, data_points, graph_y, graph_x, char_w, char_h, color):
    """Draw a braille-character line graph.

    data_points: list of (label, value) — plotted left to right.
    char_w/char_h: size of graph area in terminal characters.
    Each braille char = 2 pixel cols × 4 pixel rows.
    """
    if len(data_points) < 2:
        return

    values = [v for _, v in data_points]
    lo = min(values)
    hi = max(values)
    if lo == hi:
        lo -= 1
        hi += 1

    px_w = char_w * 2
    px_h = char_h * 4

    # Init canvas
    canvas = [[0] * char_w for _ in range(char_h)]

    def set_pixel(px, py):
        if px < 0 or px >= px_w or py < 0 or py >= px_h:
            return
        cy, cx = py // 4, px // 2
        dy, dx = py % 4, px % 2
        canvas[cy][cx] |= _BRAILLE_MAP[(dx, dy)]

    # Map data to pixel coordinates
    n = len(values)
    coords = []
    for i, v in enumerate(values):
        px = int(i / (n - 1) * (px_w - 1)) if n > 1 else 0
        py = int((1 - (v - lo) / (hi - lo)) * (px_h - 1))
        coords.append((px, py))

    # Draw lines between consecutive points (Bresenham)
    for i in range(len(coords) - 1):
        x0, y0 = coords[i]
        x1, y1 = coords[i + 1]
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            set_pixel(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    # Render canvas
    for r in range(char_h):
        for c in range(char_w):
            ch = chr(0x2800 + canvas[r][c])
            try:
                win.addstr(graph_y + r, graph_x + c, ch, curses.color_pair(color) | curses.A_BOLD)
            except curses.error:
                pass

    # Y-axis labels
    for i in range(5):
        val = lo + (hi - lo) * (1 - i / 4)
        label = f"{int(val):>3}"
        row = graph_y + int(i / 4 * (char_h - 1))
        try:
            win.addstr(row, graph_x - 4, label, curses.color_pair(COLOR_DIM))
        except curses.error:
            pass

    # Y-axis line
    for r in range(char_h):
        try:
            win.addstr(graph_y + r, graph_x - 1, "│", curses.color_pair(COLOR_DIM))
        except curses.error:
            pass

    # X-axis line
    try:
        win.addstr(graph_y + char_h, graph_x - 1, "└" + "─" * char_w, curses.color_pair(COLOR_DIM))
    except curses.error:
        pass

    # X-axis labels (spread evenly, max ~6)
    labels = [l for l, _ in data_points]
    max_labels = min(6, len(labels))
    if max_labels >= 2:
        for i in range(max_labels):
            idx = int(i / (max_labels - 1) * (len(labels) - 1))
            lbl = labels[idx]
            col = graph_x + int(idx / (len(labels) - 1) * (char_w - 1)) if len(labels) > 1 else graph_x
            try:
                win.addstr(graph_y + char_h + 1, max(graph_x, col - len(lbl) // 2), lbl, curses.color_pair(COLOR_DIM))
            except curses.error:
                pass


PERIODS = [
    ("week", timedelta(days=7)),
    ("month", timedelta(days=30)),
    ("year", timedelta(days=365)),
    ("all", None),
]


def _filter_history(history, period_delta):
    """Filter history entries to a time period, return list."""
    if period_delta is None:
        return history
    cutoff = datetime.now() - period_delta
    return [e for e in history if datetime.fromisoformat(e["date"]) >= cutoff]


def _date_label(iso_str, period_name):
    """Format a date for x-axis based on period granularity."""
    dt = datetime.fromisoformat(iso_str)
    if period_name == "week":
        return dt.strftime("%a")        # Mon, Tue, ...
    if period_name == "month":
        return dt.strftime("%d %b")     # 05 Mar
    if period_name == "year":
        return dt.strftime("%b %d")     # Mar 05
    return dt.strftime("%b %d")         # Mar 05


# ── Screens ──────────────────────────────────────────────────────────

def _draw_selector(win, items, selected, y, w, active=True):
    """Draw a horizontal selector row, return nothing."""
    total_w = sum(len(f" {item} ") for item in items) + (len(items) - 1) * 2
    sx = w // 2 - total_w // 2
    for i, item in enumerate(items):
        label = f" {item} "
        if i == selected and active:
            win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD | curses.A_REVERSE)
            win.addstr(y, sx, label)
            win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD | curses.A_REVERSE)
        elif i == selected and not active:
            win.addstr(y, sx, label, curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        else:
            win.addstr(y, sx, label, curses.color_pair(COLOR_DIM))
        sx += len(label) + 2


def draw_menu(win, sel_mode, sel_dur, sel_diff, menu_row, h, w, history):
    win.clear()
    title = "termtype"
    cy = h // 2 - 6
    win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    win.addstr(cy, w // 2 - len(title) // 2, title)
    win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

    # Mode row
    mode_label = "mode"
    win.addstr(cy + 2, w // 2 - len(mode_label) // 2, mode_label, curses.color_pair(COLOR_DIM))
    _draw_selector(win, MODES, sel_mode, cy + 3, w, active=(menu_row == 0))

    mode = MODES[sel_mode]
    show_duration = mode in ("classic",)
    show_difficulty = mode in ("classic", "word rain", "time attack")

    # Duration row (only for classic)
    row = cy + 5
    if show_duration:
        dur_label = "duration"
        win.addstr(row, w // 2 - len(dur_label) // 2, dur_label, curses.color_pair(COLOR_DIM))
        dur_items = [f"{d}s" for d in DURATIONS]
        _draw_selector(win, dur_items, sel_dur, row + 1, w, active=(menu_row == 1))
        row += 3

    # Difficulty row
    if show_difficulty:
        diff_label = "difficulty"
        win.addstr(row, w // 2 - len(diff_label) // 2, diff_label, curses.color_pair(COLOR_DIM))
        diff_row_idx = 2 if show_duration else 1
        _draw_selector(win, DIFFICULTIES, sel_diff, row + 1, w, active=(menu_row == diff_row_idx))
        row += 3

    # Personal bests (classic mode)
    if mode == "classic" and show_difficulty:
        difficulty = DIFFICULTIES[sel_diff]
        filtered = [e for e in history if e.get("difficulty", "easy") == difficulty
                    and e.get("mode", "classic") == "classic"]
        if filtered:
            pb_parts = []
            for d in DURATIONS:
                stats = get_stats(filtered, d)
                if stats:
                    pb_parts.append(f"{d}s: {stats['best_wpm']} wpm")
                else:
                    pb_parts.append(f"{d}s: --")
            pb_line = "pb  " + "  |  ".join(pb_parts)
            win.addstr(row, w // 2 - len(pb_line) // 2, "pb  ", curses.color_pair(COLOR_STAT) | curses.A_BOLD)
            win.addstr(row, w // 2 - len(pb_line) // 2 + 4, "  |  ".join(pb_parts), curses.color_pair(COLOR_DIM))

    hint = "← → select · ↑ ↓ row · enter start · s stats · q quit"
    win.addstr(h - 2, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
    win.refresh()


def draw_results(win, wpm, accuracy, duration, difficulty, h, w, history):
    win.clear()
    title = "results"
    win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    win.addstr(h // 2 - 4, w // 2 - len(title) // 2, title)
    win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

    wpm_str = f"wpm: {wpm}"
    acc_str = f"accuracy: {accuracy}%"
    dur_str = f"{duration}s · {difficulty}"

    win.attron(curses.color_pair(COLOR_STAT) | curses.A_BOLD)
    win.addstr(h // 2 - 1, w // 2 - len(wpm_str) // 2, wpm_str)
    win.attroff(curses.color_pair(COLOR_STAT) | curses.A_BOLD)
    win.addstr(h // 2, w // 2 - len(acc_str) // 2, acc_str, curses.color_pair(COLOR_DIM))
    win.addstr(h // 2 + 1, w // 2 - len(dur_str) // 2, dur_str, curses.color_pair(COLOR_DIM))

    # Compare to personal best (same difficulty)
    filtered = [e for e in history if e.get("difficulty", "easy") == difficulty]
    stats = get_stats(filtered, duration)
    if stats:
        if wpm >= stats["best_wpm"]:
            badge = "new personal best!"
            win.addstr(h // 2 + 3, w // 2 - len(badge) // 2, badge,
                       curses.color_pair(COLOR_STAT) | curses.A_BOLD)
        else:
            diff = wpm - stats["best_wpm"]
            cmp_str = f"pb: {stats['best_wpm']} wpm ({diff:+d})"
            win.addstr(h // 2 + 3, w // 2 - len(cmp_str) // 2, cmp_str, curses.color_pair(COLOR_DIM))

    hint = "enter retry · tab menu · s stats · q quit"
    win.addstr(h // 2 + 6, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
    win.refresh()


def _render_stats(win, history, h, w, period_idx, scroll):
    """Render the full stats screen (called each frame of the stats loop)."""
    win.clear()
    title = "stats & progress"
    win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    win.addstr(1, w // 2 - len(title) // 2, title)
    win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

    if not history:
        msg = "no history yet — complete a test first!"
        win.addstr(h // 2, w // 2 - len(msg) // 2, msg, curses.color_pair(COLOR_DIM))
        hint = "esc/q to go back"
        win.addstr(h - 2, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
        win.refresh()
        return

    period_name, period_delta = PERIODS[period_idx]
    filtered = _filter_history(history, period_delta)

    pad_x = max(6, (w - 76) // 2)
    row = 3

    # ── Period tabs ──
    tab_x = pad_x
    for i, (pname, _) in enumerate(PERIODS):
        label = f" {pname} "
        if i == period_idx:
            win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD | curses.A_REVERSE)
            win.addstr(row, tab_x, label)
            win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD | curses.A_REVERSE)
        else:
            win.addstr(row, tab_x, label, curses.color_pair(COLOR_DIM))
        tab_x += len(label) + 1
    row += 2

    # ── Summary for period ──
    stats = get_stats(filtered)
    if stats:
        win.addstr(row, pad_x,
                   f"tests: {stats['total']}   "
                   f"best: {stats['best_wpm']} wpm   "
                   f"avg: {stats['avg_wpm']} wpm   "
                   f"acc: {stats['avg_acc']}%   "
                   f"L10 avg: {stats['last10_avg']} wpm",
                   curses.color_pair(COLOR_DIM))
    else:
        win.addstr(row, pad_x, "no tests in this period", curses.color_pair(COLOR_DIM))
    row += 2

    # ── Line graph ──
    graph_w = min(60, w - pad_x - 8)
    graph_h = min(12, h - row - 14)
    if graph_h >= 4 and graph_w >= 10 and filtered:
        data_points = [(_date_label(e["date"], period_name), e["wpm"]) for e in filtered]
        win.addstr(row - 1, pad_x, "wpm", curses.color_pair(COLOR_STAT) | curses.A_BOLD)
        _draw_line_graph(win, data_points, row, pad_x + 4, graph_w, graph_h, COLOR_GRAPH)
        row += graph_h + 3
    elif not filtered:
        row += 1

    # ── Per-duration breakdown ──
    row += 1
    for dur in DURATIONS:
        dur_entries = [e for e in filtered if e["duration"] == dur]
        dur_stats = get_stats(dur_entries)
        if not dur_stats:
            continue
        if row >= h - 6:
            break
        label = f"{dur}s"
        win.addstr(row, pad_x, label, curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        win.addstr(row, pad_x + 5,
                   f"tests: {dur_stats['total']}   "
                   f"best: {dur_stats['best_wpm']}   "
                   f"avg: {dur_stats['avg_wpm']}   "
                   f"acc: {dur_stats['avg_acc']}%",
                   curses.color_pair(COLOR_DIM))
        row += 1

    # ── Recent history table ──
    row += 1
    if row < h - 4 and filtered:
        win.addstr(row, pad_x, "recent tests", curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        row += 1
        header = f"{'date':<20} {'dur':>4} {'wpm':>5} {'acc':>7}"
        win.addstr(row, pad_x, header, curses.color_pair(COLOR_DIM) | curses.A_UNDERLINE)
        row += 1

        visible = filtered[-(h - row - 2):]
        for entry in reversed(visible):
            if row >= h - 3:
                break
            dt = entry["date"][:16].replace("T", " ")
            line = f"{dt:<20} {entry['duration']:>3}s {entry['wpm']:>5} {entry['accuracy']:>6}%"
            dur_best = get_stats(filtered, entry["duration"])
            if dur_best and entry["wpm"] == dur_best["best_wpm"]:
                win.addstr(row, pad_x, line, curses.color_pair(COLOR_STAT))
            else:
                win.addstr(row, pad_x, line, curses.color_pair(COLOR_DIM))
            row += 1

    hint = "← → period · esc/q back"
    win.addstr(h - 2, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
    win.refresh()


def show_stats_screen(win, history):
    """Interactive stats screen with period switching."""
    period_idx = 3  # default: all-time
    scroll = 0
    win.timeout(100)
    while True:
        h, w = win.getmaxyx()
        _render_stats(win, history, h, w, period_idx, scroll)
        key = win.getch()
        if key == -1:
            continue
        if key in (27, ord('q'), ord('Q'), ord('s'), ord('S')):
            return
        if key == curses.KEY_LEFT:
            period_idx = max(0, period_idx - 1)
        elif key == curses.KEY_RIGHT:
            period_idx = min(len(PERIODS) - 1, period_idx + 1)


# ── Classic test runner ──────────────────────────────────────────────

def _build_timeline(keystroke_log, text, duration):
    """Build per-second WPM timeline and error positions from keystroke log.

    keystroke_log: list of (elapsed_seconds, char_index, is_correct)
    Returns: (wpm_timeline, error_times)
        wpm_timeline: list of (second, wpm) for each second
        error_times: list of seconds where errors occurred
    """
    if not keystroke_log:
        return [], []

    # Per-second rolling WPM (correct chars so far / elapsed * 12)
    wpm_timeline = []
    error_times = []
    correct_count = 0
    log_idx = 0

    for sec in range(1, int(duration) + 1):
        while log_idx < len(keystroke_log) and keystroke_log[log_idx][0] <= sec:
            _, _, is_correct = keystroke_log[log_idx]
            if is_correct:
                correct_count += 1
            log_idx += 1
        wpm = (correct_count / 5) / (sec / 60) if sec > 0 else 0
        wpm_timeline.append((sec, round(wpm)))

    for elapsed, _, is_correct in keystroke_log:
        if not is_correct:
            error_times.append(elapsed)

    return wpm_timeline, error_times


def draw_post_test(win, wpm_timeline, error_times, final_wpm, accuracy, duration, h, w):
    """Draw the post-test analysis screen with WPM graph and error markers."""
    win.clear()

    title = "test analysis"
    win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    win.addstr(1, w // 2 - len(title) // 2, title)
    win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

    # Stats line
    stats_str = f"wpm: {final_wpm}   accuracy: {accuracy}%   duration: {duration}s"
    win.addstr(3, w // 2 - len(stats_str) // 2, stats_str, curses.color_pair(COLOR_STAT) | curses.A_BOLD)

    if not wpm_timeline:
        win.refresh()
        return

    # Graph area
    pad_x = max(6, (w - 70) // 2)
    graph_x = pad_x + 5
    graph_w = min(60, w - graph_x - 4)
    graph_h = min(10, h - 12)

    if graph_w < 10 or graph_h < 4:
        win.refresh()
        return

    values = [v for _, v in wpm_timeline]
    data_points = [(f"{s}s", v) for s, v in wpm_timeline]

    win.addstr(5, pad_x, "wpm over time", curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    _draw_line_graph(win, data_points, 6, graph_x, graph_w, graph_h, COLOR_GRAPH)

    # Error markers on X-axis
    if error_times and len(wpm_timeline) > 1:
        axis_y = 6 + graph_h + 1
        for et in error_times:
            # Map error time to graph x position
            col = graph_x + int(et / duration * (graph_w - 1))
            if graph_x <= col < graph_x + graph_w:
                try:
                    win.addstr(axis_y, col, "x", curses.color_pair(COLOR_WRONG) | curses.A_BOLD)
                except curses.error:
                    pass
        # Legend
        legend_y = 6 + graph_h + 3
        win.addstr(legend_y, pad_x, "x", curses.color_pair(COLOR_WRONG) | curses.A_BOLD)
        win.addstr(legend_y, pad_x + 2, f"= error ({len(error_times)} total)", curses.color_pair(COLOR_DIM))

    hint = "enter to continue"
    win.addstr(h - 2, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
    win.refresh()


def run_classic(stdscr, duration, difficulty="easy"):
    text = generate_text(difficulty=difficulty, count=max(80, duration * 3))
    typed = []
    keystroke_log = []  # (elapsed, char_index, is_correct)
    start_time = None

    stdscr.timeout(100)

    while True:
        h, w = stdscr.getmaxyx()
        pad_x = max(2, (w - min(w - 4, 80)) // 2)
        text_w = min(w - 4, 80)

        elapsed = time.time() - start_time if start_time else 0
        remaining = max(0, duration - int(elapsed))

        if start_time and elapsed >= duration:
            wpm, accuracy = calc_wpm(typed, text, duration)
            timeline, errors = _build_timeline(keystroke_log, text, duration)
            return wpm, accuracy, timeline, errors

        stdscr.clear()

        title = "termtype"
        stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        stdscr.addstr(1, w // 2 - len(title) // 2, title)
        stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

        if start_time:
            draw_timer(stdscr, remaining, duration, 1, w // 2 + len(title) // 2 + 2)

        if start_time and len(typed) > 0:
            wpm, accuracy = calc_wpm(typed, text, elapsed)
            draw_live_stats(stdscr, wpm, accuracy, 3, pad_x)

        draw_text(stdscr, text, typed, len(typed), 5, pad_x, pad_x + text_w)

        if not start_time:
            hint = "start typing..."
            stdscr.addstr(h - 2, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
        else:
            hint = "esc to cancel"
            stdscr.addstr(h - 2, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))

        stdscr.refresh()

        try:
            key = stdscr.getch()
        except curses.error:
            continue

        if key == -1:
            continue
        if key == 27:
            return None, None, None, None
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if typed:
                typed.pop()
            continue
        if 32 <= key <= 126:
            if start_time is None:
                start_time = time.time()
            if len(typed) < len(text):
                ch = chr(key)
                idx = len(typed)
                is_correct = ch == text[idx]
                keystroke_log.append((time.time() - start_time, idx, is_correct))
                typed.append(ch)


# ── Word Rain mode ──────────────────────────────────────────────────

def run_word_rain(stdscr, difficulty="easy"):
    """Words fall from top. Type them before they reach the bottom."""
    words_list = load_words(difficulty)
    stdscr.timeout(50)

    active_words = []  # list of {word, x, y (float), typed}
    lives = 3
    score = 0
    start_time = time.time()
    last_spawn = 0
    spawn_interval = 2.0  # seconds between spawns
    fall_speed = 0.15     # rows per frame
    input_buf = ""

    while lives > 0:
        h, w = stdscr.getmaxyx()
        now = time.time()
        elapsed = now - start_time

        # Increase difficulty over time
        fall_speed = 0.15 + elapsed / 300  # gradually faster
        spawn_interval = max(0.8, 2.0 - elapsed / 120)

        # Spawn new word
        if now - last_spawn > spawn_interval:
            word = random.choice(words_list)
            x = random.randint(2, max(3, w - len(word) - 2))
            active_words.append({"word": word, "x": x, "y": 0.0})
            last_spawn = now

        # Move words down
        for aw in active_words:
            aw["y"] += fall_speed

        # Check for words hitting bottom
        fallen = [aw for aw in active_words if aw["y"] >= h - 3]
        for aw in fallen:
            lives -= 1
            active_words.remove(aw)

        # Draw
        stdscr.clear()

        # Header
        header = f" word rain   score: {score}   "
        lives_str = "♥ " * lives + "♡ " * (3 - lives)
        stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        stdscr.addstr(0, 1, header)
        stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        stdscr.addstr(0, len(header) + 1, lives_str.strip(), curses.color_pair(COLOR_WRONG) | curses.A_BOLD)
        time_str = f"{int(elapsed)}s"
        stdscr.addstr(0, w - len(time_str) - 2, time_str, curses.color_pair(COLOR_DIM))

        # Draw falling words
        for aw in active_words:
            row = int(aw["y"])
            if 1 <= row < h - 2:
                word = aw["word"]
                # Highlight matching prefix
                for ci, ch in enumerate(word):
                    if ci < len(input_buf) and word[:len(input_buf)] == input_buf[:len(input_buf)] and ci < len(input_buf) and word.startswith(input_buf):
                        attr = curses.color_pair(COLOR_CORRECT) | curses.A_BOLD
                    else:
                        attr = curses.color_pair(COLOR_CURSOR) | curses.A_BOLD
                    try:
                        win_x = aw["x"] + ci
                        if win_x < w:
                            stdscr.addch(row, win_x, ch, attr)
                    except curses.error:
                        pass

        # Input line
        input_line = f"> {input_buf}_"
        stdscr.addstr(h - 2, 1, input_line, curses.color_pair(COLOR_STAT) | curses.A_BOLD)

        hint = "type words to destroy them · esc to quit"
        stdscr.addstr(h - 1, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))

        stdscr.refresh()

        try:
            key = stdscr.getch()
        except curses.error:
            continue

        if key == -1:
            continue
        if key == 27:
            return None, None
        if key in (curses.KEY_BACKSPACE, 127, 8):
            input_buf = input_buf[:-1]
            continue

        if 32 <= key <= 126:
            input_buf += chr(key)

            # Check if input matches any active word
            matched = None
            for aw in active_words:
                if aw["word"] == input_buf:
                    matched = aw
                    break
            if matched:
                active_words.remove(matched)
                score += len(matched["word"])
                input_buf = ""

    # Game over
    elapsed = time.time() - start_time
    return score, round(elapsed, 1)


def draw_word_rain_results(win, score, time_survived, h, w):
    win.clear()
    title = "game over"
    win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    win.addstr(h // 2 - 3, w // 2 - len(title) // 2, title)
    win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

    score_str = f"score: {score}"
    time_str = f"survived: {time_survived}s"
    win.attron(curses.color_pair(COLOR_STAT) | curses.A_BOLD)
    win.addstr(h // 2, w // 2 - len(score_str) // 2, score_str)
    win.attroff(curses.color_pair(COLOR_STAT) | curses.A_BOLD)
    win.addstr(h // 2 + 1, w // 2 - len(time_str) // 2, time_str, curses.color_pair(COLOR_DIM))

    hint = "enter retry · tab menu · q quit"
    win.addstr(h // 2 + 5, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
    win.refresh()


# ── Time Attack mode ────────────────────────────────────────────────

def run_time_attack(stdscr, difficulty="easy"):
    """Type words to gain time. Mistakes cost time. Survive as long as you can."""
    words_list = load_words(difficulty)
    stdscr.timeout(50)

    time_left = 10.0
    score = 0
    words_typed = 0
    current_word = random.choice(words_list)
    input_buf = ""
    last_tick = time.time()
    start_time = last_tick

    while time_left > 0:
        h, w = stdscr.getmaxyx()
        now = time.time()
        dt = now - last_tick
        last_tick = now
        time_left -= dt

        if time_left <= 0:
            break

        stdscr.clear()

        # Header
        title = "time attack"
        stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        stdscr.addstr(1, w // 2 - len(title) // 2, title)
        stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

        # Timer bar
        bar_w = min(40, w - 10)
        bar_x = w // 2 - bar_w // 2
        filled = max(0, min(bar_w, int(time_left / 15 * bar_w)))
        empty = bar_w - filled
        timer_color = COLOR_CORRECT if time_left > 5 else COLOR_WRONG
        try:
            if filled > 0:
                stdscr.addstr(3, bar_x, "█" * filled, curses.color_pair(timer_color) | curses.A_BOLD)
            if empty > 0:
                stdscr.addstr(3, bar_x + filled, "░" * empty, curses.color_pair(COLOR_DIM))
        except curses.error:
            pass
        timer_str = f" {time_left:.1f}s"
        stdscr.addstr(3, bar_x + bar_w + 1, timer_str, curses.color_pair(COLOR_STAT) | curses.A_BOLD)

        # Score
        score_str = f"score: {score}   words: {words_typed}"
        stdscr.addstr(5, w // 2 - len(score_str) // 2, score_str, curses.color_pair(COLOR_DIM))

        # Current word (large, centered)
        word_x = w // 2 - len(current_word) // 2
        for ci, ch in enumerate(current_word):
            if ci < len(input_buf):
                if input_buf[ci] == ch:
                    attr = curses.color_pair(COLOR_CORRECT) | curses.A_BOLD
                else:
                    attr = curses.color_pair(COLOR_WRONG) | curses.A_BOLD
            else:
                attr = curses.color_pair(COLOR_DIM) | curses.A_BOLD
            try:
                stdscr.addch(h // 2, word_x + ci, ch, attr)
            except curses.error:
                pass

        # Input below
        cursor = f"> {input_buf}_"
        stdscr.addstr(h // 2 + 2, w // 2 - len(cursor) // 2, cursor, curses.color_pair(COLOR_STAT))

        # Bonuses info
        info = "+2s correct   -1s wrong"
        stdscr.addstr(h - 3, w // 2 - len(info) // 2, info, curses.color_pair(COLOR_DIM))
        hint = "esc to quit"
        stdscr.addstr(h - 2, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))

        stdscr.refresh()

        try:
            key = stdscr.getch()
        except curses.error:
            continue

        if key == -1:
            continue
        if key == 27:
            return None, None
        if key in (curses.KEY_BACKSPACE, 127, 8):
            input_buf = input_buf[:-1]
            continue

        if 32 <= key <= 126:
            input_buf += chr(key)

            if len(input_buf) == len(current_word):
                if input_buf == current_word:
                    score += len(current_word)
                    time_left += 2.0
                    words_typed += 1
                else:
                    time_left -= 1.0
                input_buf = ""
                current_word = random.choice(words_list)

    elapsed = time.time() - start_time
    return score, words_typed


def draw_time_attack_results(win, score, words_typed, h, w):
    win.clear()
    title = "time's up!"
    win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    win.addstr(h // 2 - 3, w // 2 - len(title) // 2, title)
    win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

    score_str = f"score: {score}"
    words_str = f"words: {words_typed}"
    win.attron(curses.color_pair(COLOR_STAT) | curses.A_BOLD)
    win.addstr(h // 2, w // 2 - len(score_str) // 2, score_str)
    win.attroff(curses.color_pair(COLOR_STAT) | curses.A_BOLD)
    win.addstr(h // 2 + 1, w // 2 - len(words_str) // 2, words_str, curses.color_pair(COLOR_DIM))

    hint = "enter retry · tab menu · q quit"
    win.addstr(h // 2 + 5, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
    win.refresh()


# ── Quote Mode ──────────────────────────────────────────────────────

def run_quotes(stdscr):
    """Type real quotes. Shows author after completion."""
    quote = get_random_quote()
    text = quote["text"]
    author = quote["author"]
    typed = []
    start_time = None

    stdscr.timeout(100)

    while True:
        h, w = stdscr.getmaxyx()
        pad_x = max(2, (w - min(w - 4, 80)) // 2)
        text_w = min(w - 4, 80)

        elapsed = time.time() - start_time if start_time else 0

        # Check if done
        if len(typed) == len(text):
            wpm, accuracy = calc_wpm(typed, text, elapsed)
            return wpm, accuracy, author

        stdscr.clear()

        title = "quotes"
        stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        stdscr.addstr(1, w // 2 - len(title) // 2, title)
        stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

        if start_time:
            time_str = f" {int(elapsed)}s"
            stdscr.addstr(1, w // 2 + len(title) // 2 + 2, time_str, curses.color_pair(COLOR_DIM))

        if start_time and len(typed) > 0:
            wpm, accuracy = calc_wpm(typed, text, elapsed)
            draw_live_stats(stdscr, wpm, accuracy, 3, pad_x)

        draw_text(stdscr, text, typed, len(typed), 5, pad_x, pad_x + text_w)

        if not start_time:
            hint = "start typing..."
            stdscr.addstr(h - 2, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
        else:
            hint = "esc to cancel"
            stdscr.addstr(h - 2, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))

        stdscr.refresh()

        try:
            key = stdscr.getch()
        except curses.error:
            continue

        if key == -1:
            continue
        if key == 27:
            return None, None, None
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if typed:
                typed.pop()
            continue
        if 32 <= key <= 126:
            if start_time is None:
                start_time = time.time()
            if len(typed) < len(text):
                typed.append(chr(key))


def draw_quote_results(win, wpm, accuracy, author, h, w):
    win.clear()
    title = "done!"
    win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    win.addstr(h // 2 - 4, w // 2 - len(title) // 2, title)
    win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

    wpm_str = f"wpm: {wpm}"
    acc_str = f"accuracy: {accuracy}%"
    author_str = f"— {author}"

    win.attron(curses.color_pair(COLOR_STAT) | curses.A_BOLD)
    win.addstr(h // 2 - 1, w // 2 - len(wpm_str) // 2, wpm_str)
    win.attroff(curses.color_pair(COLOR_STAT) | curses.A_BOLD)
    win.addstr(h // 2, w // 2 - len(acc_str) // 2, acc_str, curses.color_pair(COLOR_DIM))
    win.addstr(h // 2 + 2, w // 2 - len(author_str) // 2, author_str,
               curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

    hint = "enter next quote · tab menu · q quit"
    win.addstr(h // 2 + 6, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
    win.refresh()


# ── Main loop ────────────────────────────────────────────────────────

def main(stdscr):
    _init_data_dir()
    curses.curs_set(0)
    curses.use_default_colors()
    curses.init_pair(COLOR_CORRECT, curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_WRONG, curses.COLOR_RED, -1)
    curses.init_pair(COLOR_CURSOR, curses.COLOR_WHITE, -1)
    curses.init_pair(COLOR_DIM, 240, -1)
    curses.init_pair(COLOR_STAT, curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_TITLE, curses.COLOR_CYAN, -1)
    curses.init_pair(COLOR_GRAPH, curses.COLOR_MAGENTA, -1)

    sel_mode = 0   # default classic
    sel_dur = 1    # default 30s
    sel_diff = 0   # default easy
    menu_row = 0   # 0 = mode, 1 = duration (if shown), 2 = difficulty (if shown)
    stdscr.timeout(100)

    while True:
        h, w = stdscr.getmaxyx()
        history = load_history()
        mode = MODES[sel_mode]

        # How many menu rows for this mode
        show_duration = mode in ("classic",)
        show_difficulty = mode in ("classic", "word rain", "time attack")
        max_rows = 1 + (1 if show_duration else 0) + (1 if show_difficulty else 0)

        # --- MENU ---
        draw_menu(stdscr, sel_mode, sel_dur, sel_diff, menu_row, h, w, history)
        key = stdscr.getch()
        if key == -1:
            continue
        if key in (ord('q'), ord('Q')):
            return
        if key in (ord('s'), ord('S')):
            show_stats_screen(stdscr, history)
            stdscr.timeout(100)
            continue
        if key == curses.KEY_UP:
            menu_row = max(0, menu_row - 1)
            continue
        if key == curses.KEY_DOWN:
            menu_row = min(max_rows - 1, menu_row + 1)
            continue
        if key == curses.KEY_LEFT:
            if menu_row == 0:
                sel_mode = max(0, sel_mode - 1)
                menu_row = 0  # reset when mode changes
            elif menu_row == 1 and show_duration:
                sel_dur = max(0, sel_dur - 1)
            else:
                sel_diff = max(0, sel_diff - 1)
            continue
        if key == curses.KEY_RIGHT:
            if menu_row == 0:
                sel_mode = min(len(MODES) - 1, sel_mode + 1)
                menu_row = 0
            elif menu_row == 1 and show_duration:
                sel_dur = min(len(DURATIONS) - 1, sel_dur + 1)
            else:
                sel_diff = min(len(DIFFICULTIES) - 1, sel_diff + 1)
            continue
        if key not in (curses.KEY_ENTER, 10, 13):
            continue

        duration = DURATIONS[sel_dur]
        difficulty = DIFFICULTIES[sel_diff]

        # --- RUN SELECTED MODE ---
        if mode == "classic":
            result = run_classic(stdscr, duration, difficulty)
            if result[0] is None:
                continue
            wpm, accuracy, timeline, errors = result
            save_result(wpm, accuracy, duration, difficulty)
            history = load_history()

            # Post-test analysis screen
            stdscr.timeout(-1)
            h, w = stdscr.getmaxyx()
            draw_post_test(stdscr, timeline, errors, wpm, accuracy, duration, h, w)
            curses.flushinp()  # discard buffered keypresses from typing
            stdscr.getch()

            # Results loop
            while True:
                h, w = stdscr.getmaxyx()
                draw_results(stdscr, wpm, accuracy, duration, difficulty, h, w, history)
                key = stdscr.getch()
                if key in (ord('q'), ord('Q')):
                    return
                if key in (ord('s'), ord('S')):
                    show_stats_screen(stdscr, history)
                    stdscr.timeout(-1)
                    continue
                if key in (curses.KEY_ENTER, 10, 13):
                    stdscr.timeout(100)
                    result = run_classic(stdscr, duration, difficulty)
                    if result[0] is None:
                        break
                    wpm, accuracy, timeline, errors = result
                    save_result(wpm, accuracy, duration, difficulty)
                    history = load_history()
                    stdscr.timeout(-1)
                    h, w = stdscr.getmaxyx()
                    draw_post_test(stdscr, timeline, errors, wpm, accuracy, duration, h, w)
                    stdscr.getch()
                    continue
                if key == 9:
                    stdscr.timeout(100)
                    break

        elif mode == "word rain":
            result = run_word_rain(stdscr, difficulty)
            if result[0] is None:
                continue
            score, time_survived = result

            stdscr.timeout(-1)
            while True:
                h, w = stdscr.getmaxyx()
                draw_word_rain_results(stdscr, score, time_survived, h, w)
                key = stdscr.getch()
                if key in (ord('q'), ord('Q')):
                    return
                if key in (curses.KEY_ENTER, 10, 13):
                    stdscr.timeout(50)
                    result = run_word_rain(stdscr, difficulty)
                    if result[0] is None:
                        break
                    score, time_survived = result
                    stdscr.timeout(-1)
                    continue
                if key == 9:
                    stdscr.timeout(100)
                    break

        elif mode == "time attack":
            result = run_time_attack(stdscr, difficulty)
            if result[0] is None:
                continue
            score, words_typed = result

            stdscr.timeout(-1)
            while True:
                h, w = stdscr.getmaxyx()
                draw_time_attack_results(stdscr, score, words_typed, h, w)
                key = stdscr.getch()
                if key in (ord('q'), ord('Q')):
                    return
                if key in (curses.KEY_ENTER, 10, 13):
                    stdscr.timeout(50)
                    result = run_time_attack(stdscr, difficulty)
                    if result[0] is None:
                        break
                    score, words_typed = result
                    stdscr.timeout(-1)
                    continue
                if key == 9:
                    stdscr.timeout(100)
                    break

        elif mode == "quotes":
            result = run_quotes(stdscr)
            if result[0] is None:
                continue
            wpm, accuracy, author = result

            stdscr.timeout(-1)
            while True:
                h, w = stdscr.getmaxyx()
                draw_quote_results(stdscr, wpm, accuracy, author, h, w)
                key = stdscr.getch()
                if key in (ord('q'), ord('Q')):
                    return
                if key in (curses.KEY_ENTER, 10, 13):
                    stdscr.timeout(100)
                    result = run_quotes(stdscr)
                    if result[0] is None:
                        break
                    wpm, accuracy, author = result
                    stdscr.timeout(-1)
                    continue
                if key == 9:
                    stdscr.timeout(100)
                    break


def cli():
    curses.wrapper(main)


if __name__ == "__main__":
    cli()
