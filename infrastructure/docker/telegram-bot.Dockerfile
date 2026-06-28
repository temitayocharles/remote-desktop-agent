FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir .
COPY apps/telegram-bot /app/apps/telegram-bot
ENV PYTHONPATH=/app/apps/telegram-bot
CMD ["python", "/app/apps/telegram-bot/bot.py"]
