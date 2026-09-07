FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Both the FastAPI backend and the Streamlit UI are built from this same
# image (see docker-compose.yml) — the UI service overrides CMD to run
# Streamlit instead of rebuilding a second image for one extra process.
EXPOSE 8000
EXPOSE 8501
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
