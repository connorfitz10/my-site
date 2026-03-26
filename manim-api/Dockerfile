FROM manimcommunity/manim:latest

USER root

WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic sympy

COPY main.py .

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
