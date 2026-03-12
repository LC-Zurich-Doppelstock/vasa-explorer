FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY main.py theme.py sandbox.py resources.py ./

# Copy the dataset (baked into the image)
COPY results_clean.csv /data/results_clean.csv

EXPOSE 9000

CMD ["python", "main.py"]
