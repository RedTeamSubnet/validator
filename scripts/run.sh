#!/usr/bin/env bash
set -euo pipefail


## --- Base --- ##
_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-"$0"}")" >/dev/null 2>&1 && pwd -P)"
_PROJECT_DIR="$(cd "${_SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
cd "${_PROJECT_DIR}" || exit 2


# shellcheck disable=SC1091
[ -f .env ] && . .env


if ! command -v python >/dev/null 2>&1; then
	echo "[ERROR]: Not found 'python' command, please install it first!" >&2
	exit 1
fi
## --- Base --- ##


_use_centralized_param=""
if [ "${RT_VALIDATOR_USE_CENTRALIZED:-}" = "true" ]; then
	_use_centralized_param="--validator.use_centralized_scoring"
fi

_logging_param=""
if [ "${RT_VALIDATOR_LOG_LEVEL:-}" = "debug" ]; then
	_logging_param="--logging.debug"
elif [ "${RT_VALIDATOR_LOG_LEVEL:-}" = "trace" ]; then
	_logging_param="--logging.trace"
fi


## --- Main --- ##
main()
{
	echo "[INFO]: Starting agent validator..."
	python -u -m src.validator  || exit 2

	echo "[OK]: Done."
	exit 0
}

main
## --- Main --- ##
