# ide8.flow render service (PRD RND-1)
# ubuntu:24.04 ships Scribus 1.6.1 — matches the donor template pin.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        scribus \
        xvfb \
        xauth \
        poppler-utils \
        fonts-liberation \
        fontconfig \
        python3 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY sla_compiler.py template.sla ./
COPY service/ service/
COPY examples/ examples/
COPY tests/ tests/

EXPOSE 8000

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
