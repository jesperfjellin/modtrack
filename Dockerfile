FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy source code
COPY src/ /app/src/
COPY pyproject.toml .
COPY README.md .

# Install the package
RUN pip install -e .

CMD ["python", "-m", "modtrack.main", "--directory", "/data/model_results"]
