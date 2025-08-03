#!/bin/bash
#
# This script automates the deployment process by pulling the latest changes,
# stopping the current services, and rebuilding/restarting them to ensure a clean deployment.
#
# It ensures that the application is always running the most recent version
# of the code from the main branch.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "🚀 Starting deployment process..."


# 2. Stop and remove the old containers, networks, and volumes.
echo "🧹 Stopping and removing old containers..."
docker-compose down

# 4. Clean up any unused Docker images.
echo "🗑️  Cleaning up dangling images..."
docker system prune -af

# 3. Rebuild and restart the Docker containers in detached mode.
#    The '--build' flag forces a rebuild of the images.
#    The '-d' flag runs the containers in the background.
echo "🏗️  Building and restarting Docker services..."
docker-compose up --build 



echo "✅ Deployment finished successfully!"
