FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY bot_api.py commands_bot.py /app/
USER 10001:10001
CMD ["python", "/app/commands_bot.py"]
