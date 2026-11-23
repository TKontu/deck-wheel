// deck-wheel OSK room: make space for the Steam on-screen keyboard.
// deck-wheel watches Steam's log and invokes the Shrink/Restore shortcuts when the keyboard
// opens/closes. While it is open, this script follows focus: the newly active window gets
// the room above the keyboard (the previous one is restored), and deck-wheel is asked to
// reopen Steam's keyboard, which otherwise keeps typing at the window it was opened on.
var KEYBOARD_TOP = 0.47;   // the Steam keyboard covers the screen below ~47 % of its height
var oskOpen = false;
var saved = null;          // { win, geom, maximized } of the window we shrank
var target = null;         // window the keyboard is meant for
var targetLost = false;    // focus left the target (panel, desktop, another window) since
                           // the keyboard last (re)opened for it

function usable(w) {
    return w && w.normalWindow && !w.fullScreen &&
        String(w.resourceClass).indexOf("steam") === -1 &&
        String(w.resourceClass) !== "io.github.deckwheel";
}

function shrinkWindow(w) {
    if (saved || !usable(w)) return;
    var area = workspace.clientArea(KWin.MaximizeArea, w);
    var g = w.frameGeometry;
    var screen = workspace.clientArea(KWin.FullScreenArea, w);
    var bottom = screen.y + Math.round(screen.height * KEYBOARD_TOP) - 6;
    // exactly our shrunk shape = a window left shrunk earlier (missed restore): treat it as
    // maximized so closing the keyboard maximizes it again instead of leaving it stuck
    var leftShrunk = Math.abs(g.x - area.x) <= 2 && Math.abs(g.y - area.y) <= 2 &&
        Math.abs(g.width - area.width) <= 2 && Math.abs(g.height - (bottom - area.y)) <= 2;
    if (!leftShrunk && g.y + g.height <= bottom) return;     // already clear of the keyboard
    saved = {
        win: w,
        geom: { x: g.x, y: g.y, width: g.width, height: g.height },
        maximized: leftShrunk || (g.width >= area.width - 2 && g.height >= area.height - 2)
    };
    if (leftShrunk) return;                                   // already the right size
    if (saved.maximized) w.setMaximize(false, false);
    w.frameGeometry = { x: area.x, y: area.y, width: area.width, height: bottom - area.y };
}

function restoreWindow() {
    if (!saved) return;
    var s = saved;
    saved = null;
    if (s.maximized) s.win.setMaximize(true, true);
    else s.win.frameGeometry = s.geom;
}

function shrink() {                 // Steam keyboard opened
    oskOpen = true;
    targetLost = false;
    if (usable(workspace.activeWindow)) target = workspace.activeWindow;
    shrinkWindow(target);
}

function restore() {                // Steam keyboard closed
    oskOpen = false;
    restoreWindow();
}

function retargetKeyboard() {
    // ask deck-wheel to reopen Steam's keyboard so it types into the active window
    targetLost = false;
    callDBus("io.github.deckwheel", "/io/github/deckwheel", "org.gtk.Actions", "Activate",
             "osk-retarget", [], {});
}

workspace.windowActivated.connect(function (w) {
    if (!oskOpen) return;
    if (w && String(w.resourceClass).indexOf("steam") !== -1) return;   // Steam's own windows
    if (!usable(w)) {                // panel, desktop, nothing: the keyboard loses its target
        if (w !== target) targetLost = true;
        return;
    }
    if (w === target) {              // back to the same window: reopen only if focus had left
        if (targetLost) retargetKeyboard();
        return;
    }
    restoreWindow();                 // a different window: give it the room and the keyboard
    target = w;
    shrinkWindow(w);
    retargetKeyboard();
});

workspace.windowRemoved.connect(function (w) {
    if (saved && saved.win === w) saved = null;
    if (target === w) target = null;
});

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
