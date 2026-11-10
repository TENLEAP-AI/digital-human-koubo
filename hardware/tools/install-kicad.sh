#!/bin/bash
# Install KiCad 9 (schematic + PCB + command-line DRC/ERC/export) on Ubuntu 24.04.
# Run as root. Safe to run again: it only installs what is missing.
#
# Why the KiCad PPA: Ubuntu 24.04 ships KiCad 7.0.11, which has no command-line
# DRC or ERC. The 3D model package (3.3 GB) is left out on purpose; add
# kicad-packages3d to the install line if STEP export with models is needed.
set -euo pipefail

KEY=/etc/apt/keyrings/kicad-9.gpg
FPR=FDA854F61C4D0D9572BB95E5245D5502FAD7A805   # "Launchpad PPA for KiCad"
export DEBIAN_FRONTEND=noninteractive

mkdir -p /etc/apt/keyrings
curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$FPR" -o /tmp/kicad-ppa.asc
gpg --dearmor --yes -o "$KEY" /tmp/kicad-ppa.asc
echo "deb [signed-by=$KEY] https://ppa.launchpadcontent.net/kicad/kicad-9.0-releases/ubuntu noble main" \
  > /etc/apt/sources.list.d/kicad-9.list
apt-get update -qq

# Refuse to fall back to the distro's KiCad 7 if the PPA did not load.
CAND=$(apt-cache policy kicad | sed -n 's/^ *Candidate: //p')
case "$CAND" in 9.*) ;; *) echo "apt offers KiCad '$CAND', not 9.x; check the PPA" >&2; exit 1 ;; esac
apt-get install -y -qq --no-install-recommends kicad kicad-symbols kicad-footprints kicad-templates

# Global library tables: without them ERC cannot resolve symbol/footprint libraries.
CFG="${HOME:-/root}/.config/kicad/9.0"
mkdir -p "$CFG"
cp --update=none /usr/share/kicad/template/sym-lib-table /usr/share/kicad/template/fp-lib-table "$CFG"/

echo "kicad-cli $(kicad-cli version)"
echo "Note: KiCad's Python module (pcbnew) is built for the system Python: use /usr/bin/python3.12, not python3."
