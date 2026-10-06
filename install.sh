#!/usr/bin/env bash
# maj-scripts installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/majal/maj-scripts/main/install.sh | bash
#
# Installs Python/ffmpeg/git if missing, downloads maj-scripts to ~/.maj-scripts, adds it
# to your shell PATH, and sets up a `maj-scripts-update` command. Safe to re-run -
# re-running this script (or `maj-scripts-update`) updates maj-scripts in place.
set -euo pipefail

MAJ_SCRIPTS_HOME="${MAJ_SCRIPTS_HOME:-$HOME/.maj-scripts}"
REPO_URL="https://github.com/majal/maj-scripts"
TARBALL_URL="${REPO_URL}/archive/refs/heads/main.tar.gz"
TOOLS=(ffcut gmail-cleanup pdflat pdflat-auto pdflat-single printing-mode thumb ubuntu-hibernate wh whisper)
INSTALLED_DEPENDENCIES=()
DEPENDENCY_MANAGER=""

c_bold()   { printf '\033[1m%s\033[0m\n' "$1"; }
c_green()  { printf '\033[32m%s\033[0m\n' "$1"; }
c_yellow() { printf '\033[33m%s\033[0m\n' "$1"; }
c_red()    { printf '\033[31m%s\033[0m\n' "$1" >&2; }
step()     { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# python3 merely existing isn't enough: macOS's /usr/bin/python3 is 3.9, and
# whisper imports tomllib (Python 3.11+).
python_ok() {
    command_exists python3 &&
        python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

safe_install_dir() {
    case "$MAJ_SCRIPTS_HOME" in
        ""|/|"$HOME")
            c_red "Refusing unsafe MAJ_SCRIPTS_HOME: ${MAJ_SCRIPTS_HOME:-<empty>}"
            exit 1
            ;;
    esac
}

on_error() {
    c_red "Something went wrong partway through setup."
    c_red "You can re-run this installer any time - it's safe to repeat."
    c_red "If it keeps failing, please open an issue: ${REPO_URL}/issues"
}
trap on_error ERR

step "Setting up maj-scripts"
safe_install_dir

# --- Dependencies ---
ensure_macos_deps() {
    if ! command_exists brew; then
        step "Installing Homebrew (needed to install Python/ffmpeg on macOS)"
        c_yellow "Homebrew's own installer may ask for your Mac login password - that's expected."
        NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
        if [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi
    fi

    step "Checking Python, ffmpeg, git"
    local missing=()
    python_ok || missing+=(python3)
    command_exists ffmpeg || missing+=(ffmpeg)
    command_exists git || missing+=(git)
    if [ "${#missing[@]}" -gt 0 ]; then
        c_yellow "Installing via Homebrew: ${missing[*]}"
        brew install "${missing[@]}"
        DEPENDENCY_MANAGER="brew"
        INSTALLED_DEPENDENCIES+=("${missing[@]}")
    else
        c_green "Already have python3, ffmpeg, and git."
    fi
}

ensure_linux_deps() {
    step "Checking Python, ffmpeg, git"
    local missing=()
    python_ok || missing+=(python3)
    command_exists ffmpeg || missing+=(ffmpeg)
    command_exists git || missing+=(git)

    if [ "${#missing[@]}" -eq 0 ]; then
        c_green "Already have python3, ffmpeg, and git."
        return
    fi

    c_yellow "Installing: ${missing[*]} (this needs your sudo password)"
    if command_exists apt-get; then
        sudo apt-get update -y
        sudo apt-get install -y "${missing[@]}"
        DEPENDENCY_MANAGER="apt-get"
    elif command_exists dnf; then
        sudo dnf install -y "${missing[@]}"
        DEPENDENCY_MANAGER="dnf"
    elif command_exists pacman; then
        sudo pacman -Sy --noconfirm "${missing[@]}"
        DEPENDENCY_MANAGER="pacman"
    elif command_exists apk; then
        sudo apk add "${missing[@]}"
        DEPENDENCY_MANAGER="apk"
    else
        c_red "Couldn't detect apt/dnf/pacman/apk. Please install manually: ${missing[*]}"
        c_red "Then re-run this installer."
        exit 1
    fi
    INSTALLED_DEPENDENCIES+=("${missing[@]}")
    if ! python_ok; then
        c_red "Your system's Python is older than 3.11, which maj-scripts needs."
        c_red "Install a newer one (for example via pyenv or your distro's python3.11+ package), then re-run this installer."
        exit 1
    fi
}

os="$(uname -s)"
case "$os" in
    Darwin) ensure_macos_deps ;;
    Linux) ensure_linux_deps ;;
    *)
        c_red "The maj-scripts installer supports macOS and Linux. For Windows, use install.ps1 instead:"
        c_red "  irm https://raw.githubusercontent.com/majal/maj-scripts/main/install.ps1 | iex"
        exit 1
        ;;
esac

# --- Fetch maj-scripts ---
step "Getting maj-scripts"
if command_exists git; then
    if [ -d "$MAJ_SCRIPTS_HOME/.git" ]; then
        c_yellow "Updating existing install at $MAJ_SCRIPTS_HOME"
        git -C "$MAJ_SCRIPTS_HOME" fetch -q origin main
        # Named explicitly rather than relying only on .gitignore: an
        # existing install whose checked-out .gitignore predates a given
        # installer-generated file (as .maj-scripts-install-state did until this
        # fix) would otherwise see it as an untracked "local change" and
        # never update again to PICK UP that .gitignore fix - the exact bug
        # this line fixes. Keep this list and .gitignore in sync.
        untracked_files="$(git -C "$MAJ_SCRIPTS_HOME" ls-files --others --exclude-standard | grep -vE '^(maj-scripts-update|\.maj-scripts-install-state)$' || true)"
        if ! git -C "$MAJ_SCRIPTS_HOME" diff --quiet ||
           ! git -C "$MAJ_SCRIPTS_HOME" diff --cached --quiet ||
           [ -n "$untracked_files" ]; then
            c_yellow "Local changes found; leaving the existing install untouched."
            c_yellow "Commit, stash, or remove them, then run maj-scripts-update again."
        elif ! git -C "$MAJ_SCRIPTS_HOME" merge --ff-only origin/main; then
            c_yellow "Could not fast-forward the existing install; leaving it untouched."
            c_yellow "Resolve its Git state, then run maj-scripts-update again."
        fi
    else
        if [ -e "$MAJ_SCRIPTS_HOME" ]; then
            c_red "Install path exists but is not a maj-scripts Git checkout: $MAJ_SCRIPTS_HOME"
            c_red "Choose an empty MAJ_SCRIPTS_HOME or move the existing directory yourself."
            exit 1
        fi
        git clone -q "${REPO_URL}.git" "$MAJ_SCRIPTS_HOME"
    fi
else
    if [ -e "$MAJ_SCRIPTS_HOME" ]; then
        c_red "Install path already exists and Git is unavailable: $MAJ_SCRIPTS_HOME"
        c_red "Install Git, or choose an empty MAJ_SCRIPTS_HOME."
        exit 1
    fi
    mkdir -p "$MAJ_SCRIPTS_HOME"
    curl -fsSL "$TARBALL_URL" | tar -xz -C "$MAJ_SCRIPTS_HOME" --strip-components=1
fi

for tool in "${TOOLS[@]}"; do
    [ -f "$MAJ_SCRIPTS_HOME/$tool" ] && chmod +x "$MAJ_SCRIPTS_HOME/$tool"
done

# Record only packages this installer added.  This lets uninstall.sh clean up a
# standalone install without guessing whether an existing dependency is used
# by another project.  Keep prior entries when an install is re-run.
if [ -n "$DEPENDENCY_MANAGER" ] && [ "${#INSTALLED_DEPENDENCIES[@]}" -gt 0 ]; then
    state_file="$MAJ_SCRIPTS_HOME/.maj-scripts-install-state"
    state_tmp="${state_file}.tmp.$$"
    {
        [ -f "$state_file" ] && cat "$state_file"
        printf 'dependency_manager=%s\n' "$DEPENDENCY_MANAGER"
        printf 'dependency=%s\n' "${INSTALLED_DEPENDENCIES[@]}"
    } | awk '!seen[$0]++' >"$state_tmp"
    mv "$state_tmp" "$state_file"
fi

# --- PATH ---
step "Adding maj-scripts to your PATH"
add_path_block() {
    local rc="$1"
    local marker="# maj-scripts PATH (added by maj-scripts's install.sh)"
    [ -f "$rc" ] || touch "$rc"
    if grep -qF "$marker" "$rc" 2>/dev/null ||
       grep -qF "$MAJ_SCRIPTS_HOME" "$rc" 2>/dev/null; then
        return 0
    fi
    {
        echo ""
        echo "$marker"
        echo "export PATH=\"$MAJ_SCRIPTS_HOME:\$PATH\""
    } >>"$rc"
    c_green "Added to $rc"
}

case "$(basename "${SHELL:-bash}")" in
    zsh)
        add_path_block "$HOME/.zshrc"
        ;;
    bash)
        # Bash reads only the first existing login file.  Do not create a
        # .bash_profile when .profile already owns the user's login setup.
        login_rc=""
        for login_rc in "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"; do
            if [ -e "$login_rc" ]; then
                add_path_block "$login_rc"
                break
            fi
        done
        if [ -z "$login_rc" ] || [ ! -e "$login_rc" ]; then
            add_path_block "$HOME/.profile"
        fi
        add_path_block "$HOME/.bashrc"
        ;;
    *)
        add_path_block "$HOME/.profile"
        ;;
esac
export PATH="$MAJ_SCRIPTS_HOME:$PATH"

# --- Update command ---
cat >"$MAJ_SCRIPTS_HOME/maj-scripts-update" <<UPDATE
#!/usr/bin/env bash
set -euo pipefail
curl -fsSL https://raw.githubusercontent.com/majal/maj-scripts/main/install.sh | bash
UPDATE
chmod +x "$MAJ_SCRIPTS_HOME/maj-scripts-update"

step "All set!"
c_green "maj-scripts is installed at $MAJ_SCRIPTS_HOME"
echo ""
echo "Open a new terminal window, then try:"
c_bold "  ffcut --help"
c_bold "  wh --help"
echo ""
echo "To update maj-scripts later, run:"
c_bold "  maj-scripts-update"
