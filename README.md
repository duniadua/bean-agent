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
Anda dapat memasang dependensi langsung untuk user lokal tanpa perlu `.venv` (aman tanpa merusak paket sistem):

```bash
python3 -m pip install --user google-genai python-dotenv pytest
```

### 2. Konfigurasi Variabel Environment & Kunci Dekripsi

#### A. Jika menggunakan file `.env` biasa (Plaintext lokal):
Buat berkas `.env` dengan format:
```env
GEMINI_API_KEY="AIzaSy..."
REGISTERED_APPS='{"frontend":"/var/www/frontend"}'
```

#### B. Jika menggunakan `.env` Terenkripsi (dengan `dotenvx`):
1. **Di Laptop Anda (Untuk mengambil private key):**
   ```bash
   dotenvx keypair
   ```
2. **Di Server Production (Simpan private key sekali secara permanen):**
   Buat file `.env.keys` di folder proyek:
   ```bash
   echo 'DOTENV_PRIVATE_KEY="8067dbf8c869079d490e964e85d05d2da37d4496a112130759c2ac0bf4beff50"' > .env.keys
   ```
   *(Atau tambahkan `export DOTENV_PRIVATE_KEY="..."` ke `~/.bashrc`).*

---

### 3. Menjalankan Agent

Pilih perintah sesuai metode yang Anda gunakan:

#### ✅ Menggunakan `dotenvx` (Rekomendasi - Terenkripsi):
Jika sudah memasang `dotenvx` dan memiliki `.env.keys` atau `DOTENV_PRIVATE_KEY`:
```bash
dotenvx run -- python3 bean_agent.py
```

*Jika ingin langsung meng-inject key dalam satu baris perintah tanpa file `.env.keys`:*
```bash
DOTENV_PRIVATE_KEY="8067dbf8c869079d490e964e85d05d2da37d4496a112130759c2ac0bf4beff50" dotenvx run -- python3 bean_agent.py
```

#### 🔹 Tanpa `dotenvx` (Menggunakan `.env` biasa):
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
