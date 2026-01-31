FROM python:3.11-slim

# Keep logs visible in kubectl
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files (including the main.py with the token)
COPY . .

# Run the bot
CMD ["python", "main.py"]
