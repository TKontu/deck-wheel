#!/usr/bin/python3
"""deck-wheel: on-screen hotkey wheels for the Steam Deck sticks in Desktop Mode.

Touch a stick  -> its wheel appears
Push the stick -> highlight a slot
Let go         -> lifting your thumb off the stick runs the slot (R1 also runs it);
                  for side flicks the touch sensor misses, a quick snap back runs it
Ease back      -> resting the dot in the centre circle, thumb still on, cancels

It also makes room for Steam's on-screen keyboard: when the keyboard opens, the
active window shrinks to the space above it, and it is restored when the keyboard
closes (via the deckwheel-osk KWin script).

Reads the Deck controller directly from hidraw (alongside Steam), draws the wheel
with GTK4, and types the hotkeys through a uinput virtual keyboard, so it works in
every app, Wayland-native ones included.
"""
import glob
import math
import os
import struct
import sys
import threading
import time

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from evdev import UInput, ecodes as e  # noqa: E402

APP_ID = "io.github.deckwheel"
SIZE = 520                 # window is SIZE x SIZE px
SHOW_DEFLECT = 9000        # show the wheel when pushed this far even without the touch sensor
HUB = 0.42                 # centre circle (cancel zone) radius as a fraction of the wheel
SELECT_DEFLECT = int(32767 * HUB)   # dot outside the centre circle = a slot is highlighted
CANCEL_DWELL = 0.15        # dot resting in the centre circle this long, thumb still on = cancel
                           # (a slot runs when the thumb lifts off the stick while it is highlighted)
SWITCH_HOLD = 0.05         # a different slot must stay pointed at this long to replace the
                           # highlighted one (ignores the spring overshoot when you let go)
SNAP_DEFLECT = 7000        # side flicks (touch sensor never sees the thumb): the stick snapping
SNAP_TIME = 0.12           # back this close to the middle within SNAP_TIME runs the slot
HIDE_DELAY = 0.15          # seconds after the thumb lifts before the wheel hides
PREFIX_GAP = 0.08          # seconds between Ctrl+B and the herdr action key

# ---------------------------------------------------------------- keyboard layout


def _first_layout():
    try:
        for line in open(os.path.expanduser("~/.config/kxkbrc")):
            if line.startswith("LayoutList="):
                return line.split("=", 1)[1].strip().split(",")[0]
    except OSError:
        pass
    return "us"


# keys whose position differs from US on the layouts we care about
LAYOUT_FIXUPS = {
    "de": {"-": e.KEY_SLASH},
    "fi": {"-": e.KEY_SLASH},
    "se": {"-": e.KEY_SLASH},
}
LAYOUT = _first_layout()


def key(name):
    if name in LAYOUT_FIXUPS.get(LAYOUT, {}):
        return LAYOUT_FIXUPS[LAYOUT][name]
    return {"-": e.KEY_MINUS}.get(name) or getattr(e, "KEY_" + name.upper())


CTRL, SHIFT = e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT


def combo(*names):
    return [key(n) if isinstance(n, str) else n for n in names]


def herdr(k):
    """Ctrl+B, then the herdr action key."""
    return [combo(CTRL, "b"), combo(k)]


# ---------------------------------------------------------------- wheels (clockwise from the top)

WHEELS = {
    "left": ("herdr", [
        ("New tab", herdr("c")),
        ("Next tab", herdr("n")),
        ("Split right", herdr("v")),
        ("Workspaces", herdr("w")),
        ("Detach", herdr("q")),
        ("Goto", herdr("g")),
        ("Split down", herdr("-")),
        ("Prev tab", herdr("p")),
    ]),
    "right": ("Edit", [
        ("Ctrl+B", [combo(CTRL, "b")]),
        ("Paste", [combo(CTRL, SHIFT, "v")]),
        ("Shift+Tab", [combo(SHIFT, "tab")]),
        ("Newline", [combo(SHIFT, "enter")]),
        ("Ctrl+C", [combo(CTRL, "c")]),
        ("Esc Esc", [combo("esc"), combo("esc")]),
        ("Clear line", [combo(CTRL, "u")]),
        ("Copy", [combo(CTRL, SHIFT, "c")]),
    ]),
}

# ---------------------------------------------------------------- key output


class Keyboard:
    def __init__(self):
        # Declare a full keyboard (all standard key codes), not just the keys the wheels
        # use: udev only tags a device ID_INPUT_KEYBOARD when it has the full main block,
        # and the compositor ignores or mistranslates keys from non-keyboard devices.
        keys = set(range(e.KEY_ESC, e.KEY_MICMUTE + 1))
        for _, slots in WHEELS.values():
            for _, steps in slots:
                for step in steps:
                    keys.update(step)
        self.ui = UInput({e.EV_KEY: sorted(keys)}, name="deck-wheel keyboard")
        self.lock = threading.Lock()

    def run(self, steps):
        threading.Thread(target=self._run, args=(steps,), daemon=True).start()

    def _run(self, steps):
        with self.lock:
            time.sleep(0.03)
            for i, step in enumerate(steps):
                if i:
                    time.sleep(PREFIX_GAP)
                for k in step:
                    self.ui.write(e.EV_KEY, k, 1)
                    self.ui.syn()
                    time.sleep(0.008)
                for k in reversed(step):
                    self.ui.write(e.EV_KEY, k, 0)
                    self.ui.syn()
                    time.sleep(0.008)

# ---------------------------------------------------------------- controller input


def find_deck_hidraw():
    for dev in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            if "Steam Controller" not in open(dev + "/device/uevent").read():
                continue
            fd = os.open("/dev/" + os.path.basename(dev), os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        deadline = time.time() + 0.5
        while time.time() < deadline:
            try:
                d = os.read(fd, 64)
                if len(d) == 64 and d[2] == 0x09:
                    os.set_blocking(fd, True)
                    return fd
            except BlockingIOError:
                time.sleep(0.01)
            except OSError:
                break
        os.close(fd)
    return None


class Stick:
    def __init__(self, side):
        self.side = side
        self.touched = self.clicked = False
        self.x = self.y = 0


R1 = {"down": False}


def parse(d, left, right):
    # Deck state report (id 0x09): buttons in bytes 8..15, sticks as int16 at 48..55
    R1["down"] = bool(d[8] & 0x04)
    left.clicked = bool(d[10] & 0x40)
    right.clicked = bool(d[11] & 0x04)
    left.touched = bool(d[13] & 0x40)
    right.touched = bool(d[13] & 0x80)
    left.x, left.y, right.x, right.y = struct.unpack_from("<hhhh", d, 48)

# ---------------------------------------------------------------- on-screen keyboard room

STEAM_UI_LOG = os.path.expanduser("~/.local/share/Steam/logs/controller_ui.txt")


def kwin_shortcut(name):
    """Invoke a shortcut registered by the deckwheel-osk KWin script."""
    try:
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            "org.kde.kglobalaccel", "/component/kwin", "org.kde.kglobalaccel.Component",
            "invokeShortcut", GLib.Variant("(s)", (name,)), None, Gio.DBusCallFlags.NONE, 2000, None)
    except GLib.Error as err:
        print("kwin shortcut failed:", err.message, file=sys.stderr, flush=True)


def watch_osk():
    """Follow Steam's controller UI log; it records every keyboard open/close."""
    f, ino, first = None, None, True
    while True:
        try:
            st = os.stat(STEAM_UI_LOG)
            if f is None or st.st_ino != ino or st.st_size < f.tell():
                if f:
                    f.close()
                f, ino = open(STEAM_UI_LOG, errors="replace"), st.st_ino
                if first:                     # skip history; a new/rotated log is read from the start
                    f.seek(0, os.SEEK_END)
                    first = False
            for line in f.readlines():
                if "Set OSK active 1" in line:
                    kwin_shortcut("DeckWheelOskShrink")
                elif "Set OSK active 0" in line:
                    kwin_shortcut("DeckWheelOskRestore")
        except OSError:
            f = None
        time.sleep(0.15)

# ---------------------------------------------------------------- UI


class Wheel(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.title, self.slots, self.selected = "", [], None
        self.dot = (0.0, 0.0)       # stick position, -1..1 (x right, y up)
        self.set_content_width(SIZE)
        self.set_content_height(SIZE)
        self.set_draw_func(self.draw)

    def draw(self, _area, cr, w, h):
        if not self.slots:          # hidden: window stays mapped but fully transparent
            return
        cx, cy = w / 2, h / 2
        r_out = min(w, h) / 2 - 6
        r_in = r_out * HUB
        n = len(self.slots) or 1
        step = 2 * math.pi / n
        cr.set_source_rgba(0.08, 0.09, 0.11, 0.96)
        cr.arc(cx, cy, r_out, 0, 2 * math.pi)
        cr.fill()
        for i, (label, _) in enumerate(self.slots):
            a0 = -math.pi / 2 + i * step - step / 2      # slot 0 centred at the top
            a1 = a0 + step
            if i == self.selected:
                cr.set_source_rgba(0.25, 0.55, 0.95, 0.95)
                cr.move_to(cx + r_in * math.cos(a0), cy + r_in * math.sin(a0))
                cr.arc(cx, cy, r_out - 4, a0, a1)
                cr.arc_negative(cx, cy, r_in, a1, a0)
                cr.close_path()
                cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.18)             # divider
            cr.set_line_width(1.5)
            cr.move_to(cx + r_in * math.cos(a0), cy + r_in * math.sin(a0))
            cr.line_to(cx + (r_out - 4) * math.cos(a0), cy + (r_out - 4) * math.sin(a0))
            cr.stroke()
            mid = a0 + step / 2
            rl = (r_in + r_out) / 2 + 8
            self._text(cr, label, cx + rl * math.cos(mid), cy + rl * math.sin(mid), 19,
                       bold=(i == self.selected))
        cr.set_source_rgba(0.14, 0.15, 0.18, 1)        # centre = cancel zone
        cr.arc(cx, cy, r_in, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.22 if self.selected is not None else 0.45)
        cr.set_line_width(2)
        cr.set_dash([6, 6])
        cr.arc(cx, cy, r_in, 0, 2 * math.pi)
        cr.stroke()
        cr.set_dash([])
        self._text(cr, self.title, cx, cy - 10, 22, bold=True)
        self._text(cr, "let go to run" if self.selected is not None else "centre = cancel",
                   cx, cy + 16, 13, alpha=0.6)
        dx, dy = self.dot                              # live stick position
        px, py = cx + dx * (r_out - 10), cy - dy * (r_out - 10)
        cr.set_source_rgba(0, 0, 0, 0.6)
        cr.arc(px, py, 10, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 1)
        cr.arc(px, py, 7, 0, 2 * math.pi)
        cr.fill()

    @staticmethod
    def _text(cr, text, x, y, size, bold=False, alpha=1.0):
        cr.select_font_face("Sans", 0, 1 if bold else 0)
        cr.set_font_size(size)
        ext = cr.text_extents(text)
        cr.set_source_rgba(1, 1, 1, alpha)
        cr.move_to(x - ext.width / 2 - ext.x_bearing, y - ext.height / 2 - ext.y_bearing)
        cr.show_text(text)


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.kb = Keyboard()
        self.left, self.right = Stick("left"), Stick("right")
        self.active = None          # side whose wheel is shown
        self.selected = None
        self.last_touch = 0.0
        self.prev_r1 = False
        self.last_high = 0.0        # last time the stick was pushed out far enough to select
        self.last_draw = 0.0
        self.prev_touched = False
        self.pending = False        # a redraw is already queued for the UI thread
        self.view = {"title": "", "slots": [], "selected": None, "dot": (0.0, 0.0)}
        self.candidate, self.candidate_since = None, 0.0   # slot being switched to
        self.locked = None          # side that just fired; ignore it until the thumb lifts

    def do_activate(self):
        css = Gtk.CssProvider()
        css.load_from_data(b"window, window.background { background: transparent; box-shadow: none; }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.win = Gtk.Window(application=self, title="deck-wheel", decorated=False, resizable=False)
        self.win.set_default_size(SIZE, SIZE)
        self.wheel = Wheel()
        self.win.set_child(self.wheel)
        self.win.connect("map", self._click_through)
        self.win.present()          # mapped once and kept; hiding = drawing nothing
        self.hold()
        if DEMO:                    # --demo <left|right> <slot>: show a wheel for 4 s (for testing)
            self.open(DEMO[0])
            self.selected = self.view["selected"] = int(DEMO[1])
            GLib.timeout_add(4000, lambda: self.quit())
            return
        threading.Thread(target=self.read_loop, daemon=True).start()
        threading.Thread(target=watch_osk, daemon=True).start()

    def _click_through(self, win):
        surf = win.get_surface()
        if surf:
            surf.set_input_region(cairo.Region())   # mouse goes straight to the app below

    # -- input thread: every controller report (~250 Hz) goes through step(), so quick
    #    flicks are never missed; the UI thread only draws the latest state.
    def read_loop(self):
        while True:
            fd = find_deck_hidraw()
            if fd is None:
                time.sleep(2)
                continue
            try:
                while True:
                    d = os.read(fd, 64)              # blocks until the next report
                    if len(d) == 64 and d[2] == 0x09:
                        parse(d, self.left, self.right)
                        self.step(time.time())
            except OSError:
                os.close(fd)
                time.sleep(1)

    def step(self, now):
        sticks = {"left": self.left, "right": self.right}

        def engaged(s):
            return s.touched or math.hypot(s.x, s.y) > SHOW_DEFLECT

        if self.locked and not engaged(sticks[self.locked]):
            self.locked = None
        if self.active is None:
            for side, s in sticks.items():
                if side != self.locked and engaged(s):
                    self.open(side)
                    break
        if self.active:
            s = sticks[self.active]
            mag = math.hypot(s.x, s.y)
            if mag > self.dbg["peak"]:
                self.dbg.update(peak=mag, ang=math.degrees(math.atan2(s.x, s.y)) % 360)
            self.dbg["touch"] += s.touched
            self.touch_seen |= s.touched
            self.dbg["n"] += 1
            self.view["dot"] = (max(-1.0, min(1.0, s.x / 32767)), max(-1.0, min(1.0, s.y / 32767)))
            if mag > SELECT_DEFLECT:                 # update the highlight first ...
                self.last_high = now
                ang = math.atan2(s.x, s.y) % (2 * math.pi)   # 0 = up, clockwise
                n = len(WHEELS[self.active][1])
                sel = int(round(ang / (2 * math.pi / n))) % n
                if self.selected is None or sel == self.selected:
                    self.selected, self.candidate = sel, None
                elif sel != self.candidate:
                    self.candidate, self.candidate_since = sel, now
                elif now - self.candidate_since >= SWITCH_HOLD:
                    self.selected, self.candidate = sel, None
            if self.selected is not None:            # ... then check for a let-go
                if self.prev_touched and not s.touched:
                    self.fire("thumb lifted")        # thumb lifted off the stick: run the slot
                    self.prev_r1, self.prev_touched = R1["down"], False
                    return
                if (not self.touch_seen and mag < SNAP_DEFLECT
                        and now - self.last_high <= SNAP_TIME):
                    self.fire(f"snapped back in {int((now - self.last_high) * 1000)} ms")
                    self.prev_r1 = R1["down"]
                    return
                if (mag < SELECT_DEFLECT and (s.touched or not self.touch_seen)
                        and now - self.last_high > CANCEL_DWELL):
                    print(f"{self.active} wheel: dot in centre circle, cancelled", flush=True)
                    self.selected = None
            self.prev_touched = s.touched
            if engaged(s):
                self.last_touch = now
                if R1["down"] and not self.prev_r1:
                    if self.selected is None:
                        print(f"{self.active} wheel: R1 pressed but no slot highlighted", flush=True)
                    else:
                        self.fire("R1")
                        self.prev_r1 = True
                        return
            elif now - self.last_touch > HIDE_DELAY:
                d = self.dbg
                print(f"{self.active} wheel: closed, nothing run (peak {int(d['peak'])}/{SELECT_DEFLECT} "
                      f"at {int(d['ang'])} deg, touched {d['touch']}/{d['n']} reports, "
                      f"selected {self.selected})", flush=True)
                self.close()
            self.view["selected"] = self.selected
            self.request_draw(now)
        self.prev_r1 = R1["down"]

    def request_draw(self, now, force=False):
        if (force or now - self.last_draw > 0.011) and not self.pending:
            self.last_draw, self.pending = now, True
            GLib.idle_add(self.draw, priority=GLib.PRIORITY_HIGH)

    # -- UI thread
    def draw(self):
        self.pending = False
        v = dict(self.view)
        self.wheel.title, self.wheel.slots = v["title"], v["slots"]
        self.wheel.selected, self.wheel.dot = v["selected"], v["dot"]
        self.wheel.queue_draw()
        return False

    def fire(self, how):
        label, steps = WHEELS[self.active][1][self.selected]
        print(f"{self.active} wheel: run '{label}' ({how})", flush=True)
        self.kb.run(steps)
        self.locked = self.active   # ignore this stick until the thumb lifts
        self.close()

    def open(self, side):
        print(f"{side} wheel: open", flush=True)
        self.active, self.selected, self.candidate = side, None, None
        self.dbg = {"peak": 0.0, "ang": 0.0, "touch": 0, "n": 0}
        self.touch_seen = False     # did the touch sensor see the thumb during this use?
        title, slots = WHEELS[side]
        self.view.update(title=title, slots=slots, selected=None, dot=(0.0, 0.0))
        self.prev_touched = True
        self.last_touch = time.time()
        self.request_draw(self.last_touch, force=True)

    def close(self):
        self.active = self.selected = None
        self.view.update(slots=[], selected=None)
        self.request_draw(time.time(), force=True)

DEMO = sys.argv[2:4] if sys.argv[1:2] == ["--demo"] else None

if __name__ == "__main__":
    sys.exit(App().run([]))
