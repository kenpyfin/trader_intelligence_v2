# This file defines the environment for the Python FastAPI backend.
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for building Python packages
# build-essential: for compiling C extensions (numpy, pandas, etc.)
# curl: for health checks
# libxml2-dev, libxslt-dev: for lxml
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY ./requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir reduces the image size.
# Explicitly install requests, pandas, and numpy to ensure analysis dependencies are met
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt requests pandas numpy

# Copy the rest of the backend application's code into the container at /app
COPY . /app

# Add the project root to the python path to allow imports from src and other root directories.
ENV PYTHONPATH=/app

# The command to run the application using uvicorn.
# It will listen on the port specified by the BACKEND_PORT environment variable from .env
# We use the shell form of CMD to allow environment variable substitution.
# Force asyncio event loop to avoid uvloop incompatibilities with ib_insync
CMD uvicorn src.main:app --host 0.0.0.0 --port ${BACKEND_PORT:-8511} --loop asyncio
