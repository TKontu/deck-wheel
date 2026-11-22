#!/bin/bash
# Install deck-wheel for the current user (Steam Deck, Desktop Mode).
# Everything goes under $HOME, so it survives SteamOS updates.
set -euo pipefail
cd "$(dirname "$0")"

install -Dm644 deck_wheel.py ~/.local/share/deck-wheel/deck_wheel.py
install -Dm644 deck-wheel.service ~/.config/systemd/user/deck-wheel.service

# KWin rule: keep the wheel window centred, on top, borderless and unable to take focus
R=deck-wheel-overlay
k() { kwriteconfig6 --file kwinrulesrc --group "$R" --key "$1" "$2"; }
k Description "deck-wheel overlay"
k wmclass io.github.deckwheel; k wmclassmatch 1; k wmclasscomplete false
k above true; k aboverule 2
k acceptfocus false; k acceptfocusrule 2
k noborder true; k noborderrule 2
k skiptaskbar true; k skiptaskbarrule 2
k skippager true; k skippagerrule 2
k skipswitcher true; k skipswitcherrule 2
k position 380,140; k positionrule 2      # centred on the Deck's 1280x800 screen
k size 520,520; k sizerule 2
k fsplevel 0; k fsplevelrule 2
k types 1
rules=$(kreadconfig6 --file kwinrulesrc --group General --key rules)
case ",$rules," in *",$R,"*) ;; *) rules="${rules:+$rules,}$R" ;; esac
kwriteconfig6 --file kwinrulesrc --group General --key rules "$rules"
kwriteconfig6 --file kwinrulesrc --group General --key count "$(tr ',' '\n' <<<"$rules" | grep -c .)"
qdbus6 org.kde.KWin /KWin reconfigure || true

systemctl --user daemon-reload
systemctl --user enable --now deck-wheel.service
systemctl --user restart deck-wheel.service
echo "deck-wheel installed and running."
echo "Next: unbind the sticks and R1 in Steam's Desktop layout (see README, 'Steam layout')."
