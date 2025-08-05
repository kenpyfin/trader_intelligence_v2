# This file defines the environment for the Python FastAPI backend.
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY ./requirements.txt /app/requirements.txt

# Install system dependencies for TA-Lib, build it from source,
# and then clean up to keep the image small.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    unzip && \
    wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz -O ta-lib-0.4.0-src.tar.gz && \
    tar -xzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz && \
    apt-get purge -y --auto-remove build-essential wget unzip && \
    rm -rf /var/lib/apt/lists/*

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir reduces the image size.
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy the rest of the backend application's code into the container at /app
COPY . /app

# Add the project root to the python path to allow imports from src and other root directories.
ENV PYTHONPATH=/app

# The command to run the application using uvicorn.
# It will listen on the port specified by the BACKEND_PORT environment variable from .env
# The --reload flag is added for development convenience.
# We use the shell form of CMD to allow environment variable substitution.
CMD uvicorn src.main:app --host 0.0.0.0 --port ${BACKEND_PORT:-8511} --reload
