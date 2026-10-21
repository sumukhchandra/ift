# Use a lightweight Python image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for some ML libraries
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Kolkata

# Run the trader by default
CMD ["python", "QA/nse_auto_trader.py"]
