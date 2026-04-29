FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY config/ config/

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "api_chaos_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
