"""Allow running with `python -m termtype`."""
from termtype.app import main
import curses

curses.wrapper(main)
