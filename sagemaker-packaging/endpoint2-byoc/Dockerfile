# Same pinned versions as services/endpoint1-flex/Dockerfile (Module 3) - that's the whole
# point of this image: it's proven to load this exact model correctly, unlike AWS's
# pre-built container. --platform linux/amd64 at build time (see deploy steps) matters
# because SageMaker's standard instance types are x86_64, and this may be built on an
# Apple Silicon (arm64) Mac otherwise.
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
# from the model.tar.gz in S3, at container start. That's different from Module 3's
# image, which bundled the model files directly since nothing else was doing that job.

# SageMaker always runs `docker run <image> serve` - ENTRYPOINT (not CMD) is what makes
# that "serve" argument land as $1 in our script instead of overwriting the whole command.
EXPOSE 8080
ENTRYPOINT ["serve"]
