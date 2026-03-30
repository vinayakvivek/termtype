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
HISTORY_FILE = Path.home() / ".termtype_history.json"
WORDS_FILE = Path(__file__).parent / "words.json"

COLOR_CORRECT = 1
COLOR_WRONG = 2
COLOR_CURSOR = 3
COLOR_DIM = 4
COLOR_STAT = 5
COLOR_TITLE = 6
COLOR_GRAPH = 7


# ── Word dictionary ──────────────────────────────────────────────────

_word_cache = {}


def load_words(difficulty="easy"):
    if difficulty in _word_cache:
        return _word_cache[difficulty]
    words = json.loads(WORDS_FILE.read_text())
    for k, v in words.items():
        _word_cache[k] = v
    return _word_cache[difficulty]


# ── History persistence ──────────────────────────────────────────────

def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_result(wpm, accuracy, duration, difficulty="easy"):
    history = load_history()
    history.append({
        "wpm": wpm,
        "accuracy": accuracy,
        "duration": duration,
        "difficulty": difficulty,
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
        return dt.strftime("%a")      # Mon, Tue, ...
    if period_name == "month":
        return dt.strftime("%d %b")   # 05 Mar
    if period_name == "year":
        return dt.strftime("%b")      # Mar
    return dt.strftime("%b %y")       # Mar 25


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


def draw_menu(win, sel_dur, sel_diff, menu_row, h, w, history):
    win.clear()
    title = "termtype"
    win.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    win.addstr(h // 2 - 5, w // 2 - len(title) // 2, title)
    win.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

    # Duration row
    dur_label = "duration"
    win.addstr(h // 2 - 3, w // 2 - len(dur_label) // 2, dur_label, curses.color_pair(COLOR_DIM))
    dur_items = [f"{d}s" for d in DURATIONS]
    _draw_selector(win, dur_items, sel_dur, h // 2 - 2, w, active=(menu_row == 0))

    # Difficulty row
    diff_label = "difficulty"
    win.addstr(h // 2, w // 2 - len(diff_label) // 2, diff_label, curses.color_pair(COLOR_DIM))
    _draw_selector(win, DIFFICULTIES, sel_diff, h // 2 + 1, w, active=(menu_row == 1))

    # Show quick personal best for each duration at current difficulty
    difficulty = DIFFICULTIES[sel_diff]
    filtered = [e for e in history if e.get("difficulty", "easy") == difficulty]
    if filtered:
        pb_y = h // 2 + 3
        pb_parts = []
        for d in DURATIONS:
            stats = get_stats(filtered, d)
            if stats:
                pb_parts.append(f"{d}s: {stats['best_wpm']} wpm")
            else:
                pb_parts.append(f"{d}s: --")
        pb_line = "pb  " + "  |  ".join(pb_parts)
        win.addstr(pb_y, w // 2 - len(pb_line) // 2, "pb  ", curses.color_pair(COLOR_STAT) | curses.A_BOLD)
        win.addstr(pb_y, w // 2 - len(pb_line) // 2 + 4, "  |  ".join(pb_parts), curses.color_pair(COLOR_DIM))

    hint = "← → select · ↑ ↓ row · enter start · s stats · q quit"
    win.addstr(h // 2 + 6, w // 2 - len(hint) // 2, hint, curses.color_pair(COLOR_DIM))
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


# ── Test runner ──────────────────────────────────────────────────────

def run_test(stdscr, duration, difficulty="easy"):
    text = generate_text(difficulty=difficulty, count=max(80, duration * 3))
    typed = []
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
            return wpm, accuracy

        stdscr.clear()

        # Title
        title = "termtype"
        stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        stdscr.addstr(1, w // 2 - len(title) // 2, title)
        stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

        # Timer
        if start_time:
            draw_timer(stdscr, remaining, duration, 1, w // 2 + len(title) // 2 + 2)

        # Live stats
        if start_time and len(typed) > 0:
            wpm, accuracy = calc_wpm(typed, text, elapsed)
            draw_live_stats(stdscr, wpm, accuracy, 3, pad_x)

        # Text area
        draw_text(stdscr, text, typed, len(typed), 5, pad_x, pad_x + text_w)

        # Hint
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

        if key == 27:  # ESC
            return None, None

        if key in (curses.KEY_BACKSPACE, 127, 8):
            if typed:
                typed.pop()
            continue

        if 32 <= key <= 126:
            if start_time is None:
                start_time = time.time()
            if len(typed) < len(text):
                typed.append(chr(key))


# ── Main loop ────────────────────────────────────────────────────────

def main(stdscr):
    curses.curs_set(0)
    curses.use_default_colors()
    curses.init_pair(COLOR_CORRECT, curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_WRONG, curses.COLOR_RED, -1)
    curses.init_pair(COLOR_CURSOR, curses.COLOR_WHITE, -1)
    curses.init_pair(COLOR_DIM, 240, -1)
    curses.init_pair(COLOR_STAT, curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_TITLE, curses.COLOR_CYAN, -1)
    curses.init_pair(COLOR_GRAPH, curses.COLOR_MAGENTA, -1)

    sel_dur = 1    # default 30s
    sel_diff = 0   # default easy
    menu_row = 0   # 0 = duration row, 1 = difficulty row
    stdscr.timeout(100)

    while True:
        h, w = stdscr.getmaxyx()
        history = load_history()

        # --- MENU ---
        draw_menu(stdscr, sel_dur, sel_diff, menu_row, h, w, history)
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
            menu_row = min(1, menu_row + 1)
            continue
        if key == curses.KEY_LEFT:
            if menu_row == 0:
                sel_dur = max(0, sel_dur - 1)
            else:
                sel_diff = max(0, sel_diff - 1)
            continue
        if key == curses.KEY_RIGHT:
            if menu_row == 0:
                sel_dur = min(len(DURATIONS) - 1, sel_dur + 1)
            else:
                sel_diff = min(len(DIFFICULTIES) - 1, sel_diff + 1)
            continue
        if key in (curses.KEY_ENTER, 10, 13):
            duration = DURATIONS[sel_dur]
            difficulty = DIFFICULTIES[sel_diff]
        else:
            continue

        # --- TEST ---
        wpm, accuracy = run_test(stdscr, duration, difficulty)
        if wpm is None:
            continue

        # Save to history
        save_result(wpm, accuracy, duration, difficulty)
        history = load_history()

        # --- RESULTS ---
        stdscr.timeout(-1)
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
                wpm, accuracy = run_test(stdscr, duration, difficulty)
                if wpm is None:
                    break
                save_result(wpm, accuracy, duration, difficulty)
                history = load_history()
                stdscr.timeout(-1)
                continue
            if key == 9:  # tab
                stdscr.timeout(100)
                break


def cli():
    curses.wrapper(main)


if __name__ == "__main__":
    cli()
