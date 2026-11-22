"""Build the Steam Input layout for the 'herdr devbox' shortcut from the Desktop layout.

Usage: python3 -I build.py <desktop controller_neptune.vdf> <output vdf>

Layout:
  left trackpad  : scroll wheel (unchanged from Desktop layout)
  right trackpad : mouse        (unchanged)
  left stick     : hotkey wheel 'herdr' (push to highlight, click stick to fire)
  right stick    : hotkey wheel 'Edit'
  buttons/dpad   : unchanged
"""
import re
import sys

src, out = sys.argv[1], sys.argv[2]
s = open(src).read()

T = "\t"


def act(keys, label="", delay=None):
    lines = "".join(
        f'{T*7}"binding"{T*2}"key_press {k}, {label if i == 0 else ""}, , "\n'
        for i, k in enumerate(keys)
    )
    settings = ""
    if delay:
        settings = f'{T*6}"settings"\n{T*6}{{\n{T*7}"delay_start"{T*2}"{delay}"\n{T*6}}}\n'
    return (
        f'{T*5}"Full_Press"\n{T*5}{{\n{T*6}"bindings"\n{T*6}{{\n{lines}{T*6}}}\n'
        f"{settings}{T*5}}}\n"
    )


def inp(name, acts):
    return (
        f'{T*3}"{name}"\n{T*3}{{\n{T*4}"activators"\n{T*4}{{\n{"".join(acts)}{T*4}}}\n'
        f'{T*4}"disabled_activators"\n{T*4}{{\n{T*4}}}\n{T*3}}}\n'
    )


PREFIX = ["LEFT_CONTROL", "B"]


def herdr(key, label):
    """Ctrl+B, then the action key 80 ms later."""
    return [act(PREFIX, label), act([key], "", 80)]


def dpad(inputs, deadzone=None):
    body = f'{T*2}"mode"{T*2}"dpad"\n{T*2}"inputs"\n{T*2}{{\n{"".join(inputs)}{T*2}}}\n'
    if deadzone:
        body += f'{T*2}"settings"\n{T*2}{{\n{T*3}"deadzone"{T*2}"{deadzone}"\n{T*2}}}\n'
    return body


def replace_group(text, gid, body):
    m = re.search(r'\t"group"\n\t\{\n\t\t"id"\t\t"%s"\n' % gid, text)
    start = m.end()
    depth, i = 1, start
    while depth:
        depth += (text[i] == "{") - (text[i] == "}")
        i += 1
    return text[:start] + body + text[i - 2:]


def radial(name, slots):
    """Hotkey wheel: push the stick to highlight a slot, click the stick in to fire it."""
    body = f'{T*2}"mode"{T*2}"radial_menu"\n{T*2}"name"{T*2}"{name}"\n{T*2}"description"{T*2}""\n{T*2}"inputs"\n{T*2}{{\n'
    body += "".join(inp(f"touch_menu_button_{i}", a) for i, a in enumerate(slots))
    body += (f'{T*2}}}\n{T*2}"settings"\n{T*2}{{\n{T*3}"touchmenu_button_fire_type"{T*2}"0"\n'
             f'{T*3}"touch_menu_opacity"{T*2}"100"\n{T*3}"touch_menu_scale"{T*2}"150"\n{T*2}}}\n')
    return body


# slots go clockwise from the top
left_stick = radial("herdr", [
    herdr("C", "New tab"),
    herdr("N", "Next tab"),
    herdr("V", "Split right"),
    herdr("W", "Workspaces"),
    herdr("Q", "Detach"),
    herdr("G", "Goto"),
    herdr("DASH", "Split down"),
    herdr("P", "Prev tab"),
])

right_stick = radial("Edit", [
    [act(PREFIX, "Ctrl+B prefix")],
    [act(["LEFT_CONTROL", "LEFT_SHIFT", "V"], "Paste")],
    [act(["LEFT_SHIFT", "TAB"], "Shift+Tab")],
    [act(["LEFT_SHIFT", "RETURN"], "Newline")],
    [act(["LEFT_CONTROL", "C"], "Ctrl+C")],
    [act(["ESCAPE"], "Esc"), act(["ESCAPE"], "", 80)],
    [act(["LEFT_CONTROL", "U"], "Clear line")],
    [act(["LEFT_CONTROL", "LEFT_SHIFT", "C"], "Copy")],
])

s = replace_group(s, "27", left_stick)   # left joystick (active)
s = replace_group(s, "31", right_stick)  # right joystick (active)
s = re.sub(r'("title"\t\t)"Desktop Configuration"', r'\1"herdr devbox"', s, count=1)

assert s.count("{") == s.count("}"), "unbalanced braces"
open(out, "w").write(s)
print("ok")
