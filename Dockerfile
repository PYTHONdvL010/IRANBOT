FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
COPY web_panel.py .
COPY mini_app.py .
RUN mkdir -p /app/data
CMD ["python", "bot.py"]
