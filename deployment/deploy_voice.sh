#!/bin/bash
#
# Deploy skeleton-app voice command service to multiple nodes
#

set -e

# Configuration
NODES=("indigo" "green" "karate")
NODE_IPS=("192.168.32.7" "192.168.32.5" "192.168.32.11")
NODE_IDS=("indigo" "green" "karate")
USER="sysadmin"
REMOTE_DIR="/home/sysadmin/Programs/skeleton-app"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Skeleton App Voice Service Deployment${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""

# Function to deploy to a single node
deploy_to_node() {
    local node_name=$1
    local node_ip=$2
    local node_id=$3
    
    echo -e "\n${YELLOW}→ Deploying to ${node_name} (${node_ip})${NC}"
    
    # Test SSH connection
    if ! ssh -o ConnectTimeout=5 ${USER}@${node_ip} "echo 'Connected'" > /dev/null 2>&1; then
        echo -e "${RED}✗ Cannot connect to ${node_name}${NC}"
        return 1
    fi
    
    echo "  ✓ SSH connection successful"
    
    # Create remote directory if it doesn't exist
    ssh ${USER}@${node_ip} "mkdir -p ${REMOTE_DIR}"
    
    # Sync code to remote node
    echo "  → Syncing code..."
    rsync -avz --exclude '__pycache__' \
               --exclude '*.pyc' \
               --exclude '.git' \
               --exclude 'venv' \
               --exclude 'models' \
               ${LOCAL_DIR}/ ${USER}@${node_ip}:${REMOTE_DIR}/
    
    echo "  ✓ Code synced"
    
    # Create node-specific config
    echo "  → Configuring for ${node_id}..."
    ssh ${USER}@${node_ip} "cd ${REMOTE_DIR} && \
        sed 's/id: \"linux-01\"/id: \"${node_id}\"/' config.yaml > config.yaml.tmp && \
        sed 's/host: \"0.0.0.0\"/host: \"${node_ip}\"/' config.yaml.tmp > config.yaml.new && \
        mv config.yaml.new config.yaml && rm -f config.yaml.tmp"
    
    # Install Python dependencies
    echo "  → Installing Python dependencies..."
    ssh ${USER}@${node_ip} "cd ${REMOTE_DIR} && pip3 install -e '.[audio,stt]' --user --quiet"
    
    echo "  ✓ Dependencies installed"
    
    # Check if JACK is running
    echo "  → Checking JACK status..."
    if ssh ${USER}@${node_ip} "pgrep -x jackd > /dev/null || pgrep -x jackdbus > /dev/null"; then
        echo "  ✓ JACK is running"
    else
        echo -e "  ${YELLOW}⚠ JACK is not running on ${node_name}${NC}"
        echo "    Start JACK with: qjackctl or jackd"
    fi
    
    # Check if Vosk model exists
    echo "  → Checking Vosk model..."
    if ssh ${USER}@${node_ip} "test -d ${REMOTE_DIR}/models/vosk/vosk-model-en-us-0.22"; then
        echo "  ✓ Vosk model found"
    else
        echo -e "  ${YELLOW}⚠ Vosk model not found${NC}"
        echo "    Download from: https://alphacephei.com/vosk/models"
        echo "    Place in: ${REMOTE_DIR}/models/vosk/"
    fi
    
    # Install systemd service (optional)
    if [ "$INSTALL_SERVICE" = "yes" ]; then
        echo "  → Installing systemd service..."
        ssh ${USER}@${node_ip} "sudo cp ${REMOTE_DIR}/deployment/skeleton-voice.service /etc/systemd/system/ && \
                                  sudo systemctl daemon-reload && \
                                  sudo systemctl enable skeleton-voice.service"
        echo "  ✓ Systemd service installed"
    fi
    
    echo -e "${GREEN}  ✓ Deployment to ${node_name} complete${NC}"
    
    return 0
}

# Parse command line arguments
INSTALL_SERVICE="no"
SELECTED_NODES=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --install-service)
            INSTALL_SERVICE="yes"
            shift
            ;;
        --node)
            SELECTED_NODES+=("$2")
            shift 2
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --install-service    Install as systemd service"
            echo "  --node <name>        Deploy to specific node(s) only"
            echo "  --help               Show this help"
            echo ""
            echo "Available nodes: ${NODES[*]}"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# If no specific nodes selected, deploy to all
if [ ${#SELECTED_NODES[@]} -eq 0 ]; then
    SELECTED_NODES=("${NODES[@]}")
fi

# Deploy to selected nodes
SUCCESS_COUNT=0
FAIL_COUNT=0

for node in "${SELECTED_NODES[@]}"; do
    # Find node index
    for i in "${!NODES[@]}"; do
        if [[ "${NODES[$i]}" = "${node}" ]]; then
            if deploy_to_node "${NODES[$i]}" "${NODE_IPS[$i]}" "${NODE_IDS[$i]}"; then
                ((SUCCESS_COUNT++))
            else
                ((FAIL_COUNT++))
            fi
            break
        fi
    done
done

# Summary
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Deployment Summary${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "  Successful: ${GREEN}${SUCCESS_COUNT}${NC}"
echo -e "  Failed:     ${RED}${FAIL_COUNT}${NC}"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}✓ All deployments successful!${NC}"
    echo ""
    echo "To start the voice service on each node:"
    echo "  skeleton voice"
    echo ""
    echo "Or with systemd (if installed):"
    echo "  sudo systemctl start skeleton-voice"
    echo ""
    echo "To test the WebSocket connection:"
    echo "  websocat ws://192.168.32.7:8001/ws"
else
    echo -e "${RED}✗ Some deployments failed${NC}"
    exit 1
fi
