"""Prepare Steam's Desktop layout for deck-wheel.

deck-wheel reads the sticks and R1 itself, so Steam must not also act on them:
this unbinds both joysticks and R1 (which sends Alt in the stock Desktop layout).

Usage: python3 -I desktop_layout.py <desktop controller_neptune.vdf> <output vdf>

Steam rewrites its layout files when it exits, so install the output with Steam
closed (steam -shutdown), then start Steam again. See README.
"""
import re
import sys

src, out = sys.argv[1], sys.argv[2]
s = open(src).read()


def group_span(text, gid):
    m = re.search(r'\t"group"\n\t\{\n\t\t"id"\t\t"%s"\n' % gid, text)
    start = m.end()
    depth, i = 1, start
    while depth:
        depth += (text[i] == "{") - (text[i] == "}")
        i += 1
    return start, i - 2


EMPTY_STICK = '\t\t"mode"\t\t"dpad"\n\t\t"inputs"\n\t\t{\n\t\t}\n'
for gid in ("27", "31"):            # left / right joystick groups of the Desktop preset
    a, b = group_span(s, gid)
    s = s[:a] + EMPTY_STICK + s[b:]

# R1 lives in the Desktop preset's switch group (id 7)
a, b = group_span(s, "7")
switches = s[a:b]
r1 = switches.find('"right_bumper"')
if r1 != -1:
    line = re.compile(r'\n\t*"binding"\t\t"key_press [A-Z_]+, , "(?=\n)')
    m = line.search(switches, r1)
    if m and m.start() - r1 < 200:
        switches = switches[:m.start()] + switches[m.end():]
s = s[:a] + switches + s[b:]

assert s.count("{") == s.count("}"), "unbalanced braces"
open(out, "w").write(s)
print("ok: sticks and R1 unbound")
