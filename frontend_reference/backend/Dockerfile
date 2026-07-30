# Use the official Manim community image — ships with LaTeX (TeX Live), FFmpeg, Cairo, Pango
FROM ghcr.io/manimcommunity/manim:stable

USER root

# Install additional Python dependencies on top of what Manim already provides
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Working directory
WORKDIR /app

# Copy backend source
COPY main.py prompts.py ./

# Output videos directory
RUN mkdir -p outputs && chmod 777 outputs

# Expose port (Railway sets $PORT automatically)
EXPOSE 8000

# Start FastAPI
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
