FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir .
COPY apps/control-plane /app/apps/control-plane
ENV PYTHONPATH=/app/apps/control-plane
ENV DATABASE_URL=sqlite:////app/data/agent.db
RUN mkdir -p /app/data
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
