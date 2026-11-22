// deck-wheel OSK room: make space for the Steam on-screen keyboard.
// deck-wheel watches Steam's log and invokes these shortcuts when the keyboard opens/closes.
var KEYBOARD_TOP = 0.47;   // the Steam keyboard covers the screen below ~47 % of its height
var saved = null;          // { win, geom, maximized }

function usable(w) {
    return w && w.normalWindow && !w.fullScreen &&
        String(w.resourceClass).indexOf("steam") === -1 &&
        String(w.resourceClass) !== "io.github.deckwheel";
}

function shrink() {
    var w = workspace.activeWindow;
    if (saved || !usable(w)) return;
    var area = workspace.clientArea(KWin.MaximizeArea, w);
    var g = w.frameGeometry;
    saved = {
        win: w,
        geom: { x: g.x, y: g.y, width: g.width, height: g.height },
        maximized: g.width >= area.width - 2 && g.height >= area.height - 2
    };
    var screen = workspace.clientArea(KWin.FullScreenArea, w);
    var bottom = screen.y + Math.round(screen.height * KEYBOARD_TOP) - 6;
    if (g.y + g.height <= bottom) { saved = null; return; }   // already clear of the keyboard
    if (saved.maximized) w.setMaximize(false, false);
    w.frameGeometry = { x: area.x, y: area.y, width: area.width, height: bottom - area.y };
}

function restore() {
    if (!saved) return;
    var s = saved;
    saved = null;
    if (s.maximized) s.win.setMaximize(true, true);
    else s.win.frameGeometry = s.geom;
}

registerShortcut("DeckWheelOskShrink", "deck-wheel: make room for the on-screen keyboard", "", shrink);
registerShortcut("DeckWheelOskRestore", "deck-wheel: restore after the on-screen keyboard", "", restore);
