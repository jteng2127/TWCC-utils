#!/usr/bin/env bash
REMOTE_BASH_PATH=""
REMOTE_LOG_PREFIX=""
CREATE_ONLY=0
IS_FOLLOW=0
VERBOSE=0
GPU_REQUESTED=1
IMAGE_NAME="pytorch-21.02-py3:latest"
IMAGE_TYPE="PyTorch"

# Flag
show_usage() {
	echo "Usage: $0 -s \"script_path\" [-l \"log_prefix\"] [-v] [-f]"
	echo ""
	echo "Options:"
	echo "  -s, --script       Path to the remote script (REQUIRED if not using -c)"
	echo "  -c, --create       Create container only (REQUIRED if not using -s)"
	echo "  -l, --log-prefix   Prefix for log file storage (optional)"
	echo "  -g, --gpu          Number of requested GPUs (default: 1)"
	echo "  -t, --image-type   Type of the image to use (default: PyTorch)"
	echo "  -i, --image-name   Name of the image to use (default: pytorch-21.02-py3:latest)"
	echo "  -v, --verbose      Enable verbose mode (optional)"
	echo "  -f, --follow       Follow log output (optional)"
	echo "  -h, --help         Show this help message and exit"
	exit 0
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	-s | --script)
		REMOTE_BASH_PATH="$2"
		shift 2
		;;
	-c | --create)
		CREATE_ONLY=1
		shift
		;;
	-l | --log-prefix)
		REMOTE_LOG_PREFIX="$2"
		shift 2
		;;
	-g | --gpu)
		if [[ "$2" =~ ^[0-9]+$ ]]; then
			GPU_REQUESTED="$2"
			shift 2
		else
			echo "Error: Invalid GPU count. Must be a positive integer."
			exit 1
		fi
		;;
	-t | --image-type)
		IMAGE_TYPE="$2"
		shift 2
		;;
	-i | --image-name)
		IMAGE_NAME="$2"
		shift 2
		;;
	-v | --verbose)
		VERBOSE=1
		shift
		;;
	-f | --follow)
		IS_FOLLOW=1
		shift
		;;
	-h | --help)
		show_usage
		;;
	*)
		echo "Unknown option: $1"
		exit 1
		;;
	esac
done

if [[ "$CREATE_ONLY" -eq 1 && -n "$REMOTE_BASH_PATH" ]]; then
	echo "Error: -c and -s options are mutually exclusive."
	exit 1
fi

if [[ "$CREATE_ONLY" -eq 0 && -z "$REMOTE_BASH_PATH" ]]; then
	echo "Error: Either -c or -s is required."
	show_usage
fi

[[ -z "$REMOTE_LOG_PREFIX" ]] && REMOTE_LOG_PREFIX=${REMOTE_BASH_PATH%.*}

UUID=$(uuidgen | tr '[:upper:]' '[:lower:]')
REMOTE_LOG_PATH=${REMOTE_LOG_PREFIX}-$(date +"%Y_%m%d_%H%M%S")-$(echo ${UUID} | cut -c1-8).log
CONTAINER_NAME="c$(date +'%m%d_%H%M%S')_$(echo ${UUID} | cut -c1-3)"

# exit message
handle_exit() {
	CREDENTIAL_PATH=$(twccli config whoami | grep twcc_file_session | cut -d '|' -f3 | xargs)
	TWCC_USERNAME=$(cat ${CREDENTIAL_PATH} | grep twcc_username | awk '{print $2}')

	echo -e "\n\n- To monitor the container log, use the following command:\n"
	echo "ssh ${SSH_INFO} \"tail -n +1 -f ${REMOTE_LOG_PATH}\""

	echo -e "\n- To remove the container, use the following command:\n"
	echo "twccli rm ccs -fs ${CCS_ID}"

	echo -e "\n- To fetch the log file, use the following command:\n"
	echo "sftp -oBatchMode=yes -oStrictHostKeyChecking=no ${TWCC_USERNAME}@xdata1.twcc.ai <<EOF
get ${REMOTE_LOG_PATH} .
bye
EOF"
	echo ""
	exit 0
}

# Log function for verbose
mylog() {
	if [[ $VERBOSE -eq 1 ]]; then
		# echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
		printf "[%3ds] " "$SECONDS"
		echo -e "$1"
	fi
}

# for twccli environment
mylog "Activating twccli environment..."
eval "$(conda shell.bash hook)"
conda activate base

# Create container
mylog "GPU requested: ${GPU_REQUESTED}"
mylog "Creating container \"${CONTAINER_NAME}\"..."
out=$(twccli mk ccs -gpu "${GPU_REQUESTED}" -itype "${IMAGE_TYPE}" -img "${IMAGE_NAME}" -n "${CONTAINER_NAME}" -wait -json)
CCS_ID=$(echo "$out" | jq -r '.id') || {
	echo "jq failed. Output was:"
	echo "$out"
	exit 1
}
mylog "Created!"
mylog "CCS_ID=\"${CCS_ID}\""
mylog ""

# Fetch ssh info
mylog "Fetching ssh info..."
SSH_INFO=$(twccli ls ccs -gssh -s ${CCS_ID} | sed -E 's/([a-zA-Z0-9._%+-]+)@([0-9]+)-([0-9]+)-([0-9]+)-([0-9]+)\.ccs\.twcc\.ai/\1@\2.\3.\4.\5/')

# Create only
if [[ "$CREATE_ONLY" -eq 1 ]]; then
	handle_exit
fi

# Resolve script/log path
mylog "Checking script exist..."
if ! ssh -o "StrictHostKeyChecking=no" ${SSH_INFO} "[[ -f ${REMOTE_BASH_PATH} ]]" 2>/dev/null; then
	echo "Error: script path does not exist, removing container..."
	twccli rm ccs -fs ${CCS_ID}
	echo "Container removed."
	exit 1
fi
mylog "Resolving script/log path..."
ssh -o "StrictHostKeyChecking=no" ${SSH_INFO} "touch ${REMOTE_LOG_PATH}" 2>/dev/null
read REMOTE_BASH_PATH < <(ssh -o "StrictHostKeyChecking=no" ${SSH_INFO} "realpath ${REMOTE_BASH_PATH}" 2>/dev/null)
read REMOTE_LOG_PATH < <(ssh -o "StrictHostKeyChecking=no" ${SSH_INFO} "realpath ${REMOTE_LOG_PATH}" 2>/dev/null)
# Run script
mylog "Remote log path: \"${REMOTE_LOG_PATH}\""
mylog "Running script: \"${REMOTE_BASH_PATH}\"..."
ssh -o "StrictHostKeyChecking=no" ${SSH_INFO} \
	"export CCS_ID=${CCS_ID}; nohup ${REMOTE_BASH_PATH} < /dev/null > ${REMOTE_LOG_PATH} 2>&1 &" \
	2>/dev/null
mylog "Script is running!"

if [[ $IS_FOLLOW -eq 1 ]]; then
	trap handle_exit SIGINT
	echo -e "\n=== Container log (Press ctrl-C to stop monitor) ==="
	ssh ${SSH_INFO} "tail -n +1 -f ${REMOTE_LOG_PATH}"
else
	handle_exit
fi
