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
IMAGE="kanidm/tools:${KANIDM_VERSION}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required to install kanidm CLI from ${IMAGE}" >&2
  exit 1
fi

echo "Pulling ${IMAGE}..."
docker pull "${IMAGE}"

cid="$(docker create "${IMAGE}")"
trap 'docker rm -f "${cid}" >/dev/null 2>&1 || true' EXIT
docker cp "${cid}:/sbin/kanidm" "${BIN}"
docker rm "${cid}"
trap - EXIT
chmod +x "${BIN}"

CLI_VERSION_LINE="$("${BIN}" --version 2>&1 | head -1)"
echo "Installed kanidm CLI: ${CLI_VERSION_LINE}"

want_mm="$(echo "${KANIDM_VERSION}" | awk -F. '{print $1"."$2}')"
got_mm="$(echo "${CLI_VERSION_LINE}" | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 | awk -F. '{print $1"."$2}')"

if [[ -z "${got_mm}" || "${got_mm}" != "${want_mm}" ]]; then
  echo "ERROR: kanidm CLI major.minor is ${got_mm:-unknown}; server under test is ${want_mm} (${KANIDM_VERSION})." >&2
  echo "PPA 'stable' and other rolling installs must not be used for e2e — pin with this script." >&2
  exit 1
fi

if [[ -n "${GITHUB_ENV:-}" ]]; then
  echo "KANIDM_EXEC=${BIN}" >> "${GITHUB_ENV}"
  echo "KANIDM_CLI_VERSION=${KANIDM_VERSION}" >> "${GITHUB_ENV}"
fi

echo "kanidm CLI ${KANIDM_VERSION} installed at ${BIN}"
