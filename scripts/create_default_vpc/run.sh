#!/bin/bash
set -eu -o pipefail

if [[ -z $1 ]]; then
    echo "session name is required as first argument, ex. {user}_assumerole"
    exit 1
else
    echo "The session name is $1"
fi

if [[ -z $2 ]]; then
    echo "account id is required as second argument"
    exit 1
else
    echo "The account id is $2"
fi

if [[ -z $3 ]]; then
    echo "assume role name is required as the third argument"
    exit 1
else
    echo "The assume role name is $3"
fi

mkdir vpc_env
python3 -m venv vpc_env
# shellcheck disable=SC1091
source vpc_env/bin/activate
python3 -m pip install -U pip
pip3 install -r requirements.txt

python3 create_default_vpc.py --dry-run --debug --account-id="$2" --role-session-name="$1" --role-to-assume="$3"

deactivate
rm -rf vpc_env
