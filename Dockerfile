FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 BOOKINGS_PATH=/data/bookings.json
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY campaigns ./campaigns
EXPOSE 8000
CMD ["python", "-m", "sales_agent", "serve"]
