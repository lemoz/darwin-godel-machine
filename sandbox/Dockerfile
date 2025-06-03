# DGM Sandbox Environment
# Basic Python environment for safe agent execution

FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash dgm_agent
WORKDIR /home/dgm_agent

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    vim \
    nano \
    && rm -rf /var/lib/apt/lists/*

# Create directory structure
RUN mkdir -p /home/dgm_agent/workspace
RUN mkdir -p /home/dgm_agent/agent_code
RUN mkdir -p /home/dgm_agent/logs

# Copy requirements and install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Set resource limits (these can be overridden at runtime)
# Memory: 2GB, CPU: 1 core (enforced by Docker run parameters)

# Set up basic safety measures
RUN echo "export HISTFILE=/dev/null" >> /home/dgm_agent/.bashrc
RUN echo "export HISTSIZE=0" >> /home/dgm_agent/.bashrc
RUN echo "alias rm='echo \"rm command is disabled for safety\"'" >> /home/dgm_agent/.bashrc
RUN echo "alias sudo='echo \"sudo is not available in this environment\"'" >> /home/dgm_agent/.bashrc

# Switch to non-root user
USER dgm_agent

# Set working directory
WORKDIR /home/dgm_agent/workspace

# Default command
CMD ["/bin/bash"]