#!/usr/bin/env bash
# Remove the maj-scripts copy installed by install.sh, without removing dependencies
# or maj-scripts's configuration and downloaded data.
#
#   curl -fsSL https://raw.githubusercontent.com/majal/maj-scripts/main/uninstall.sh | bash
set -euo pipefail

MAJ_SCRIPTS_HOME="${MAJ_SCRIPTS_HOME:-$HOME/.maj-scripts}"
MARKER="# maj-scripts PATH (added by maj-scripts's install.sh)"
TOOLS=(ffcut gmail-cleanup pdflat pdflat-auto pdflat-single printing-mode thumb ubuntu-hibernate wh whisper)

die() { printf 'maj-scripts uninstall: %s\n' "$1" >&2; exit 1; }
note() { printf '%s\n' "$1"; }

safe_install_dir() {
    case "$MAJ_SCRIPTS_HOME" in
        ""|/|"$HOME") die "refusing unsafe MAJ_SCRIPTS_HOME: ${MAJ_SCRIPTS_HOME:-<empty>}" ;;
    esac
}

is_installer_owned() {
    # The normal location is the legacy-safe target for installs made before
    # this uninstaller existed.  A custom path needs stronger evidence.
    [ "$MAJ_SCRIPTS_HOME" = "$HOME/.maj-scripts" ] && return 0
    [ -f "$MAJ_SCRIPTS_HOME/maj-scripts-update" ] || return 1
    local tool
    for tool in "${TOOLS[@]}"; do
        [ -f "$MAJ_SCRIPTS_HOME/$tool" ] || return 1
    done
}

remove_recorded_dependencies() {
    local state_file="$1" manager dependency
    [ -f "$state_file" ] || return 0
    manager="$(awk -F= '$1 == "dependency_manager" { print $2; exit }' "$state_file")"
    case "$manager" in
        brew|apt-get|dnf|pacman|apk) ;;
        *) note "Kept dependencies: no recognized installer record."; return 0 ;;
    esac
    while IFS= read -r dependency; do
        [ -n "$dependency" ] || continue
        note "Removing installer-added dependency: $dependency"
        case "$manager" in
            brew) brew uninstall "$dependency" || note "Could not remove $dependency; leaving it installed." ;;
            apt-get) sudo apt-get remove -y "$dependency" || note "Could not remove $dependency; leaving it installed." ;;
            dnf) sudo dnf remove -y "$dependency" || note "Could not remove $dependency; leaving it installed." ;;
            pacman) sudo pacman -Rns --noconfirm "$dependency" || note "Could not remove $dependency; leaving it installed." ;;
            apk) sudo apk del "$dependency" || note "Could not remove $dependency; leaving it installed." ;;
        esac
    done < <(awk -F= '$1 == "dependency" { print $2 }' "$state_file")
}

remove_path_block() {
    local rc="$1" tmp
    [ -f "$rc" ] || return 0
    tmp="${rc}.maj-scripts-uninstall.$$"
    awk -v marker="$MARKER" '
        $0 == marker {
            if (getline next_line && next_line == "export PATH=\"" ENVIRON["MAJ_SCRIPTS_HOME"] ":$PATH\"") next
            print $0
            if (next_line != "") print next_line
            next
        }
        { print }
    ' "$rc" >"$tmp"
    if ! cmp -s "$rc" "$tmp"; then
        mv "$tmp" "$rc"
        note "Removed maj-scripts from $rc"
    else
        rm -f "$tmp"
    fi
}

safe_install_dir
export MAJ_SCRIPTS_HOME

if [ -e "$MAJ_SCRIPTS_HOME" ] && ! is_installer_owned; then
    die "refusing to remove custom MAJ_SCRIPTS_HOME without an installer footprint: $MAJ_SCRIPTS_HOME"
fi

state_copy="$(mktemp "${TMPDIR:-/tmp}/maj-scripts-install-state.XXXXXX")"
if [ -f "$MAJ_SCRIPTS_HOME/.maj-scripts-install-state" ]; then
    cp "$MAJ_SCRIPTS_HOME/.maj-scripts-install-state" "$state_copy"
fi

for rc in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile" "$HOME/.bashrc"; do
    remove_path_block "$rc"
done

if [ -e "$MAJ_SCRIPTS_HOME" ]; then
    rm -rf -- "$MAJ_SCRIPTS_HOME"
    note "Removed installed maj-scripts copy at $MAJ_SCRIPTS_HOME"
else
    note "No installed maj-scripts copy found at $MAJ_SCRIPTS_HOME"
fi

remove_recorded_dependencies "$state_copy"
rm -f "$state_copy"
note "Kept your scripts' own settings and data. Existing dependencies not recorded as installer-added were kept."
