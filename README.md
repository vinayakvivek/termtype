# termtype

A [Monkeytype](https://monkeytype.com)-style typing test that runs entirely in your terminal. No browser, no dependencies — just Python.

```
                          termtype

                            mode
              classic   word rain   time attack   quotes

                         duration
                      15s   30s   60s

                        difficulty
                    easy  medium  hard

        ← → select · ↑ ↓ row · enter start · s stats · q quit
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

## Game modes

### Classic
The standard typing test. Pick a duration (15s/30s/60s) and difficulty, type as fast and accurately as you can. Tracks WPM, accuracy, and personal bests.

### Word Rain
Words fall from the top of the screen. Type each word before it hits the bottom. Speed increases over time. You get 3 lives — miss 3 words and it's game over. Tracks score and survival time.

### Time Attack
Start with 10 seconds on the clock. Each correctly typed word adds +2s. Each mistake costs -1s. Survive as long as you can. A timer bar shows your remaining time turning red when low.

### Quotes
Type real quotes from famous people. Quotes are fetched fresh from [ZenQuotes API](https://zenquotes.io/) each session and cached locally for offline use. The author is revealed after you finish typing. Bundled fallback quotes included for first launch.

## Difficulty levels

| Level    | Words | Length  | Description                        |
|----------|-------|---------|------------------------------------|
| **easy** | 300   | 1-5     | Common everyday words              |
| **medium** | 300 | 4-8     | Moderate frequency, longer words   |
| **hard** | 300   | 6-12    | Less common, challenging words     |

Word dictionary sourced from [google-10000-english](https://github.com/first20hours/google-10000-english).

## Controls

| Screen     | Key           | Action                          |
|------------|---------------|---------------------------------|
| Menu       | `← →`         | Select option                  |
| Menu       | `↑ ↓`         | Switch between rows            |
| Menu       | `Enter`       | Start                          |
| Menu       | `s`           | Open stats                     |
| Menu       | `q`           | Quit                           |
| Classic    | type          | Timer starts on first key      |
| Classic    | `Backspace`   | Delete last character          |
| Classic    | `Esc`         | Cancel                         |
| Word Rain  | type          | Type falling words to destroy  |
| Word Rain  | `Backspace`   | Clear input                    |
| Word Rain  | `Esc`         | Quit                           |
| Time Attack| type          | Type words, +2s correct, -1s wrong |
| Time Attack| `Esc`         | Quit                           |
| Quotes     | type          | Type the quote                 |
| Quotes     | `Esc`         | Cancel                         |
| Results    | `Enter`       | Retry / next                   |
| Results    | `Tab`         | Back to menu                   |
| Results    | `q`           | Quit                           |
| Stats      | `← →`         | Switch time period             |
| Stats      | `Esc` / `q`   | Back                           |

## Stats & progress

Press `s` to see your progress:

- **Summary** — total tests, best WPM, averages, accuracy
- **Line graph** — WPM trend over time using braille characters
- **Period tabs** — filter by week / month / year / all-time
- **Per-duration breakdown** — stats for 15s, 30s, 60s separately
- **Recent tests** — table of latest results with PBs highlighted

All data stored in `~/.termtype/`.

## Requirements

- Python 3.8+
- A terminal with Unicode support (most modern terminals)
- No external dependencies (quotes API is optional — works offline)

## License

MIT
