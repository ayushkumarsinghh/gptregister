FROM python:3.10-slim

# Install system core utilities, Xvfb and xauth for headful browser support, and Google Chrome stable
RUN apt-get update && apt-get install -y \
    xvfb \
    xauth \
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
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Run the bot directly, letting it start the background display internally
CMD ["python", "-u", "py3.py"]
