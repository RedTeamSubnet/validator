#!/usr/bin/env bash
set -euo pipefail


echo "[INFO]: Running '${RT_VALIDATOR_SLUG}' docker-entrypoint.sh..."


_wallet_dir="${RT_BTCLI_WALLET_DIR:-${RT_BTCLI_DATA_DIR:-/var/lib/sidecar-btcli}/wallets}"

_run()
{
	local _i=0
	while true; do
		if [ -d "${_wallet_dir}" ]; then
			break
		fi

		echo "[INFO]: Waiting for the wallet directory to be created..."
		_i=$((_i + 1))
		if [ "${_i}" -ge 60 ]; then
			echo "[ERROR]: Timeout waiting for the wallet directory to be created!" >&2
			exit 1
		fi

		sleep 1
	done

	if [ "${ENV:-}" != "PRODUCTION" ] && [ "${ENV:-}" != "STAGING" ]; then
		_i=0
		while true; do
			local _checkpoint_file_path="${RT_BTCLI_DATA_DIR:-/var/lib/sidecar-btcli}/${RT_BTCLI_CHECKPOINT_FNAME:-.checkpoint.txt}"
			if [ -f "${_checkpoint_file_path}" ]; then
				local _checkpoint_val=0
				_checkpoint_val=$(cat "${_checkpoint_file_path}")
				if [ "${_checkpoint_val}" -ge 4 ]; then
					break
				fi
			fi

			if [ $(( _i % 10 )) -eq 0 ]; then
				echo "[INFO]: Waiting for the wallets to be registered and ready..."
			fi
			_i=$((_i + 1))
			sleep 1
		done
	fi

	sleep 5
	echo "[INFO]: Starting ${RT_VALIDATOR_SLUG}..."
	exec sg docker "exec python -u -m validator"

	exit 0
}

_fix_root_wallet()
{
	if [ "${_wallet_dir#/root/}" != "${_wallet_dir}" ]; then
		echo "[WARN]: Wallet dir is under /root ('${_wallet_dir}'), temporarily fixing permissions to allow validator user access, but this is not recommended!"

		sudo chmod -c 755 /root || exit 2
	fi
}


main()
{
	umask 0002 || exit 2

	_fix_root_wallet

	sudo find "${_wallet_dir}" \
		"${RT_HOME_DIR}" \
		"${RT_VALIDATOR_CONFIGS_DIR}" \
		"${RT_VALIDATOR_DATA_DIR}" \
		"${RT_VALIDATOR_LOGS_DIR}" \
		"${RT_VALIDATOR_TMP_DIR}" \
		\( \
			-type d -name ".git" -o \
			-type d -name ".venv" -o \
			-type d -name "modules" -o \
			-type d -name "volumes" -o \
			-type l -name ".env" \
		\) -prune -o -print0 | \
			sudo xargs -0 chown -c "${USER}:${GROUP}" || exit 2

	find "${RT_VALIDATOR_DIR}" "${RT_VALIDATOR_CONFIGS_DIR}" "${RT_VALIDATOR_DATA_DIR}" \
		\( \
			-type d -name ".git" -o \
			-type d -name ".venv" -o \
			-type d -name "scripts" -o \
			-type d -name "modules" -o \
			-type d -name "volumes" \
		\) -prune -o -type d -exec \
			sudo chmod 770 {} + || exit 2

	find "${RT_VALIDATOR_DIR}" "${RT_VALIDATOR_CONFIGS_DIR}" "${RT_VALIDATOR_DATA_DIR}" \
		\( \
			-type d -name ".git" -o \
			-type d -name ".venv" -o \
			-type d -name "scripts" -o \
			-type d -name "modules" -o \
			-type d -name "volumes" -o \
			-type l -name ".env" \
		\) -prune -o -type f -exec \
			sudo chmod 660 {} + || exit 2

	find "${RT_VALIDATOR_DIR}" "${RT_VALIDATOR_CONFIGS_DIR}" "${RT_VALIDATOR_DATA_DIR}" \
		\( \
			-type d -name ".git" -o \
			-type d -name ".venv" -o \
			-type d -name "scripts" -o \
			-type d -name "modules" -o \
			-type d -name "volumes" \
		\) -prune -o -type d -exec \
			sudo chmod ug+s {} + || exit 2

	find "${RT_VALIDATOR_LOGS_DIR}" "${RT_VALIDATOR_TMP_DIR}" -type d -exec sudo chmod 775 {} + || exit 2
	find "${RT_VALIDATOR_LOGS_DIR}" "${RT_VALIDATOR_TMP_DIR}" -type f -exec sudo chmod 664 {} + || exit 2
	find "${RT_VALIDATOR_LOGS_DIR}" "${RT_VALIDATOR_TMP_DIR}" -type d -exec sudo chmod +s {} + || exit 2

	echo "${USER} ALL=(ALL) ALL" | sudo tee -a "/etc/sudoers.d/${USER}" > /dev/null || exit 2
	echo ""

	## Parsing input:
	case ${1:-} in
		"" | -s | --start | start | --run | run)
			_run;;
			# shift;;
		-b | --bash | bash | /bin/bash)
			shift
			if [ -z "${*:-}" ]; then
				echo "[INFO]: Starting bash..."
				/bin/bash
			else
				echo "[INFO]: Executing command -> ${*}"
				exec /bin/bash -c "${@}" || exit 2
			fi
			exit 0;;
		*)
			echo "[ERROR]: Failed to parsing input -> ${*}" >&2
			echo "[INFO]: USAGE: ${0}  -s, --start, start | -b, --bash, bash, /bin/bash"
			exit 1;;
	esac
}

main "${@:-}"
