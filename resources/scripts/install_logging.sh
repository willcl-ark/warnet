#!/bin/bash
set -e

THIS_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
MANIFESTS_DIR=$( cd -- "$THIS_DIR/../manifests" &> /dev/null && pwd )

helm repo add grafana https://grafana.github.io/helm-charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm upgrade --install --namespace warnet-logging --create-namespace --values "${MANIFESTS_DIR}/loki_values.yaml" loki grafana/loki --version 5.47.2
helm upgrade --install --namespace warnet-logging promtail grafana/promtail --values "${MANIFESTS_DIR}/promtail-values.yaml"
helm upgrade --install --namespace warnet-logging prometheus prometheus-community/kube-prometheus-stack --namespace warnet-logging --set grafana.enabled=false
helm upgrade --install --namespace warnet-logging loki-grafana grafana/grafana --values "${MANIFESTS_DIR}/grafana_values.yaml"
