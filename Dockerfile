FROM python:3.11-slim

# Metadata
LABEL maintainer="Cuadros de Carga Platform"
LABEL description="Aplicación web Streamlit para Cuadros de Carga de Alumbrado Público Vial Chile"

# Variables de entorno del sistema
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema (mínimas para psycopg2 y reportlab)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar código fuente
COPY . .

# Crear directorios de datos
RUN mkdir -p uploads

# Puerto por defecto de Streamlit
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Comando de inicio
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
