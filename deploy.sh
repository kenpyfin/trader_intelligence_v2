#!/bin/bash
#
# This script automates the deployment process by pulling the latest changes,
# stopping the current services, and rebuilding/restarting them to ensure a clean deployment.
#
# It ensures that the application is always running the most recent version
# of the code from the main branch.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Args ---------------------------------------------------------------
# Support running in detached mode via -d/--detached
DETACHED=0

usage() {
  echo "Usage: $0 [-d|--detached] [-h|--help]"
  echo "  -d, --detached   Run docker-compose up in detached mode (-d)"
  echo "  -h, --help       Show this help and exit"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--detached)
      DETACHED=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$DETACHED" -eq 1 ]]; then
  echo "🚀 Starting deployment process (detached)..."
else
  echo "🚀 Starting deployment process..."
fi


# 2. Stop and remove the old containers, networks, and volumes.
echo "🧹 Stopping and removing old containers..."
docker-compose down

# 4. Clean up any unused Docker images.
echo "🗑️  Cleaning up dangling images..."
docker system prune -af

# 3. Rebuild and restart the Docker containers (detached optional).
#    The '--build' flag forces a rebuild of the images.
#    The '-d' flag runs the containers in the background.
echo "🏗️  Building and restarting Docker services (default backend: ib_async)..."
if [[ "$DETACHED" -eq 1 ]]; then
  docker-compose up --build -d
else
  docker-compose up --build
fi



echo "✅ Deployment finished successfully!"
