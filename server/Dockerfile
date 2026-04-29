FROM python:3.13

WORKDIR /app

RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    libmagic-dev \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy dependency files first for better layer caching
COPY pyproject.toml poetry.lock* ./

# Configure Poetry to not create virtual env (we're already in a container)
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --only main --no-interaction --no-ansi --no-root \
    && pip uninstall -y torch torchvision \
    && pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu \
    && rm -rf /root/.cache \
    && rm -rf /usr/local/lib/python3.13/site-packages/nvidia* \
    && rm -rf /usr/local/lib/python3.13/site-packages/triton* \
    && rm -rf /usr/local/lib/python3.13/site-packages/cuda*

# Copy the rest of the application
COPY . .

EXPOSE 8000
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]