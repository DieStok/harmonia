#!/bin/bash
# diagnose_hpc.sh
# Comprehensive diagnostic script for HPC compute node
# Run this ON THE COMPUTE NODE where the container runs

set -u

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "=============================================="
echo "HPC COMPUTE NODE DIAGNOSTIC SCRIPT"
echo "=============================================="
echo "Timestamp: $(date)"
echo ""

# ============================================
# SECTION 1: Node Identity
# ============================================
echo -e "${BLUE}========== SECTION 1: NODE IDENTITY ==========${NC}"
echo ""

echo "Short hostname:"
HOSTNAME_SHORT=$(hostname)
echo "  $HOSTNAME_SHORT"

echo ""
echo "Full hostname (FQDN):"
HOSTNAME_FULL=$(hostname -f 2>/dev/null || echo "Could not get FQDN")
echo "  $HOSTNAME_FULL"

echo ""
echo "All hostnames/aliases:"
hostname -A 2>/dev/null || echo "  Could not get aliases"

echo ""
echo "IP addresses:"
hostname -I 2>/dev/null || echo "  Could not get IPs"

echo ""
echo "Detailed IP info:"
ip addr 2>/dev/null | grep "inet " | while read line; do
    echo "  $line"
done

echo ""
echo "SLURM Job Info:"
echo "  SLURM_JOB_ID: ${SLURM_JOB_ID:-not set}"
echo "  SLURM_NODELIST: ${SLURM_NODELIST:-not set}"
echo "  SLURM_JOB_NODELIST: ${SLURM_JOB_NODELIST:-not set}"

echo ""
echo -e "${GREEN}>>> COPY THIS FOR SSH TUNNEL:${NC}"
echo -e "${GREEN}    Hostname options to try:${NC}"
echo "      1. $HOSTNAME_SHORT"
echo "      2. $HOSTNAME_FULL"
for ip in $(hostname -I 2>/dev/null); do
    echo "      3. $ip"
done
echo ""

# ============================================
# SECTION 2: Port 8888 Status (Before Container)
# ============================================
echo -e "${BLUE}========== SECTION 2: PORT 8888 STATUS (BEFORE) ==========${NC}"
echo ""

echo "Checking if port 8888 is already in use..."
if command -v lsof &> /dev/null; then
    LSOF_OUT=$(lsof -i :8888 2>/dev/null)
    if [ -n "$LSOF_OUT" ]; then
        echo -e "${YELLOW}WARNING: Port 8888 is already in use:${NC}"
        echo "$LSOF_OUT"
    else
        echo -e "${GREEN}✓ Port 8888 is free${NC}"
    fi
else
    echo "lsof not available, trying netstat..."
    netstat -tlnp 2>/dev/null | grep 8888 || echo -e "${GREEN}✓ Port 8888 appears free${NC}"
fi

echo ""
echo "Checking if port 8889 is available (backup)..."
if command -v lsof &> /dev/null; then
    LSOF_OUT=$(lsof -i :8889 2>/dev/null)
    if [ -n "$LSOF_OUT" ]; then
        echo -e "${YELLOW}Port 8889 is also in use${NC}"
    else
        echo -e "${GREEN}✓ Port 8889 is free (backup option)${NC}"
    fi
fi

echo ""

# ============================================
# SECTION 3: Container File Check
# ============================================
echo -e "${BLUE}========== SECTION 3: CONTAINER CHECK ==========${NC}"
echo ""

if [ -f "jupyter.sif" ]; then
    echo -e "${GREEN}✓ jupyter.sif exists${NC}"
    ls -lh jupyter.sif
else
    echo -e "${RED}✗ jupyter.sif NOT FOUND in current directory${NC}"
    echo "  Current directory: $(pwd)"
    echo "  Contents:"
    ls -la
    exit 1
fi

echo ""
if [ -f "run_apptainer_harmonia.sh" ]; then
    echo -e "${GREEN}✓ run_apptainer_harmonia.sh exists${NC}"
else
    echo -e "${YELLOW}! run_apptainer_harmonia.sh not found${NC}"
fi

echo ""

# ============================================
# SECTION 4: Network Interfaces
# ============================================
echo -e "${BLUE}========== SECTION 4: NETWORK INTERFACES ==========${NC}"
echo ""

echo "All network interfaces:"
ip link show 2>/dev/null | grep -E "^[0-9]+" | while read line; do
    echo "  $line"
done

echo ""
echo "Routing table (default gateway):"
ip route 2>/dev/null | grep default || echo "  No default route found"

echo ""

# ============================================
# SECTION 5: Firewall Status
# ============================================
echo -e "${BLUE}========== SECTION 5: FIREWALL STATUS ==========${NC}"
echo ""

echo "Checking iptables..."
if command -v iptables &> /dev/null; then
    IPTABLES_COUNT=$(iptables -L -n 2>/dev/null | wc -l)
    if [ "$IPTABLES_COUNT" -gt 10 ]; then
        echo -e "${YELLOW}iptables has rules (may affect connectivity)${NC}"
        echo "  Run 'iptables -L -n' for details"
    else
        echo -e "${GREEN}✓ iptables appears open${NC}"
    fi
else
    echo "  iptables command not available"
fi

echo ""

# ============================================
# SECTION 6: Start Container
# ============================================
echo -e "${BLUE}========== SECTION 6: STARTING CONTAINER ==========${NC}"
echo ""

echo "Starting container in background..."
echo "Command: bash run_apptainer_harmonia.sh"
echo ""

# Start in background and capture PID
bash run_apptainer_harmonia.sh &
CONTAINER_PID=$!

echo "Container started with PID: $CONTAINER_PID"
echo "Waiting 10 seconds for startup..."
sleep 10

echo ""

# ============================================
# SECTION 7: Port Status (After Container)
# ============================================
echo -e "${BLUE}========== SECTION 7: PORT STATUS (AFTER STARTUP) ==========${NC}"
echo ""

echo "Checking what's listening on port 8888..."
if command -v lsof &> /dev/null; then
    lsof -i :8888 2>/dev/null || echo "  Nothing found on port 8888"
else
    netstat -tlnp 2>/dev/null | grep 8888 || echo "  Nothing found on port 8888"
fi

echo ""
echo "Checking what's listening on all ports (LISTEN state):"
if command -v ss &> /dev/null; then
    ss -tlnp 2>/dev/null | head -20
else
    netstat -tlnp 2>/dev/null | head -20
fi

echo ""

# ============================================
# SECTION 8: Process Check
# ============================================
echo -e "${BLUE}========== SECTION 8: PROCESS CHECK ==========${NC}"
echo ""

echo "Looking for Jupyter/Beaker processes:"
ps aux 2>/dev/null | grep -E "(jupyter|beaker|python)" | grep -v grep || echo "  No matching processes found"

echo ""
echo "Container process status:"
if kill -0 $CONTAINER_PID 2>/dev/null; then
    echo -e "${GREEN}✓ Container process $CONTAINER_PID is running${NC}"
else
    echo -e "${RED}✗ Container process $CONTAINER_PID is NOT running${NC}"
fi

echo ""

# ============================================
# SECTION 9: Local Connectivity Test
# ============================================
echo -e "${BLUE}========== SECTION 9: LOCAL CONNECTIVITY TEST ==========${NC}"
echo ""

echo "Testing localhost:8888..."
CURL_RESULT=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://localhost:8888 2>/dev/null)
if [ "$CURL_RESULT" == "200" ] || [ "$CURL_RESULT" == "302" ] || [ "$CURL_RESULT" == "301" ]; then
    echo -e "${GREEN}✓ localhost:8888 responds with HTTP $CURL_RESULT${NC}"
elif [ "$CURL_RESULT" == "000" ]; then
    echo -e "${RED}✗ localhost:8888 - Connection failed (no response)${NC}"
else
    echo -e "${YELLOW}! localhost:8888 responds with HTTP $CURL_RESULT${NC}"
fi

echo ""
echo "Testing 127.0.0.1:8888..."
CURL_RESULT=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://127.0.0.1:8888 2>/dev/null)
if [ "$CURL_RESULT" == "200" ] || [ "$CURL_RESULT" == "302" ] || [ "$CURL_RESULT" == "301" ]; then
    echo -e "${GREEN}✓ 127.0.0.1:8888 responds with HTTP $CURL_RESULT${NC}"
elif [ "$CURL_RESULT" == "000" ]; then
    echo -e "${RED}✗ 127.0.0.1:8888 - Connection failed${NC}"
else
    echo -e "${YELLOW}! 127.0.0.1:8888 responds with HTTP $CURL_RESULT${NC}"
fi

echo ""
echo "Testing 0.0.0.0:8888..."
CURL_RESULT=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://0.0.0.0:8888 2>/dev/null)
if [ "$CURL_RESULT" == "200" ] || [ "$CURL_RESULT" == "302" ] || [ "$CURL_RESULT" == "301" ]; then
    echo -e "${GREEN}✓ 0.0.0.0:8888 responds with HTTP $CURL_RESULT${NC}"
elif [ "$CURL_RESULT" == "000" ]; then
    echo -e "${RED}✗ 0.0.0.0:8888 - Connection failed${NC}"
else
    echo -e "${YELLOW}! 0.0.0.0:8888 responds with HTTP $CURL_RESULT${NC}"
fi

# Test with IP addresses
for ip in $(hostname -I 2>/dev/null); do
    echo ""
    echo "Testing $ip:8888..."
    CURL_RESULT=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://$ip:8888 2>/dev/null)
    if [ "$CURL_RESULT" == "200" ] || [ "$CURL_RESULT" == "302" ] || [ "$CURL_RESULT" == "301" ]; then
        echo -e "${GREEN}✓ $ip:8888 responds with HTTP $CURL_RESULT${NC}"
    elif [ "$CURL_RESULT" == "000" ]; then
        echo -e "${RED}✗ $ip:8888 - Connection failed${NC}"
    else
        echo -e "${YELLOW}! $ip:8888 responds with HTTP $CURL_RESULT${NC}"
    fi
done

echo ""

# ============================================
# SECTION 10: Actual Response Content
# ============================================
echo -e "${BLUE}========== SECTION 10: RESPONSE CONTENT ==========${NC}"
echo ""

echo "Fetching actual response from localhost:8888 (first 500 chars):"
echo "---"
curl -s --connect-timeout 5 http://localhost:8888 2>/dev/null | head -c 500 || echo "(no response)"
echo ""
echo "---"

echo ""

# ============================================
# SECTION 11: Summary and SSH Commands
# ============================================
echo -e "${BLUE}========== SECTION 11: SUMMARY & SSH COMMANDS ==========${NC}"
echo ""

echo -e "${GREEN}=== TRY THESE SSH COMMANDS FROM YOUR MAC ===${NC}"
echo ""
echo "Option 1 - Short hostname:"
echo "  ssh -L 9999:${HOSTNAME_SHORT}:8888 dstoker@hpcgw.op.umcutrecht.nl"
echo ""
echo "Option 2 - Full hostname:"
echo "  ssh -L 9999:${HOSTNAME_FULL}:8888 dstoker@hpcgw.op.umcutrecht.nl"
echo ""

for ip in $(hostname -I 2>/dev/null); do
    echo "Option 3 - IP address:"
    echo "  ssh -L 9999:${ip}:8888 dstoker@hpcgw.op.umcutrecht.nl"
    echo ""
done

echo "Option 4 - Two-hop (if gateway can't reach compute node):"
echo "  First: ssh dstoker@hpcgw.op.umcutrecht.nl"
echo "  Then:  ssh -L 9999:localhost:8888 dstoker@${HOSTNAME_SHORT}"
echo ""

echo "Option 5 - ProxyJump:"
echo "  ssh -J dstoker@hpcgw.op.umcutrecht.nl -L 9999:localhost:8888 dstoker@${HOSTNAME_SHORT}"
echo ""

echo -e "${GREEN}=== THEN OPEN IN BROWSER ===${NC}"
echo "  http://localhost:9999?token=89f73481102c46c0bc13b2998f9a4fce"
echo ""

echo "=============================================="
echo "DIAGNOSTIC COMPLETE"
echo "=============================================="
echo ""
echo "Container is running in background (PID: $CONTAINER_PID)"
echo "To stop it: kill $CONTAINER_PID"
echo "To see logs: (they should be visible above)"
echo ""

# Keep script running to see container output
echo "Press Ctrl+C to stop the container and exit..."
wait $CONTAINER_PID