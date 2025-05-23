# Use a base image with Python
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the application files into the container
# This copies translate.py, translation_api.py, and translation_interface.html
COPY translate.py .
COPY translation_api.py .
COPY translation_interface.html .

# Install the required Python dependencies for the web interface
# As per the README and translation_api.py, these are for the web interface.
RUN pip install --no-cache-dir flask flask-cors flask-socketio python-socketio requests tqdm aiohttp

# Expose the port that the Flask application will run on
EXPOSE 5000

# Command to run the Flask API server
# This will start the web interface accessible via http://localhost:5000
CMD ["python", "translation_api.py"]