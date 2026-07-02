#!/usr/bin/env bash
# Run this on YOUR machine (or in GCP Cloud Shell) — not on the VM itself.
# Creates a Compute Engine VM sized for a long-running, network-bound scraper
# (CKAN's own API calls are the bottleneck, not CPU/RAM, so e2-medium is plenty).
#
# Prereqs (one-time, on whichever machine runs this script):
#   gcloud auth login
#   gcloud config set project <YOUR_PROJECT_ID>
#   gcloud services enable compute.googleapis.com
#
# Usage:
#   PROJECT_ID=my-gcp-project bash deploy/create_vm.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID=your-gcp-project-id}"
VM_NAME="${VM_NAME:-ckan-scraper}"
ZONE="${ZONE:-us-central1-a}"
MACHINE_TYPE="${MACHINE_TYPE:-e2-medium}"
DISK_SIZE="${DISK_SIZE:-50GB}"

gcloud compute instances create "$VM_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --machine-type="$MACHINE_TYPE" \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size="$DISK_SIZE" \
  --boot-disk-type=pd-balanced

echo ""
echo "VM created. Next:"
echo "  gcloud compute ssh $VM_NAME --zone=$ZONE"
echo "Then, on the VM, run deploy/bootstrap.sh (see below)."
