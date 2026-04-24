#!/usr/bin/env bash
set -euo pipefail

readonly REPO_URL="https://github.com/openwall/john.git"
readonly DEFAULT_SRC_DIR="${HOME}/.local/src/john-jumbo"
readonly DEFAULT_BIN_DIR="${HOME}/.local/bin"
readonly HELPER_PACKAGES=("git")
readonly BUILD_PACKAGES=(
  "build-essential"
  "pkg-config"
  "libssl-dev"
  "zlib1g-dev"
  "libbz2-dev"
  "libgmp-dev"
  "yasm"
)

SRC_DIR="${DEFAULT_SRC_DIR}"
BIN_DIR="${DEFAULT_BIN_DIR}"
KEEP_BUILD_DEPS=0
LINK_LOCAL_BIN=1

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Build John Jumbo locally so gmail-cleanup can use john + pdf2john.

Usage:
  scripts/install-john-jumbo-local.sh [options]

Options:
  --src-dir PATH         Clone/build under PATH instead of ~/.local/src/john-jumbo
  --bin-dir PATH         Symlink john/pdf2john into PATH instead of ~/.local/bin
  --keep-build-deps      Keep any missing apt build packages this script installs
  --no-link-local-bin    Do not create ~/.local/bin symlinks
  -h, --help             Show this help

Notes:
  - This installer targets Debian/Ubuntu systems with apt-get.
  - It never writes into system directories.
  - If it installs missing build-only apt packages, it purges only those same
    packages at the end unless --keep-build-deps is set.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src-dir)
      [[ $# -ge 2 ]] || die "--src-dir needs a value"
      SRC_DIR="$2"
      shift 2
      ;;
    --bin-dir)
      [[ $# -ge 2 ]] || die "--bin-dir needs a value"
      BIN_DIR="$2"
      shift 2
      ;;
    --keep-build-deps)
      KEEP_BUILD_DEPS=1
      shift
      ;;
    --no-link-local-bin)
      LINK_LOCAL_BIN=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

if [[ "$(uname -s)" != "Linux" ]]; then
  die "this installer currently targets Linux systems with apt-get"
fi

command -v apt-get >/dev/null 2>&1 || die "apt-get not found"
command -v dpkg-query >/dev/null 2>&1 || die "dpkg-query not found"

if [[ ${EUID} -eq 0 ]]; then
  SUDO=()
elif command -v sudo >/dev/null 2>&1; then
  SUDO=(sudo)
else
  die "sudo is required when not running as root"
fi

package_installed() {
  local package="$1"
  dpkg-query -W -f='${Status}\n' "$package" 2>/dev/null | grep -qx 'install ok installed'
}

safe_symlink() {
  local source="$1"
  local target="$2"
  if [[ -L "$target" ]]; then
    local existing
    existing="$(readlink -f "$target")"
    if [[ "$existing" == "$(readlink -f "$source")" ]]; then
      return 0
    fi
    die "refusing to overwrite existing symlink: $target -> $existing"
  fi
  if [[ -e "$target" ]]; then
    die "refusing to overwrite existing file: $target"
  fi
  ln -s "$source" "$target"
}

write_john_wrapper() {
  local source="$1"
  local target="$2"
  local resolved_source
  local john_home
  local marker="# gmail-cleanup-managed-john-wrapper"
  resolved_source="$(readlink -f "$source")"
  john_home="$(dirname "$resolved_source")"

  if [[ -L "$target" ]]; then
    local existing
    existing="$(readlink -f "$target")"
    if [[ "$existing" == "$resolved_source" ]]; then
      rm -f "$target"
    else
      die "refusing to overwrite existing symlink: $target -> $existing"
    fi
  elif [[ -e "$target" ]]; then
    if ! grep -Fqx "$marker" "$target" 2>/dev/null; then
      die "refusing to overwrite existing file: $target"
    fi
  fi

  cat >"$target" <<EOF
#!/usr/bin/env bash
$marker
set -euo pipefail
export JOHN="$john_home"
exec "$resolved_source" "\$@"
EOF
  chmod +x "$target"
}

build_nproc() {
  local detected
  detected="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
  if [[ -n "$detected" && "$detected" =~ ^[0-9]+$ && "$detected" -gt 0 ]]; then
    printf '%s\n' "$detected"
    return 0
  fi
  if command -v nproc >/dev/null 2>&1; then
    nproc
    return 0
  fi
  printf '4\n'
}

installed_build_packages=()
missing_helper_packages=()
missing_build_packages=()

for package in "${HELPER_PACKAGES[@]}"; do
  if ! package_installed "$package"; then
    missing_helper_packages+=("$package")
  fi
done

for package in "${BUILD_PACKAGES[@]}"; do
  if ! package_installed "$package"; then
    missing_build_packages+=("$package")
  fi
done

cleanup_build_packages() {
  if [[ "${KEEP_BUILD_DEPS}" -eq 1 ]]; then
    return 0
  fi
  if [[ ${#installed_build_packages[@]} -eq 0 ]]; then
    return 0
  fi
  log
  log "Cleaning up build-only apt packages installed by this run:"
  log "  ${installed_build_packages[*]}"
  "${SUDO[@]}" apt-get purge -y "${installed_build_packages[@]}"
  "${SUDO[@]}" apt-get autoremove -y
}

cleanup_called=0
cleanup_once() {
  if [[ "${cleanup_called}" -eq 1 ]]; then
    return 0
  fi
  cleanup_called=1
  cleanup_build_packages
}

trap cleanup_once EXIT

if [[ ${#missing_helper_packages[@]} -gt 0 || ${#missing_build_packages[@]} -gt 0 ]]; then
  log "Installing apt packages needed to build John Jumbo..."
  "${SUDO[@]}" apt-get update
fi

if [[ ${#missing_helper_packages[@]} -gt 0 ]]; then
  log "Installing helper packages:"
  log "  ${missing_helper_packages[*]}"
  "${SUDO[@]}" apt-get install -y --no-install-recommends "${missing_helper_packages[@]}"
fi

if [[ ${#missing_build_packages[@]} -gt 0 ]]; then
  log "Installing build packages:"
  log "  ${missing_build_packages[*]}"
  "${SUDO[@]}" apt-get install -y --no-install-recommends "${missing_build_packages[@]}"
  installed_build_packages=("${missing_build_packages[@]}")
fi

mkdir -p "$(dirname "$SRC_DIR")"

if [[ -d "$SRC_DIR" && ! -d "$SRC_DIR/.git" ]]; then
  die "source directory exists but is not a git checkout: $SRC_DIR"
fi

if [[ -d "$SRC_DIR/.git" ]]; then
  log "Updating existing John Jumbo checkout in $SRC_DIR..."
  git -C "$SRC_DIR" pull --ff-only
else
  log "Cloning John Jumbo into $SRC_DIR..."
  git clone --depth=1 "$REPO_URL" "$SRC_DIR"
fi

RUN_DIR="$SRC_DIR/run"
BUILD_DIR="$SRC_DIR/src"

log "Building John Jumbo..."
(
  cd "$BUILD_DIR"
  ./configure
  make -s clean
  make -sj"$(build_nproc)"
)

JOHN_BIN="$RUN_DIR/john"
[[ -x "$JOHN_BIN" ]] || die "build finished but john binary is missing: $JOHN_BIN"

PDF2JOHN_SOURCE=""
for candidate in "$RUN_DIR/pdf2john" "$RUN_DIR/pdf2john.py" "$RUN_DIR/pdf2john.pl"; do
  if [[ -f "$candidate" ]]; then
    PDF2JOHN_SOURCE="$candidate"
    break
  fi
done
[[ -n "$PDF2JOHN_SOURCE" ]] || die "build finished but no pdf2john helper was found under $RUN_DIR"

if [[ "${LINK_LOCAL_BIN}" -eq 1 ]]; then
  mkdir -p "$BIN_DIR"
  write_john_wrapper "$JOHN_BIN" "$BIN_DIR/john"
  safe_symlink "$PDF2JOHN_SOURCE" "$BIN_DIR/pdf2john"
  if [[ "$PDF2JOHN_SOURCE" == *.py ]]; then
    safe_symlink "$PDF2JOHN_SOURCE" "$BIN_DIR/pdf2john.py"
  elif [[ "$PDF2JOHN_SOURCE" == *.pl ]]; then
    safe_symlink "$PDF2JOHN_SOURCE" "$BIN_DIR/pdf2john.pl"
  fi
fi

log
log "Build verification:"
"$JOHN_BIN" --list=build-info >/dev/null
log "  john: $JOHN_BIN"
log "  pdf2john: $PDF2JOHN_SOURCE"
if [[ "${LINK_LOCAL_BIN}" -eq 1 ]]; then
  log "  local links: $BIN_DIR/john $BIN_DIR/pdf2john"
fi

cleanup_once
trap - EXIT

cat <<EOF

John Jumbo is ready.

Recommended PATH update for your shell startup:
  export PATH="$BIN_DIR:$RUN_DIR:\$PATH"

Quick checks:
  command -v john
  command -v pdf2john
  john --list=build-info | head

gmail-cleanup should then prefer the John backend automatically when both
john and pdf2john resolve on PATH.
EOF
