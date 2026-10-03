# 🤖 Bean Agent - AI Server Ops & Deployment Assistant

**Bean Agent** adalah asisten CLI berbasis AI yang ditenagai oleh Google Gemini (`gemini-3.8-flash`) via SDK `google-genai`. Agent ini dirancang untuk memantau status repository git, memeriksa dan menganalisis konfigurasi Docker Compose, melihat log container, serta melakukan deployment aman dengan mekanisme **Human-in-the-Loop** dan **Root Cause Analysis (RCA)** otomatis saat terjadi kendala.

---

## 🌟 Fitur Utama

1. **Deteksi Framework Otomatis & Deployment Fleksibel (Docker & Non-Docker)**:
   * **`detect_framework_and_strategy`**: Mendeteksi teknologi/framework yang digunakan oleh proyek target beserta strategi deployment terbaik.
   * **Dukungan Multi-Stack Non-Docker**:
     * **Node.js / Next.js / Nuxt / React / Vue**: `npm/pnpm/yarn install` $\rightarrow$ `build` $\rightarrow$ `pm2 reload` (jika menggunakan PM2).
     * **Python / Django / FastAPI**: Virtual environment auto-detection (`.venv`, `venv`) $\rightarrow$ `pip/poetry install` $\rightarrow$ `python manage.py migrate` $\rightarrow$ `collectstatic`.
     * **PHP / Laravel**: `composer install` $\rightarrow$ `php artisan migrate` $\rightarrow$ `config/route/view:cache`.
     * **Golang & Rust**: `go mod download` $\rightarrow$ `go build` / `cargo build --release`.
   * **Dukungan Docker Compose**: Tetap mendukung pipeline containerized (`docker compose up -d --build`).

2. **Guardrail Keamanan Ketat Human-in-the-Loop (HITL) untuk Tindakan Destruktif**:
   * **`cleanup_or_remove_app_resources`**: Melindungi operasi berbahaya seperti menghentikan container (`docker compose stop`), menghapus container & network (`docker compose down`), menghapus volume database/persisten (`docker compose down -v`), atau membersihkan direktori build/cache (`node_modules`, `.next`, `.venv`).
   * **Alasan Kebijakan Anti-Otonom**: Agent **DILARANG KERAS** mengeksekusi aksi ini tanpa izin manusia guna mencegah:
     * *Irreversible Data Loss*: Kehilangan data database atau persistent volume yang tidak dapat dipulihkan.
     * *Unplanned Downtime*: Penghentian server produksi tanpa pemberitahuan/mitigasi.
     * *Salah Sasaran*: Menghindari eksekusi pada aplikasi/folder yang salah akibat ambiguitas prompt.
   * **Mekanisme Konfirmasi Eksplisit**: User diwajibkan mengetik token kata kunci **`DELETE`** secara sadar untuk mengonfirmasi eksekusi.

3. **Human-in-the-Loop Deployment Safety**:
   * Menampilkan ringkasan framework yang terdeteksi dan meminta konfirmasi interaktif admin (`[y/N]`) sebelum build/deploy dijalankan.

4. **Dukungan Root Cause Analysis (RCA)**:
   * Jika tahapan pull, dependensi install, atau build gagal, agent otomatis menganalisis akar masalah (*merge conflict*, *dependency conflict*, *build syntax error*, *port conflict*, dll.) dan memberikan rekomendasi solusi konkret.

5. **Docker Compose Inspection Tools (Read-Only)**:
   * `get_compose_file`: Membaca file konfigurasi compose.
   * `validate_compose_syntax`: Mengevaluasi sintaks YAML & skema via `docker compose config`.
   * `get_container_logs`: Membaca log container/service tertentu.

6. **Monitoring Status Git, Container, & Native Process**:
   * `check_status`: Mengecek status update git serta status runtime (baik `docker compose ps` maupun proses native seperti `pm2 status`).

---

## 📋 Persyaratan Sistem

- Python 3.10+
- Git terpasang dan terkonfigurasi pada repositori target
- Docker & Docker Compose plugin terpasang
- Kunci API Google Gemini ([Google AI Studio](https://aistudio.google.com/))

---

## 🚀 Panduan Instalasi & Penggunaan

### 1. Pasang Dependensi
Pastikan dependensi Python yang dibutuhkan sudah terpasang:

```bash
pip install google-genai python-dotenv pytest
```

### 2. Konfigurasi Variabel Environment (`.env`)
Buat berkas `.env` di folder utama dengan format berikut:

```env
# Kunci API Gemini Anda
GEMINI_API_KEY="AIzaSy..."

# Daftar aplikasi terdaftar dalam format JSON (nama aplikasi: path lokal direktori)
REGISTERED_APPS='{
  "frontend": "/Users/macbook/apps/frontend-repo",
  "backend-api": "/Users/macbook/apps/backend-repo"
}'
```

> **Catatan**: Jika menggunakan `dotenvx` untuk enkripsi variabel environment, file tetap dapat dimuat dengan aman di runtime.

### 3. Menjalankan Agent

Jalankan skrip utama:

```bash
python3 bean_agent.py
```

### 4. Contoh Interaksi Chat

```text
=================================================
 🤖 AI DEPLOYMENT AGENT (Gemini 3.8 Flash)
=================================================
 App Terdaftar : ['frontend', 'backend-api']
 Ketik 'exit' atau 'quit' untuk keluar.
=================================================

Admin ❯ Bagaimana status aplikasi backend-api saat ini?
Agent ❯ Memeriksa status git dan container backend-api...

Admin ❯ Tolong cek apakah sintaks file docker-compose di backend-api sudah valid?
Agent ❯ Konfigurasi Docker Compose untuk 'backend-api' VALID (tidak ada error sintaks).

Admin ❯ Tampilkan 20 baris log terakhir service db di backend-api
Agent ❯ Menampilkan log container service 'db'...

Admin ❯ Tolong deploy update terbaru untuk frontend
[⚠️  PERINGATAN SISTEM] Agent meminta otorisasi deployment untuk: frontend
Lanjutkan deployment (git pull & docker build) untuk frontend? [y/N]: y
```

---

## 🧪 Menjalankan Pengujian (Testing)

Proyek ini telah dilengkapi dengan unit test dan smoke test komprehensif:

```bash
pytest -v test_server_ops.py
```

Cakupan pengujian mencakup:
- Eksekusi subprocess lokal dengan proteksi timeout
- Validasi registrasi aplikasi dan direktori lokal
- Otorisasi deployment (batal / lanjut)
- Penanganan error alur deploy & pembentukan diagnostik RCA
- Tool inspeksi konfigurasi dan log Docker Compose
- Validasi integritas tool dan schema binding Gemini SDK
