FROM python:3.10-slim
WORKDIR /app
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt ./
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt
COPY app ./app
RUN mkdir -p /app/uploads
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
