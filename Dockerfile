FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

# Environment variables defaults
ENV PORKBUN_API_KEY=""
ENV PORKBUN_SECRET_KEY=""
ENV CLOUDFLARE_API_TOKEN=""
ENV ADGUARD_HOME_URL=""
ENV ADGUARD_HOME_USERNAME=""
ENV ADGUARD_HOME_PASSWORD=""
ENV SYNC_TOKEN=""
ENV MANAGED_TYPES=CNAME
ENV PORT=8000

EXPOSE 8000

# Run the application
CMD ["python", "main.py"]
