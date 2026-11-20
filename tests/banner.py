# banner.py — ASCII banner at startup.
#
# Shows the project name in large letters in the web interface palette:
#   accent  #4d9fff  — blue
#   success #3fb950  — green
#   text    #e6edf3  — primary text
#   dim     #8b949e  — secondary text
#   faint   #5d6672  — service captions
#
# Colors are disabled with NO_COLOR, TERM=dumb or when output goes to a pipe.
# Force enable: FORCE_COLOR=1.

import os
import sys


# ANSI truecolor (24-bit). Most modern terminals support it.
ACCENT = "\033[38;2;77;159;255m"      # #4d9fff
SUCCESS = "\033[38;2;63;185;80m"      # #3fb950
DIM = "\033[38;2;139;148;158m"        # #8b949e
FAINT = "\033[38;2;93;102;114m"       # #5d6672
RESET = "\033[0m"
BOLD = "\033[1m"


# ASCII art: figlet -f standard "SKYFALL"
BANNER = r""" ____  _  ____   _______ _    _     _
/ ___|| |/ /\ \ / /  ___/ \  | |   | |
\___ \| ' /  \ V /| |_ / _ \ | |   | |
 ___) | . \   | | |  _/ ___ \| |___| |___
|____/|_|\_\  |_| |_|/_/   \_\_____|_____|"""


def _supports_color() -> bool:
    if os.environ.get("FORCE_COLOR") in {"1", "true", "yes"}:
        return True
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def clear_console() -> None:
    """
    Clears the screen and (if the terminal supports it) the scrollback.

    Does nothing when output goes to a pipe/file, so as not to break logs and
    automation. Disabled via OSINT_NO_CLEAR=1.
    """
    if os.environ.get("OSINT_NO_CLEAR") in {"1", "true", "yes"}:
        return
    if os.environ.get("TERM") == "dumb":
        return
    try:
        if not sys.stdout.isatty():
            return
        # 2J — clear the screen, 3J — clear the scrollback, H — cursor to the start.
        sys.stdout.write("\033[H\033[2J\033[3J")
        sys.stdout.flush()
    except Exception:
        pass


def print_banner(version: str = "0.1.0"):
    """Prints the Skyfall banner and brief build information."""
    from i18n import t

    tagline = t("app.tagline")
    powered_by = t("app.powered_by")

    if _supports_color():
        print(f"{ACCENT}{BANNER}{RESET}")
        print(
            f"{ACCENT}{BOLD}  SKYFALL{RESET} "
            f"{FAINT}v{version}{RESET}  "
            f"{SUCCESS}●{RESET} {DIM}{tagline}{RESET}"
        )
        print(f"{FAINT}  {powered_by}{RESET}")
    else:
        print(BANNER)
        print(f"  SKYFALL v{version}  |  {tagline}")
        print(f"  {powered_by}")

    print()
