# Module 4b: much simpler than the old model-serving Dockerfile - no xgboost/scikit-learn
# means no C/C++ toolchain is needed, so this is a single stage instead of a multi-stage
# build. Also: only schema.json is copied in, not the joblib model files - the actual
# model and its weights live inside the SageMaker endpoint's own container now, not here.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY model_artifacts/schema.json ./model_artifacts/schema.json

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
