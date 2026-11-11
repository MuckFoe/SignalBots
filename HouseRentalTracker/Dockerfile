FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Headless Chromium for the LLM fallback's browser step (RENTAL_BROWSER_ENABLED).
# Only the headless shell + its system libs (~250-300 MB). Build with
# --build-arg INSTALL_BROWSER=0 to skip it; the browser step then just reports failure.
ARG INSTALL_BROWSER=1
# libatomic1: Playwright's bundled node needs it and the slim image lacks it.
RUN if [ "$INSTALL_BROWSER" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends libatomic1 \
        && python -m playwright install --with-deps --only-shell chromium \
        && rm -rf /var/lib/apt/lists/*; \
    fi

COPY . /app

EXPOSE 5001

CMD ["python", "app.py"]
