#!/usr/bin/env bash
# Install the kanidm CLI at a pinned version (must match the Kanidm server image).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -ge 1 && -n "${1:-}" ]]; then
  KANIDM_VERSION="$1"
elif [[ -n "${KANIDM_VERSION:-}" ]]; then
  :
else
  KANIDM_VERSION="$(
    python3 -c "import pathlib, re; m=re.search(r'^KANIDM_VERSION = \"([^\"]+)\"', pathlib.Path('${repo_root}/tests/helpers.py').read_text()); assert m; print(m.group(1))"
  )"
fi

INSTALL_DIR="${KANIDM_CLI_INSTALL_DIR:-${repo_root}/.bin}"
mkdir -p "${INSTALL_DIR}"
BIN="${INSTALL_DIR}/kanidm"

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

echo "Configuring kanidm PPA (Ubuntu) for CLI ${KANIDM_VERSION}..."
curl -fsSL "https://kanidm.github.io/kanidm_ppa/kanidm_ppa.asc" \
  | "${SUDO[@]}" tee /etc/apt/trusted.gpg.d/kanidm_ppa.asc >/dev/null
curl -fsSL --compressed "https://kanidm.github.io/kanidm_ppa/kanidm_ppa.list" \
  | grep "$( ( . /etc/os-release && echo "$VERSION_CODENAME") )" | grep stable \
  | "${SUDO[@]}" tee /etc/apt/sources.list.d/kanidm_ppa.list >/dev/null

"${SUDO[@]}" apt-get update -qq

PKG_VERSION="$(
  apt-cache madison kanidm 2>/dev/null \
    | awk -v want="${KANIDM_VERSION}" '$3 ~ "^"want"-" {print $3; exit}'
)"
if [[ -z "${PKG_VERSION}" ]]; then
  echo "ERROR: no kanidm Debian package matching ${KANIDM_VERSION} in the kanidm PPA." >&2
  echo "Rolling 'stable' installs the newest release and must not be used for e2e." >&2
  exit 1
fi

echo "Installing kanidm=${PKG_VERSION}..."
DEBIAN_FRONTEND=noninteractive "${SUDO[@]}" apt-get install -y "kanidm=${PKG_VERSION}"

cp -f "$(command -v kanidm)" "${BIN}"
chmod +x "${BIN}"

CLI_VERSION_LINE="$("${BIN}" --version 2>&1 | head -1)"
echo "Installed kanidm CLI: ${CLI_VERSION_LINE}"

want_mm="$(echo "${KANIDM_VERSION}" | awk -F. '{print $1"."$2}')"
got_mm="$(echo "${CLI_VERSION_LINE}" | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 | awk -F. '{print $1"."$2}')"

if [[ -z "${got_mm}" || "${got_mm}" != "${want_mm}" ]]; then
  echo "ERROR: kanidm CLI major.minor is ${got_mm:-unknown}; server under test is ${want_mm} (${KANIDM_VERSION})." >&2
  exit 1
fi

if [[ -n "${GITHUB_ENV:-}" ]]; then
  echo "KANIDM_EXEC=${BIN}" >> "${GITHUB_ENV}"
  echo "KANIDM_CLI_VERSION=${KANIDM_VERSION}" >> "${GITHUB_ENV}"
fi

echo "kanidm CLI ${KANIDM_VERSION} (${PKG_VERSION}) installed at ${BIN}"
