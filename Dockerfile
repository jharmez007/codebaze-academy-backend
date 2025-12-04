# Use official Python image
FROM python:3.13

WORKDIR /app

# Install system dependencies for MySQL + WeasyPrint on Amazon Linux
RUN yum update -y && \
    yum install -y \
    gcc \
    python3-devel \
    libffi-devel \
    mariadb-connector-c-devel \
    cairo \
    cairo-devel \
    pango \
    pango-devel \
    gdk-pixbuf2 \
    gdk-pixbuf2-devel \
    shared-mime-info \
    && yum clean all

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
