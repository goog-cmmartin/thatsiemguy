# 1. Use an official Python runtime as a parent image
#    Choose a version compatible with your code (e.g., 3.11, 3.10, etc.)
#    Using '-slim' results in a smaller image size.
FROM python:3.11-slim

# 2. Set environment variables
#    PYTHONDONTWRITEBYTECODE: Prevents Python from writing .pyc files to disc (optional)
#    PYTHONUNBUFFERED: Prevents Python from buffering stdout and stderr (recommended for logging)
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Set the working directory in the container
WORKDIR /app

# 4. Copy the requirements file into the container at /app
#    Ensure you have a requirements.txt file listing all dependencies
#    (Flask, google-cloud-secret-manager, google-auth, requests, PyYAML, gunicorn, etc.)
COPY requirements.txt .

# 5. Install any needed packages specified in requirements.txt
#    --no-cache-dir: Disables the pip cache, making the image smaller
#    --system: Installs packages into the system site-packages, useful for some buildpack compatibility if needed (often optional)
#    Consider using --require-hashes if you have a fully pinned requirements file for security.
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of your application source code into the container at /app
COPY . .

# (Optional but good practice) Expose the port Gunicorn will run on.
# Cloud Run sets the PORT env var automatically, Gunicorn binds to it below.
EXPOSE 8080

# 7. Define the command to run your app using Gunicorn
#    This is where you put your specific command.
#    'exec' ensures Gunicorn replaces the shell process (PID 1).
#    '--bind :$PORT' binds to the port specified by Cloud Run.
#    '--workers 1 --threads 8' sets the worker/thread configuration.
#    '--timeout 0' disables the Gunicorn worker timeout.
#    'main:app' should match your Python file name (main.py) and Flask app instance name (app).
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
