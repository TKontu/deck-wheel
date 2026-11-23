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

// ---- window cycling for the deck-wheel "Next window" / "Prev window" slots ----
// Alt+Tab uses most-recently-used order, so repeating it only toggles between two windows.
// These walk all normal windows on the current desktop in a fixed order (order opened).
var order = [];                      // windows in the order they appeared

function trackable(w) {
    return w && w.normalWindow && !w.skipSwitcher &&
        String(w.resourceClass) !== "io.github.deckwheel";
}
workspace.windowList().forEach(function (w) { if (trackable(w)) order.push(w); });
workspace.windowAdded.connect(function (w) { if (trackable(w)) order.push(w); });
workspace.windowRemoved.connect(function (w) {
    var i = order.indexOf(w);
    if (i >= 0) order.splice(i, 1);
});

function onCurrentDesktop(w) {
    return w.onAllDesktops || w.desktops.indexOf(workspace.currentDesktop) >= 0;
}

function cycle(step) {
    var list = order.filter(onCurrentDesktop);
    if (list.length === 0) return;
    var i = list.indexOf(workspace.activeWindow);
    var next = list[(i < 0 ? 0 : i + step + list.length) % list.length];
    if (next.minimized) next.minimized = false;
    workspace.activeWindow = next;
}

registerShortcut("DeckWheelNextWindow", "deck-wheel: next window (fixed order)", "", function () { cycle(1); });
registerShortcut("DeckWheelPrevWindow", "deck-wheel: previous window (fixed order)", "", function () { cycle(-1); });
