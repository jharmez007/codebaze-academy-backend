# Use official Python image (Debian-based)
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies for MySQL + WeasyPrint
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libffi-dev \
    default-libmysqlclient-dev \
    pkg-config \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpango1.0-dev \
    libgdk-pixbuf-2.0-0 \
    libgdk-pixbuf-xlib-2.0-dev \
    shared-mime-info \
    fonts-dejavu-core \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt gunicorn

# Copy app source code
COPY . .

# Expose Flask port
EXPOSE 5000

# Run Flask app with Gunicorn
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
