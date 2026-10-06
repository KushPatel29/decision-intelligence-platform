FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 CORRIDOR_ROOT=/app CORRIDOR_ENV=production CORRIDOR_AUTH=oidc
WORKDIR /app
COPY requirements-runtime.txt ./
RUN pip install -r requirements-runtime.txt && useradd --uid 10001 --create-home corridor
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-deps .
COPY app.py ./
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY outputs ./outputs
COPY output/pdf ./output/pdf
RUN mkdir -p /app/runtime && chown -R corridor:corridor /app
USER corridor
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.enableXsrfProtection=true", "--server.enableCORS=true", "--server.maxUploadSize=10"]
