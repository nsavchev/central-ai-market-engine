FROM python:3.12-slim
WORKDIR /srv
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn>=0.30,<1" "httpx>=0.27,<1"
COPY central_ai /srv/central_ai
COPY developer_agent /srv/developer_agent
USER 10001
CMD ["uvicorn","central_ai.app:app","--host","0.0.0.0","--port","8010"]
