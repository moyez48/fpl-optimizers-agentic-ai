FROM python:3.11-slim

# Hugging Face requires a non-root user
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Copy application files with proper permissions
COPY --chown=user . /app

# Install dependencies (root requirements.txt includes backend/requirements.txt)
RUN pip install --no-cache-dir -r requirements.txt

# Hugging Face strict requirement: App MUST listen on port 7860
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
