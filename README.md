# termtype

A [Monkeytype](https://monkeytype.com)-style typing test that runs entirely in your terminal. No browser, no dependencies — just Python.

```
                          termtype

                       select duration

                    15s    30s    60s

             pb  15s: 72 wpm  |  30s: 68 wpm  |  60s: 65 wpm

              ← → select · enter start · s stats · q quit
```

## Install

```bash
pip install git+https://github.com/vinayakvivek/termtype.git
```

Or clone and install locally:

```bash
git clone https://github.com/vinayakvivek/termtype.git
cd termtype
pip install .
```

Then run:

```bash
termtype
```

### Run without installing

```bash
git clone https://github.com/vinayakvivek/termtype.git
cd termtype
python -m termtype
```

## Features

- **Typing test** with 15s, 30s, and 60s durations
- **Live feedback** — green for correct, red for wrong, underline cursor
- **Real-time WPM and accuracy** displayed as you type
- **Word-level wrapping** — words never split across lines
- **Personal history** — all results saved to `~/.termtype_history.json`
- **Progress tracking** — braille line graph of your WPM over time
- **Time period filtering** — view stats for last week, month, year, or all-time
- **Personal bests** shown on the menu and compared after each test
- **Per-duration breakdown** — separate stats for each test duration

## Controls

| Screen  | Key           | Action                |
|---------|---------------|-----------------------|
| Menu    | `← →`         | Select duration       |
| Menu    | `Enter`       | Start test            |
| Menu    | `s`           | Open stats            |
| Menu    | `q`           | Quit                  |
| Test    | type          | Timer starts on first key |
| Test    | `Backspace`   | Delete last character |
| Test    | `Esc`         | Cancel test           |
| Results | `Enter`       | Retry same duration   |
| Results | `Tab`         | Back to menu          |
| Results | `s`           | Open stats            |
| Results | `q`           | Quit                  |
| Stats   | `← →`         | Switch time period    |
| Stats   | `Esc` / `q`   | Back                  |

## Stats screen

Press `s` to see your progress:

- **Summary** — total tests, best WPM, averages, accuracy
- **Line graph** — WPM trend over time using braille characters
- **Period tabs** — filter by week / month / year / all-time
- **Per-duration breakdown** — stats for 15s, 30s, 60s separately
- **Recent tests** — table of latest results with PBs highlighted

## Requirements

- Python 3.8+
- A terminal with Unicode support (most modern terminals)
- No external dependencies

## License

MIT
