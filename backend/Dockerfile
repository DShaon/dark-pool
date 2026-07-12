FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config ./config
COPY prompts ./prompts

# data/ (file-backed stores: roster, calibration, lessons, paper broker...)
# is intentionally NOT baked into the image — it's runtime state. Mount a
# volume at /srv/data in production so it survives container restarts.
RUN mkdir -p /srv/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
