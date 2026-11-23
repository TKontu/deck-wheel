#!/bin/bash
# Install deck-wheel for the current user (Steam Deck, Desktop Mode).
# Everything goes under $HOME, so it survives SteamOS updates.
set -euo pipefail
cd "$(dirname "$0")"

install -Dm644 deck_wheel.py ~/.local/share/deck-wheel/deck_wheel.py
install -Dm644 deck-wheel.service ~/.config/systemd/user/deck-wheel.service

# KWin script that makes room for Steam's on-screen keyboard
mkdir -p ~/.local/share/kwin/scripts
rm -rf ~/.local/share/kwin/scripts/deckwheel-osk
cp -r kwin/deckwheel-osk ~/.local/share/kwin/scripts/
kwriteconfig6 --file kwinrc --group Plugins --key deckwheel-oskEnabled true

# KWin rules: one per wheel window (matched by title), placed top-left / top-right so the
# wheels sit next to their stick and above Steam's on-screen keyboard; on top, borderless,
# never taking focus.
rule() {   # $1 = rule id, $2 = window title, $3 = position x,y
  local R=$1
  k() { kwriteconfig6 --file kwinrulesrc --group "$R" --key "$1" "$2"; }
  k Description "deck-wheel ${2#deck-wheel-} wheel"
  k wmclass io.github.deckwheel; k wmclassmatch 1; k wmclasscomplete false
  k title "$2"; k titlematch 1
  k above true; k aboverule 2
  k acceptfocus false; k acceptfocusrule 2
  k noborder true; k noborderrule 2
  k skiptaskbar true; k skiptaskbarrule 2
  k skippager true; k skippagerrule 2
  k skipswitcher true; k skipswitcherrule 2
  k position "$3"; k positionrule 2
  k size 360,360; k sizerule 2
  k fsplevel 0; k fsplevelrule 2
  k desktops ""; k desktopsrule 2     # on all virtual desktops (else showing it switches back)
  k types 1
}
rule deck-wheel-left  deck-wheel-left  12,12     # Deck screen is 1280x800; keyboard starts ~y=378
rule deck-wheel-right deck-wheel-right 908,12
kwriteconfig6 --file kwinrulesrc --group deck-wheel-overlay --delete 2>/dev/null || true
rules=$(kreadconfig6 --file kwinrulesrc --group General --key rules | tr ',' '\n' | grep -vx 'deck-wheel-overlay' | paste -sd,)
for R in deck-wheel-left deck-wheel-right; do
  case ",$rules," in *",$R,"*) ;; *) rules="${rules:+$rules,}$R" ;; esac
done
kwriteconfig6 --file kwinrulesrc --group General --key rules "$rules"
kwriteconfig6 --file kwinrulesrc --group General --key count "$(tr ',' '\n' <<<"$rules" | grep -c .)"
qdbus6 org.kde.KWin /KWin reconfigure || true

systemctl --user daemon-reload
systemctl --user enable --now deck-wheel.service
systemctl --user restart deck-wheel.service
echo "deck-wheel installed and running."
echo "Next: unbind the sticks and R1 in Steam's Desktop layout (see README, 'Steam layout')."
