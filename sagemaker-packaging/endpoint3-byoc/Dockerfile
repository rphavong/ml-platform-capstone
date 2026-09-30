# Same pattern as endpoint1-byoc / endpoint2-byoc. Endpoint3's model is different (spatial
# neighbor-composition features + gene expression, 4527 features total, needs scikit-learn's
# NearestNeighbors at request time too) but the pinned versions and container shape are
# identical - requirements.txt already includes scikit-learn.
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY sagemaker_serve.py .
COPY serve /usr/local/bin/serve
RUN chmod +x /usr/local/bin/serve

# No model_artifacts copied here - SageMaker injects those into /opt/ml/model/ itself
# from the model.tar.gz in S3, at container start.

EXPOSE 8080
ENTRYPOINT ["serve"]
