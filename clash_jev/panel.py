"""Native side panel. Docks beside the emulator window and shows each step's read, request and answer.

Tk must own the main thread on macOS, so the match loop runs in a worker thread and hands the
panel its latest snapshot through `publish`. The panel redraws itself a few times a second.
"""

import base64
import threading
import tkinter as tk
from tkinter import font as tkfont

import cv2
import numpy

from clash_jev.state import BattleState
from clash_jev.view import annotate

WIDTH = 470
EMULATOR_APPS = ("BlueStacks", "qemu-system", "MuMuPlayer", "Android Emulator")
BG, PANEL, LINE, TEXT, DIM = "#0e1116", "#161b22", "#262d38", "#dde3ea", "#8590a0"
RATE_LABEL = {"single": "1x", "double": "2x", "triple": "3x"}
JEV, ENEMY, MINE, WARN, TRACK, FILL = "#52e08a", "#ff6b6b", "#4aa8ff", "#f0b849", "#0b0e13", "#3b4656"


def emulator_bounds() -> tuple[int, int, int, int] | None:
    """(x, y, width, height) of the emulator window, from the macOS window list. None if not found.

    Window bounds and owner names need no privacy permission (window titles would).
    """
    try:
        import Quartz
    except ImportError:
        return None
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    for window in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID):
        bounds = window["kCGWindowBounds"]
        is_app_window = window.get("kCGWindowLayer") == 0 and bounds["Height"] > 300
        if is_app_window and any(app in window.get("kCGWindowOwnerName", "") for app in EMULATOR_APPS):
            return int(bounds["X"]), int(bounds["Y"]), int(bounds["Width"]), int(bounds["Height"])
    return None


def _nice(name: str) -> str:
    return name.removeprefix("play_").rsplit("_slot", 1)[0].replace("_", " ")


class Panel:
    def __init__(self, show_screen: bool):
        self.show_screen = show_screen  # no emulator window to look at (--image): show the frame here instead
        self._lock = threading.Lock()
        self._snapshot: dict | None = None
        self._history: list[dict] = []
        self._version = 0
        self._drawn = -1

        self.root = tk.Tk()
        self.root.title("clash-jev")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self._dock()
        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        family = "SF Pro Text" if "SF Pro Text" in tkfont.families() else "Helvetica Neue"
        self.fonts = {
            "label": (family, 10, "bold"),
            "body": (family, 12),
            "small": (family, 10),
            "big": (family, 20, "bold"),
            "stat": (family, 17, "bold"),
        }
        self._photo = None

    def _dock(self) -> None:
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        bounds = emulator_bounds()
        if bounds:
            x, y, height = bounds[0] + bounds[2] + 8, bounds[1], max(bounds[3], 700)
            x = min(x, screen_w - WIDTH)
        else:
            x, y, height = screen_w - WIDTH - 12, 40, screen_h - 110
        self.root.geometry(f"{WIDTH}x{min(height, screen_h - 60)}+{x}+{y}")

    # --- called from the match-loop thread ---------------------------------------------------
    def publish(
        self, frame: numpy.ndarray, state: BattleState, sent_state: dict, decision: dict | None
    ) -> None:
        png = None
        if self.show_screen:
            latest = decision or (self._history[0] if self._history else None)
            square = (latest or {}).get("square_xy")
            small = cv2.resize(annotate(frame, state, square), (170, 257), interpolation=cv2.INTER_AREA)
            png = base64.b64encode(cv2.imencode(".png", small)[1].tobytes())
        with self._lock:
            if decision is not None:
                self._history = [decision, *self._history][:40]
            self._snapshot = {"state": sent_state, "png": png}
            self._version += 1

    # --- Tk thread ------------------------------------------------------------------------------
    def run(self, worker: threading.Thread) -> None:
        worker.start()

        def tick():
            if self._version != self._drawn:
                with self._lock:
                    snapshot, history, self._drawn = self._snapshot, list(self._history), self._version
                self._draw(snapshot, history)
            if worker.is_alive():
                self.root.after(250, tick)
            elif not self.show_screen:  # a saved screenshot stays up until the window is closed
                self.root.after(1500, self.root.destroy)

        tick()
        self.root.mainloop()

    def _text(self, x, y, text, font="body", fill=TEXT, anchor="nw", width=None) -> int:
        item = self.canvas.create_text(
            x, y, text=text, font=self.fonts[font], fill=fill, anchor=anchor, width=width
        )
        return self.canvas.bbox(item)[3]

    def _section(self, y: int, title: str) -> int:
        self.canvas.create_line(14, y + 8, WIDTH - 14, y + 8, fill=LINE)
        return self._text(14, y + 16, title.upper(), "label", DIM) + 6

    def _bars(self, y: int, probabilities: dict, chosen: str | None) -> int:
        for name, p in sorted((probabilities or {}).items(), key=lambda item: -item[1])[:7]:
            is_chosen = name == chosen
            self._text(14, y, _nice(name), "body", JEV if is_chosen else TEXT)
            self.canvas.create_rectangle(170, y + 5, WIDTH - 56, y + 13, fill=TRACK, outline="")
            end = 170 + (WIDTH - 56 - 170) * p
            self.canvas.create_rectangle(170, y + 5, end, y + 13, fill=JEV if is_chosen else FILL, outline="")
            self._text(WIDTH - 14, y, f"{p * 100:.0f}%", "body", DIM, anchor="ne")
            y += 20
        return y

    def _draw(self, snapshot: dict | None, history: list[dict]) -> None:
        c = self.canvas
        c.delete("all")
        if not snapshot or not snapshot["state"]:
            self._text(
                WIDTH // 2, 120, "Waiting for a battle…\nStart a match in the emulator.", "body", DIM, "n"
            )
            return
        s, last = snapshot["state"], history[0] if history else None

        y = self._text(14, 14, "JEV'S CHOICE", "label", DIM) + 4
        if last:
            waited = last["action"] == "wait"
            if not waited:
                headline = " → ".join(_nice(part) for part in last["action"].split(" -> "))
            elif last.get("note"):
                headline = "Nothing played — " + last["note"]
            else:
                headline = _nice(last.get("strategy_choice", "no play")) + " — nothing played"
            y = self._text(14, y, headline, "big", WARN if waited else JEV, width=WIDTH - 28)
            meta = (
                f"strategy: {_nice(last.get('strategy_choice', '–'))} · {last.get('requests_made', 0)} Jev requests · "
                f"{last.get('latency_ms', '–')} ms · at {last['state_elapsed']}s"
            )
            y = self._text(14, y + 2, meta, "small", DIM)
        else:
            y = self._text(14, y, "No decision yet", "body", DIM)

        y = self._section(y, "What the bot read")
        left = 14
        if snapshot["png"]:
            self._photo = tk.PhotoImage(data=snapshot["png"])
            c.create_image(14, y, image=self._photo, anchor="nw")
            left = 200
        stats = [
            (str(s["elixir"]), "my elixir"),
            (str(s["enemy_elixir_estimate"]), "enemy elixir (est.)"),
            (
                f"{s['clock']['elapsed_seconds'] // 60}:{s['clock']['elapsed_seconds'] % 60:02d}",
                f"match time · {RATE_LABEL[s['clock']['elixir_rate']]} refill",
            ),
        ]
        if snapshot["png"]:
            sy = y
            for value, label in stats:
                self._text(left, sy, value, "stat")
                sy = self._text(left + 62, sy + 5, label, "small", DIM) + 12
            towers = "  ".join(
                f"{name.replace('_', ' ')} {round(v * 100) if isinstance(v, float) else '–'}%"
                for name, v in s["towers"].items()
            )
            self._text(left, sy + 4, towers, "small", DIM, width=WIDTH - left - 14)
            y += 264
        else:
            for index, (value, label) in enumerate(stats):
                self._text(14 + index * 150, y, value, "stat")
                self._text(14 + index * 150, y + 24, label, "small", DIM)
            y += 44
            towers = "   ".join(
                f"{name.replace('_', ' ')} {round(v * 100) if isinstance(v, float) else '–'}%"
                for name, v in s["towers"].items()
            )
            y = self._text(14, y, towers, "small", DIM, width=WIDTH - 28) + 2

        y = self._section(y, "Hand")
        for card in s["hand"]:
            self._text(
                14,
                y,
                _nice(card["card"]),
                "body",
                DIM if (card.get("elixir_cost") or 0) > s["elixir"] else TEXT,
            )
            self._text(
                150, y, f"{card['elixir_cost'] if card['elixir_cost'] is not None else '?'}", "body", DIM
            )
            shown = [card.get("class", ""), f"health {card.get('health')}", f"hits {card.get('targets')}"]
            shown += ["flies"] if card.get("flies") else []
            y = self._text(
                172, y + 1, " · ".join(part for part in shown if part), "small", DIM, width=WIDTH - 186
            )
            y += 4

        y = self._section(y, "Enemy troops")
        if not s["enemy_troops"]:
            y = self._text(14, y, "none seen", "small", DIM)
        for troop in s["enemy_troops"]:
            flying = " (flying)" if troop.get("flies") else ""
            self._text(14, y, _nice(troop["troop"]) + flying, "body", ENEMY)
            where = f"{troop['lane']} · {troop['where']} · {round(troop['health_remaining'] * 100)}%"
            y2 = self._text(WIDTH - 14, y, where, "small", DIM, anchor="ne")
            y = y2 + 5

        if last and last.get("strategy_probabilities"):
            y = self._section(y, "Step 1 — which strategy?")
            y = self._bars(y, last["strategy_probabilities"], last.get("strategy_choice"))
        if last and last.get("card_probabilities"):
            y = self._section(y, f"Step 2 — which card for {_nice(last.get('strategy_choice', ''))}?")
            y = self._bars(y, last["card_probabilities"], last.get("card_choice"))
        if last and last.get("square_probabilities"):
            y = self._section(y, f"Step 3 — where does {_nice(last.get('card_choice', ''))} go?")
            y = self._bars(y, last["square_probabilities"], last.get("square_choice"))

        y = self._section(y, "Every step")
        rows = max(0, (self.canvas.winfo_height() - y - 8) // 17)  # only as many as still fit
        for entry in history[:rows]:
            action = (
                "wait"
                if entry["action"] == "wait"
                else " → ".join(_nice(p) for p in entry["action"].split(" -> "))
            )
            self._text(14, y, f"{entry['state_elapsed']}s", "small", DIM)
            self._text(52, y, action, "small", DIM if entry["action"] == "wait" else TEXT)
            y = self._text(WIDTH - 14, y, f"{entry.get('latency_ms', '–')} ms", "small", DIM, anchor="ne") + 3
