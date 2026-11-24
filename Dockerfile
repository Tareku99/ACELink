FROM node:22-bookworm-slim AS webui
WORKDIR /webui
COPY webui/package.json webui/package-lock.json ./
RUN npm ci
COPY webui/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    ACELINK_CONFIG_PATH=/data/acelink.config.json
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 acelink \
    && useradd --uid 10001 --gid 10001 --no-create-home acelink \
    && install -d -o acelink -g acelink /data
COPY *.py ./
COPY --from=webui /webui/dist ./webui/dist
USER acelink
EXPOSE 8765
VOLUME ["/data"]
ENTRYPOINT ["python", "main.py"]
