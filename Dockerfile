# Use a lightweight Python image (base image)
FROM python:3.11-slim

# workdir
WORKDIR /ChatBot_app

# Copy requirements.txt first (for better caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Expose the port FastAPI will run on
EXPOSE 8000

# Run FastAPI with Uvicorn
CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]