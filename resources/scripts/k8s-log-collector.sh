#!/bin/bash

# Set variables
NAMESPACE=${1:-default}
LOG_DIR="./k8s-logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Ensure log directory exists
mkdir -p "$LOG_DIR"

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Install stern if not available
if ! command_exists stern; then
  echo "Installing stern..."
  STERN_VERSION="1.30.0"
  curl -Lo stern https://github.com/stern/stern/releases/download/v${STERN_VERSION}/stern_${STERN_VERSION}_linux_amd64
  chmod +x stern
  sudo mv stern /usr/local/bin/
fi

# Collect logs using kubectl
echo "Collecting kubectl logs..."
kubectl logs --all-containers=true --namespace="$NAMESPACE" --prefix --timestamps > "$LOG_DIR/${TIMESTAMP}_kubectl_all_logs.txt"

# Collect logs using stern (includes logs from terminated pods)
echo "Collecting stern logs..."
stern --all-namespaces --output json --since 1h --output json > "$LOG_DIR/${TIMESTAMP}_stern_all_logs.json"

# Collect descriptions of all resources
echo "Collecting resource descriptions..."
kubectl describe all --namespace="$NAMESPACE" > "$LOG_DIR/${TIMESTAMP}_resource_descriptions.txt"

# Collect events
echo "Collecting events..."
kubectl get events --namespace="$NAMESPACE" --sort-by='.metadata.creationTimestamp' > "$LOG_DIR/${TIMESTAMP}_events.txt"

echo "Log collection complete. Logs saved in $LOG_DIR"
