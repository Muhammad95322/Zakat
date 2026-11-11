FROM python:3.11-slim

WORKDIR /app

# Tidak perlu compiler: semua dependensi tersedia sebagai wheel untuk Python 3.11
# (diverifikasi dengan pip install --only-binary=:all:), sehingga image lebih kecil
# dan build tidak bergantung pada mirror apt.

# Install python dependencies
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

# Copy source code
COPY . .

# Buat folder uploads dan jalankan init database
RUN mkdir -p uploads data/sample data/template

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python scripts/check_health.py || exit 1

# Validasi konfigurasi dulu (container menolak start jika APP_ENV=production dengan kunci tidak aman),
# lalu buat tabel basis data agar healthcheck langsung sehat tanpa menunggu kunjungan pertama.
CMD ["sh", "-c", "python scripts/validate_config.py && python -c 'from src.database import init_db; init_db()' && exec streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true"]

