FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libcairo2-dev \
    libffi-dev \
    libgl1 \
    libglib2.0-0 \
    libpango1.0-dev \
    pkg-config \
    texlive-fonts-recommended \
    texlive-latex-base \
    texlive-latex-extra \
    dvisvgm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY app ./app
COPY reference_scenes.py manim.cfg ./

RUN useradd --create-home --uid 10001 vivacity \
    && mkdir -p /app/outputs /var/lib/vivacity/jobs /var/lib/vivacity/cache /var/lib/vivacity/learning \
    && chown -R vivacity:vivacity /app /var/lib/vivacity

USER vivacity

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
