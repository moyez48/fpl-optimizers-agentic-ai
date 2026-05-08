# 1. Start with a lightweight Python environment
FROM python:3.10-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy your requirements and install them
COPY requirements.txt .
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the rest of your repository (agents, backend, data) into the container
COPY . .

# 5. Tell the container to open port 7860 (Hugging Face's default)
EXPOSE 7860

# 6. Start your FastAPI server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
