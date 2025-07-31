FROM python:3.11-slim
WORKDIR /app
COPY .env.local ./test.txt
RUN ls -la
CMD ["echo", "test"]
