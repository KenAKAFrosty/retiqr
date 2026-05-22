FROM python:3.12-slim

WORKDIR /app

COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/gateway.py .
COPY gateway/static/ static/
# Use shared/framing.py directly — no shim needed in the container
COPY shared/framing.py .

EXPOSE 8080

ENTRYPOINT ["python", "gateway.py"]
