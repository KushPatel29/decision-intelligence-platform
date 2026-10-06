FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /opt/program
COPY aws/requirements-container.txt /opt/program/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY aws/portfolio_entry.py aws/process_portfolio.py aws/evaluate_portfolio.py aws/container.py /opt/program/
EXPOSE 8080
ENTRYPOINT ["python", "/opt/program/container.py"]
