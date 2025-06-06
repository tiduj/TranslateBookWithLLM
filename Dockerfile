# Use a base image with Python
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the application files into the container
COPY translate.py .
COPY translation_api.py .
COPY translation_interface.html .
COPY static/ ./static/

# Install the required Python dependencies for the web interface
# As per the README, these are the recommended dependencies
RUN pip install --no-cache-dir flask flask-cors flask-socketio python-socketio requests tqdm aiohttp lxml ebooklib

# Expose the port that the Flask application will run on
EXPOSE 5000

# Command to run the Flask API server
CMD ["python", "translation_api.py"]
