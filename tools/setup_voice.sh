#!/bin/bash
#
# Quick setup for voice command testing tonight
# Configures indigo, green, and karate nodes
#

set -e

echo "═══════════════════════════════════════════════════════════"
echo "  Skeleton App Voice Commands - Quick Setup"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Check if we're on indigo (development machine)
HOSTNAME=$(hostname)
if [ "$HOSTNAME" != "indigo" ]; then
    echo "⚠ Warning: This script is designed to run from indigo"
    echo "  Current hostname: $HOSTNAME"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Configuration
NODES=("indigo:192.168.32.7" "green:192.168.32.5" "karate:192.168.32.11")

echo "Step 1: Checking SSH connectivity"
echo "─────────────────────────────────────────────────────────────"
for node_info in "${NODES[@]}"; do
    IFS=':' read -r node ip <<< "$node_info"
    
    if [ "$node" = "$HOSTNAME" ]; then
        echo "  ✓ $node (local)"
    else
        if ssh -o ConnectTimeout=3 sysadmin@$ip "echo ''" 2>/dev/null; then
            echo "  ✓ $node ($ip)"
        else
            echo "  ✗ $node ($ip) - Cannot connect"
        fi
    fi
done

echo ""
echo "Step 2: Checking JACK status on all nodes"
echo "─────────────────────────────────────────────────────────────"
for node_info in "${NODES[@]}"; do
    IFS=':' read -r node ip <<< "$node_info"
    
    if [ "$node" = "$HOSTNAME" ]; then
        if pgrep -x jackd > /dev/null || pgrep -x jackdbus > /dev/null; then
            echo "  ✓ $node - JACK is running"
        else
            echo "  ⚠ $node - JACK is NOT running"
            echo "    Start with: qjackctl &"
        fi
    else
        if ssh sysadmin@$ip "pgrep -x jackd > /dev/null || pgrep -x jackdbus > /dev/null" 2>/dev/null; then
            echo "  ✓ $node - JACK is running"
        else
            echo "  ⚠ $node - JACK is NOT running"
        fi
    fi
done

echo ""
echo "Step 3: Checking Vosk model"
echo "─────────────────────────────────────────────────────────────"
VOSK_MODEL_PATH="$HOME/Programs/skeleton-app/models/vosk/vosk-model-en-us-0.22"

if [ -d "$VOSK_MODEL_PATH" ]; then
    echo "  ✓ Vosk model found at $VOSK_MODEL_PATH"
else
    echo "  ✗ Vosk model not found"
    echo ""
    echo "  Download instructions:"
    echo "  ─────────────────────────────────────────────────────────"
    echo "  mkdir -p models/vosk"
    echo "  cd models/vosk"
    echo "  wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
    echo "  unzip vosk-model-en-us-0.22.zip"
    echo "  cd ../.."
    echo ""
    read -p "  Download now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mkdir -p models/vosk
        cd models/vosk
        echo "  → Downloading Vosk model (1.8 GB)..."
        wget -q --show-progress https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
        echo "  → Extracting..."
        unzip -q vosk-model-en-us-0.22.zip
        rm vosk-model-en-us-0.22.zip
        cd ../..
        echo "  ✓ Model downloaded and extracted"
    else
        echo "  ⚠ Skipping model download - voice service will not work without it"
    fi
fi

echo ""
echo "Step 4: Installing Python dependencies"
echo "─────────────────────────────────────────────────────────────"
if pip3 show vosk &> /dev/null; then
    echo "  ✓ vosk already installed"
else
    echo "  → Installing vosk..."
    pip3 install vosk --user --quiet
fi

if pip3 show JACK-Client &> /dev/null; then
    echo "  ✓ JACK-Client already installed"
else
    echo "  → Installing JACK-Client..."
    pip3 install JACK-Client --user --quiet
fi

if pip3 show fastapi &> /dev/null; then
    echo "  ✓ fastapi already installed"
else
    echo "  → Installing fastapi..."
    pip3 install fastapi uvicorn --user --quiet
fi

if pip3 show websockets &> /dev/null; then
    echo "  ✓ websockets already installed"
else
    echo "  → Installing websockets..."
    pip3 install websockets --user --quiet
fi

echo ""
echo "Step 5: Verifying configuration"
echo "─────────────────────────────────────────────────────────────"
if [ -f "config.yaml" ]; then
    echo "  ✓ config.yaml found"
    
    # Check for voice_commands section
    if grep -q "voice_commands:" config.yaml; then
        echo "  ✓ voice_commands section present"
    else
        echo "  ⚠ voice_commands section missing"
        echo "    You may need to update config.yaml"
    fi
else
    echo "  ⚠ config.yaml not found"
    if [ -f "config.example.yaml" ]; then
        echo "  → Copying from config.example.yaml"
        cp config.example.yaml config.yaml
        echo "  ✓ config.yaml created"
    fi
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Setup Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Quick Start:"
echo ""
echo "  1. Make sure JACK is running:"
echo "     qjackctl &"
echo ""
echo "  2. Start the voice service on this node:"
echo "     skeleton voice"
echo ""
echo "  3. In qjackctl, connect your microphone:"
echo "     system:capture_1 → skeleton_app_vosk:voice_in"
echo ""
echo "  4. Test the service (in another terminal):"
echo "     python tools/test_voice_service.py --test websocket --duration 30"
echo ""
echo "  5. Try voice commands:"
echo "     Say: 'computer indigo' (wake word)"
echo "     Then: 'play' or 'stop' (command)"
echo ""
echo "Deploy to other nodes:"
echo "  ./deployment/deploy_voice.sh"
echo ""
echo "═══════════════════════════════════════════════════════════"
