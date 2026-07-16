# ide8.flow generation worker.
# Build context is the REPO ROOT (the worker reads schema/ and the render
# exemplar from sibling paths):
#   docker build -t ide8-worker -f services/worker/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

COPY services/worker/requirements.txt services/worker/requirements.txt
RUN pip install --no-cache-dir -r services/worker/requirements.txt

COPY schema/ schema/
COPY services/render/examples/example.json services/render/examples/example.json
COPY services/worker/ services/worker/

# SQLite store on a volume until the Supabase migration (PRD §9)
ENV WORKER_DB=/data/ide8.db
VOLUME /data

WORKDIR /app/services/worker
EXPOSE 8200

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8200"]
