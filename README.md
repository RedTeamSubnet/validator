# RedTeam subnet - Validator (Agent)

This repository is for validator of RedTeam subnet. it is focused on running validator node in an independent, easy to configure, dockerized way with docker compose support. Additionally, it includes additional helper container to automatically update and restart validator image when new version is released.

## ✨ Features

- Validator node
- Automatic updates
- Easy configuration
- Dockerized setup
- Docker Compose support

---

## Getting Started

### 1. 🚧 Prerequisites

- Prepare validator wallet (skip if you already have one):
    - Install **Bittensor CLI**:
        - [Installing Bittensor CLI](https://docs.learnbittensor.org/getting-started/install-btcli)
        - [Bittensor CLI: `btcli` Reference Document](https://docs.learnbittensor.org/btcli)
    - Create miner wallet:
        - [Working with Keys](https://docs.learnbittensor.org/keys/working-with-keys)
        - [Bittensor CLI Permissions](https://docs.learnbittensor.org/btcli/btcli-permissions)
    - Stake TAO with validator wallet on RedTeam subnet:
        - [Staker's Guide to `BTCLI`](https://docs.learnbittensor.org/staking-and-delegation/stakers-btcli-guide)
        - [Managing stake with `btcli`](https://docs.learnbittensor.org/staking-and-delegation/managing-stake-btcli)
    - Register validator wallet to RedTeam subnet:
        - [Validating in Bittensor](https://docs.learnbittensor.org/validators)
        - [Validator's Guide to `BTCLI`](https://docs.learnbittensor.org/validators/validators-btcli-guide)
        - [Transaction Fees in Bittensor](https://docs.learnbittensor.org/learn/fees)
- Install [**docker** and **docker compose**](https://docs.docker.com/engine/install)
    - Docker [intstallation script](https://github.com/docker/docker-install)
    - Docker [post-installation steps](https://docs.docker.com/engine/install/linux-postinstall)

---

### 2. 📥 Download or clone the repository

**2.1.** Prepare projects directory (if not exists):

```sh
# Create projects directory:
mkdir -pv ~/workspaces/projects

# Enter into projects directory:
cd ~/workspaces/projects
```

**2.2.** Follow one of the below options **[A]** or **[B]**:

**OPTION A.** Clone the repository:

```sh
git clone https://github.com/RedTeamSubnet/validator.git && \
    cd validator
```

**OPTION B.** Download source code:

1. Download archived **zip** or **tar.gz** file from [**releases**](https://github.com/RedTeamSubnet/validator/releases).
2. Extract it into the projects directory.
3. Enter into the extracted project directory.

### 3. 🌎 Configure environment variables

[NOTE] Please, check **[environment variables](#-environment-variables)** section for more details.

**[IMPORTANT]** Make sure to change the **wallet directory and wallet name variables** to your own values in the **`.env`** file:

```sh
# Copy '.env.example' file to '.env' file:
cp -v ./.env.example ./.env

# Edit environment variables to fit in your environment:
nano ./.env
```

### 4. ✅ Check configuration

```sh
## Check docker compose configuration is valid:
./compose.sh validate
# Or:
docker compose config
```

### 5. 🏁 Run validator node

```sh
## Start docker compose:
./compose.sh start -l
# Or:
docker compose up -d --remove-orphans --force-recreate && \
    docker compose logs -f --tail 100
```

---

## ⚙️ Configuration

### 🌎 Environment Variables

[**`.env.example`**](./.env.example):

```sh
## --- Environment variable --- ##
ENV=PRODUCTION
DEBUG=false
# TZ=UTC
# PYTHONDONTWRITEBYTECODE=1


## -- Bittensor configs -- ##
# RT_BT_SUBTENSOR_NETWORK="wss://entrypoint-finney.opentensor.ai:443"


## -- Subnet configs -- ##
# ! WARNING: Do not use `~` character, it will not be expand properly! Use absolute path or ${HOME} instead:
RT_BTCLI_WALLET_DIR="${HOME}/.bittensor/wallets" # !!! CHANGE THIS TO REAL WALLET DIRECTORY !!!
# RT_BT_SUBNET_NETUID=61


## -- Validator configs -- ##
RT_VALIDATOR_WALLET_NAME="validator" # !!! CHANGE THIS TO REAL VALIDATOR WALLET NAME !!!
RT_VALIDATOR_HOTKEY_NAME="default" # !!! CHANGE THIS TO REAL VALIDATOR HOTKEY NAME !!!
# RT_VALIDATOR_LOGS_DIR="/var/log/agent-validator"
# RT_VALIDATOR_DATA_DIR="/var/lib/agent-validator"
# RT_VALIDATOR_USE_CENTRALIZED_SCORING=true
```

## 📚 Documentation

- <https://docs.theredteam.io>

---

## 📑 References

- Bittensor docs: <https://docs.learnbittensor.org>
- Bittensor CLI: <https://docs.learnbittensor.org/btcli>
- Bittensor CLI GitHub: <https://github.com/opentensor/btcli>
- Bittensor CLI PyPI: <https://pypi.org/project/bittensor-cli>
- The RedTeam subnet: <https://www.theredteam.io>
