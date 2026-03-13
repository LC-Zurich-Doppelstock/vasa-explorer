FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY main.py theme.py sandbox.py resources.py ./

EXPOSE 9000

CMD ["python", "main.py"]
