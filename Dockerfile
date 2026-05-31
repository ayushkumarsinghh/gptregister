FROM python:3.10-slim

# Install system core utilities, Xvfb for headful browser support, and Google Chrome stable
RUN apt-get update && apt-get install -y \
    xvfb \
    wget \
    gnupg \
    curl \
    unzip \
    --no-install-recommends && \
    wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get install -y ./google-chrome-stable_current_amd64.deb --no-install-recommends && \
    rm google-chrome-stable_current_amd64.deb && \
    rm -rf /var/lib/apt/lists/*

# Set environment variable to flag Docker environment
ENV DOCKER_ENV=true

# Set working directory
WORKDIR /app

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Run the bot inside virtual frame buffer display to support headful Turnstile bypasses on cloud servers
CMD ["xvfb-run", "--server-args=-screen 0 1920x1080x24", "python", "py3.py"]
