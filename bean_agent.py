import os
import sys
import subprocess
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Muat variabel dari berkas .env
load_dotenv()

# ==========================================
# 1. INISIALISASI KONFIGURASI DARI .ENV
# ==========================================
API_KEY = os.getenv("GEMINI_API_KEY")
apps_env = os.getenv("REGISTERED_APPS")

REGISTERED_APPS = {}
if apps_env:
    try:
        REGISTERED_APPS = json.loads(apps_env)
    except json.JSONDecodeError:
        print("[Fatal Error] Format REGISTERED_APPS di .env tidak valid. Pastikan menggunakan format JSON.")
        if __name__ == "__main__":
            sys.exit(1)


def validate_environment():
    """Validasi keberadaan variabel environment wajib saat aplikasi dijalankan."""
    if not API_KEY:
        print("[Fatal Error] GEMINI_API_KEY tidak ditemukan di berkas .env")
        sys.exit(1)
    if not apps_env or not REGISTERED_APPS:
        print("[Fatal Error] REGISTERED_APPS tidak ditemukan atau kosong di berkas .env")
        sys.exit(1)


def run_cmd(command: list, cwd: str, timeout: int = 120) -> str:
    """Fungsi pembantu untuk eksekusi shell lokal dengan batas waktu timeout."""
    try:
        res = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            text=True,
            capture_output=True,
            timeout=timeout
        )
        return res.stdout.strip()
    except subprocess.TimeoutExpired:
        return f"ERROR: Perintah '{' '.join(command)}' melebihi batas waktu (timeout {timeout} detik)."
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() or e.stdout.strip()
        return f"ERROR ({e.returncode}): {error_msg}"
    except Exception as e:
        return f"ERROR: {str(e)}"

# ==========================================
# 2. DEFINISI TOOLS & DETEKSI FRAMEWORK
# ==========================================

def detect_project_type(path: str) -> dict:
    """
    Mendeteksi jenis framework/stack dan metode deployment (Docker vs Native/Non-Docker).
    Mengembalikan dict berisi:
    - is_docker: bool (apakah memiliki docker-compose)
    - framework: str (nama framework / runtime terdeteksi)
    - deploy_steps: list of list string (langkah perintah build/install/restart)
    - description: str (penjelasan ringkas metode deploy)
    """
    has_compose = any(os.path.isfile(os.path.join(path, f)) for f in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"])
    
    # Deteksi Docker Compose
    if has_compose:
        return {
            "mode": "docker",
            "framework": "Docker Compose",
            "description": "Deployment berbasis Docker Compose (up -d --build)",
            "deploy_steps": [
                ["docker", "compose", "up", "-d", "--build"]
            ]
        }
    
    # Deteksi Node.js / Frontend / Backend
    pkg_json_path = os.path.join(path, "package.json")
    if os.path.isfile(pkg_json_path):
        pkg_data = {}
        try:
            with open(pkg_json_path, "r", encoding="utf-8") as f:
                pkg_data = json.load(f)
        except Exception:
            pass
            
        deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
        scripts = pkg_data.get("scripts", {})
        
        # Manajer paket
        pkg_manager = "npm"
        if os.path.isfile(os.path.join(path, "pnpm-lock.yaml")):
            pkg_manager = "pnpm"
        elif os.path.isfile(os.path.join(path, "yarn.lock")):
            pkg_manager = "yarn"
            
        steps = [[pkg_manager, "install"]]
        if "build" in scripts:
            steps.append([pkg_manager, "run", "build"])
            
        # Restart process runner jika ada (pm2 / systemctl)
        ecosystem_file = any(os.path.isfile(os.path.join(path, f)) for f in ["ecosystem.config.js", "ecosystem.config.cjs", "pm2.json"])
        if ecosystem_file:
            steps.append(["pm2", "reload", "all"])
            desc_runner = " + PM2 Reload"
        else:
            desc_runner = ""

        # Identifikasi Framework Spesifik
        if "next" in deps:
            return {"mode": "native", "framework": "Next.js (Node.js)", "description": f"Next.js build pipeline ({pkg_manager} install -> build{desc_runner})", "deploy_steps": steps}
        elif "nuxt" in deps:
            return {"mode": "native", "framework": "Nuxt (Vue.js)", "description": f"Nuxt build pipeline ({pkg_manager} install -> build{desc_runner})", "deploy_steps": steps}
        elif "react" in deps:
            return {"mode": "native", "framework": "React App", "description": f"React build pipeline ({pkg_manager} install -> build)", "deploy_steps": steps}
        elif "vue" in deps:
            return {"mode": "native", "framework": "Vue App", "description": f"Vue build pipeline ({pkg_manager} install -> build)", "deploy_steps": steps}
        elif "express" in deps or "fastify" in deps or "nestjs" in deps or "@nestjs/core" in deps:
            return {"mode": "native", "framework": "Node.js Backend", "description": f"Node.js server ({pkg_manager} install -> build/restart)", "deploy_steps": steps}
        else:
            return {"mode": "native", "framework": "Node.js Application", "description": f"Node.js app ({pkg_manager} install -> build)", "deploy_steps": steps}

    # Deteksi Python (Django, FastAPI, Flask, dll)
    is_python = any(os.path.isfile(os.path.join(path, f)) for f in ["requirements.txt", "pyproject.toml", "Pipfile", "manage.py"])
    if is_python:
        steps = []
        # Cek virtualenv lokal
        pip_cmd = "pip"
        python_cmd = "python3"
        for venv_dir in [".venv", "venv", "env"]:
            venv_pip = os.path.join(path, venv_dir, "bin", "pip")
            venv_python = os.path.join(path, venv_dir, "bin", "python")
            if os.path.isfile(venv_pip):
                pip_cmd = venv_pip
                python_cmd = venv_python
                break

        if os.path.isfile(os.path.join(path, "requirements.txt")):
            steps.append([pip_cmd, "install", "-r", "requirements.txt"])
        elif os.path.isfile(os.path.join(path, "pyproject.toml")):
            if os.path.isfile(os.path.join(path, "poetry.lock")):
                steps.append(["poetry", "install"])
            else:
                steps.append([pip_cmd, "install", "."])

        # Django
        if os.path.isfile(os.path.join(path, "manage.py")):
            steps.append([python_cmd, "manage.py", "migrate", "--noinput"])
            steps.append([python_cmd, "manage.py", "collectstatic", "--noinput"])
            return {"mode": "native", "framework": "Django (Python)", "description": "Django pipeline (pip install -> migrate -> collectstatic)", "deploy_steps": steps}
        
        return {"mode": "native", "framework": "Python Application", "description": "Python dependency install (pip/poetry)", "deploy_steps": steps}

    # Deteksi PHP / Laravel
    if os.path.isfile(os.path.join(path, "composer.json")):
        steps = [["composer", "install", "--no-dev", "--optimize-autoloader"]]
        if os.path.isfile(os.path.join(path, "artisan")):
            steps.append(["php", "artisan", "migrate", "--force"])
            steps.append(["php", "artisan", "config:cache"])
            steps.append(["php", "artisan", "route:cache"])
            steps.append(["php", "artisan", "view:cache"])
            return {"mode": "native", "framework": "Laravel (PHP)", "description": "Laravel pipeline (composer install -> migrate -> config/route cache)", "deploy_steps": steps}
        return {"mode": "native", "framework": "PHP (Composer)", "description": "PHP Composer install", "deploy_steps": steps}

    # Deteksi Go
    if os.path.isfile(os.path.join(path, "go.mod")):
        steps = [["go", "mod", "download"], ["go", "build", "-o", "app_bin"]]
        return {"mode": "native", "framework": "Go (Golang)", "description": "Go build pipeline (go mod download -> go build)", "deploy_steps": steps}

    # Deteksi Rust
    if os.path.isfile(os.path.join(path, "Cargo.toml")):
        steps = [["cargo", "build", "--release"]]
        return {"mode": "native", "framework": "Rust (Cargo)", "description": "Rust build pipeline (cargo build --release)", "deploy_steps": steps}

    # Fallback / Generic Git Pull Only
    return {
        "mode": "native",
        "framework": "Generic / Static Web",
        "description": "Aplikasi standar (hanya git pull sync)",
        "deploy_steps": []
    }


def detect_framework_and_strategy(app_name: str) -> str:
    """
    Tugas: Menganalisis direktori aplikasi dan mendeteksi framework/teknologi yang digunakan,
    serta strategi deployment umum yang disarankan (baik via Docker maupun Native/Non-Docker).
    Fungsi ini aman (read-only).
    """
    if app_name not in REGISTERED_APPS:
        return f"Error: Aplikasi '{app_name}' tidak terdaftar."
    
    path = REGISTERED_APPS[app_name]
    if not os.path.isdir(path):
        return f"Error: Direktori '{path}' untuk aplikasi '{app_name}' tidak ditemukan di server."
    
    info = detect_project_type(path)
    steps_formatted = "\n".join([f"  {idx+1}. " + " ".join(step) for idx, step in enumerate(info["deploy_steps"])]) if info["deploy_steps"] else "  (Tidak ada langkah build khusus, hanya sinkronisasi repository)"
    
    return (
        f"--- ANALISIS FRAMEWORK & STRATEGI DEPLOYMENT ({app_name}) ---\n"
        f"Lokasi Path      : {path}\n"
        f"Framework/Stack  : {info['framework']}\n"
        f"Metode Deploy    : {info['mode'].upper()}\n"
        f"Keterangan       : {info['description']}\n"
        f"Rencana Eksekusi :\n"
        f"  - git pull (selalu dijalankan terlebih dahulu)\n"
        f"{steps_formatted}"
    )


def check_status(app_name: str) -> str:
    """
    Tugas: Mengecek status repository git (apakah ada update) dan status proses/container.
    Fungsi ini aman (read-only) dan bisa dieksekusi kapan saja tanpa konfirmasi.
    """
    if app_name not in REGISTERED_APPS:
        return f"Error: Aplikasi '{app_name}' tidak terdaftar."
    
    path = REGISTERED_APPS[app_name]
    if not os.path.isdir(path):
        return f"Error: Direktori '{path}' untuk aplikasi '{app_name}' tidak ditemukan di server."
    
    # 1. Fetch & status git
    run_cmd(["git", "fetch", "origin"], path, timeout=60)
    git_status = run_cmd(["git", "status", "-uno"], path, timeout=30)
    
    # 2. Cek tipe proyek & status proses
    proj_info = detect_project_type(path)
    if proj_info["mode"] == "docker":
        runtime_status = "--- STATUS CONTAINER DOCKER ---\n" + run_cmd(["docker", "compose", "ps"], path, timeout=30)
    else:
        # Untuk non-docker, cek status PM2 atau status direktori
        pm2_status = run_cmd(["pm2", "status"], path, timeout=15)
        if not pm2_status.startswith("ERROR"):
            runtime_status = f"--- STATUS PROSES NATIVE (PM2) ---\n{pm2_status}"
        else:
            runtime_status = f"--- STATUS RUNTIME NATIVE ---\nMode: {proj_info['framework']} ({proj_info['description']})"
    
    return f"--- STATUS GIT ({app_name}) ---\n{git_status}\n\n{runtime_status}"


def deploy_app(app_name: str) -> str:
    """
    Tugas: Melakukan deployment aplikasi (git pull dilanjutkan dengan build/deploy sesuai framework atau docker compose).
    Fungsi ini memiliki pengaman interaktif (Human-in-the-loop).
    """
    if app_name not in REGISTERED_APPS:
        return f"Error: Aplikasi '{app_name}' tidak terdaftar."
    
    path = REGISTERED_APPS[app_name]
    if not os.path.isdir(path):
        return f"Error: Direktori '{path}' untuk aplikasi '{app_name}' tidak ditemukan di server."
    
    proj_info = detect_project_type(path)
    
    print(f"\n[⚠️  PERINGATAN SISTEM] Agent meminta otorisasi deployment untuk: {app_name}")
    print(f"Framework Terdeteksi: {proj_info['framework']} ({proj_info['mode'].upper()})")
    print(f"Rencana Deployment  : {proj_info['description']}")
    
    run_cmd(["git", "fetch", "origin"], path, timeout=60)
    status_awal = run_cmd(["git", "status", "-uno"], path, timeout=30)
    print(f"Info Repo Saat Ini:\n{status_awal}\n")
    
    # Hentikan eksekusi AI sementara, minta otorisasi human-in-the-loop
    konfirmasi = input(f"Lanjutkan deployment untuk {app_name} [{proj_info['framework']}]? [y/N]: ")
    
    if konfirmasi.lower() != 'y':
        print("[SISTEM] Dibatalkan oleh administrator.\n")
        return "User membatalkan proses deployment."

    # 1. Eksekusi git pull
    print("\n[SISTEM] Mengeksekusi git pull...")
    pull_log = run_cmd(["git", "pull"], path, timeout=60)
    
    if pull_log.startswith("ERROR"):
        print(f"[SISTEM] Deployment dibatalkan karena git pull gagal.\n{pull_log}\n")
        repo_diagnostics = run_cmd(["git", "status"], path, timeout=30)
        return (
            f"Deployment GAGAL pada tahap 'git pull'.\n"
            f"--- ERROR LOG GIT PULL ---\n{pull_log}\n\n"
            f"--- DIAGNOSTIK REPOSITORY (git status) ---\n{repo_diagnostics}\n\n"
            f"Tugas Agent: Analisis log error dan diagnostik di atas, tentukan root cause (akar masalah), "
            f"dan berikan rekomendasi solusi/perintah perbaikan untuk user."
        )
    
    # 2. Eksekusi tahapan deployment sesuai framework
    execution_logs = [f"Log Git Pull:\n{pull_log}"]
    
    for step in proj_info["deploy_steps"]:
        cmd_str = " ".join(step)
        print(f"[SISTEM] Mengeksekusi: {cmd_str}...")
        step_log = run_cmd(step, path, timeout=600)
        execution_logs.append(f"Command '{cmd_str}':\n{step_log}")
        
        if step_log.startswith("ERROR"):
            print(f"[SISTEM] Deployment GAGAL saat menjalankan '{cmd_str}'.\n{step_log}\n")
            all_logs = "\n\n".join(execution_logs)
            return (
                f"Deployment GAGAL pada perintah '{cmd_str}'.\n"
                f"Framework: {proj_info['framework']} ({proj_info['mode'].upper()})\n\n"
                f"--- LOG EKSEKUSI ---\n{all_logs}\n\n"
                f"Tugas Agent: Analisis pesan error di atas, tentukan root cause "
                f"(misal: dependensi error, build compile failed, syntax/migration issue), dan berikan rekomendasi solusinya."
            )

    print("[SISTEM] Deployment selesai dengan sukses.\n")
    all_logs = "\n\n".join(execution_logs)
    return f"Deploy berhasil!\nFramework: {proj_info['framework']}\n\n{all_logs}"


def get_compose_file(app_name: str) -> str:
    """
    Tugas: Membaca isi file docker-compose.yml / compose.yaml dari aplikasi yang terdaftar (Read-Only).
    Gunakan tool ini ketika perlu menganalisis konfigurasi, service, port, volume, atau environment.
    """
    if app_name not in REGISTERED_APPS:
        return f"Error: Aplikasi '{app_name}' tidak terdaftar."
    
    path = REGISTERED_APPS[app_name]
    if not os.path.isdir(path):
        return f"Error: Direktori '{path}' untuk aplikasi '{app_name}' tidak ditemukan."
    
    candidates = ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]
    for filename in candidates:
        full_path = os.path.join(path, filename)
        if os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return f"--- ISI FILE: {filename} ({app_name}) ---\n{content}"
            except Exception as e:
                return f"Error membaca {filename}: {str(e)}"
                
    return f"Error: File docker-compose.yml tidak ditemukan di {path}."


def validate_compose_syntax(app_name: str) -> str:
    """
    Tugas: Memvalidasi sintaks dan skema konfigurasi docker compose menggunakan 'docker compose config' (Read-Only).
    Gunakan tool ini jika ada kecurigaan kesalahan sintaks YAML, format field yang salah, atau interpolasi variabel.
    """
    if app_name not in REGISTERED_APPS:
        return f"Error: Aplikasi '{app_name}' tidak terdaftar."
    
    path = REGISTERED_APPS[app_name]
    if not os.path.isdir(path):
        return f"Error: Direktori '{path}' untuk aplikasi '{app_name}' tidak ditemukan."
    
    result = run_cmd(["docker", "compose", "config", "-q"], path, timeout=30)
    if result.startswith("ERROR"):
        # Jalankan tanpa -q untuk mengambil detail error sintaksis secara penuh
        detailed_error = run_cmd(["docker", "compose", "config"], path, timeout=30)
        return f"SINTAKS INVALID / ERROR:\n{detailed_error}"
    
    return f"Konfigurasi Docker Compose untuk '{app_name}' VALID (tidak ada error sintaks)."


def get_container_logs(app_name: str, service_name: str = "", tail: int = 50) -> str:
    """
    Tugas: Membaca log output container dari docker compose (Read-Only).
    Parameter:
    - app_name: Nama aplikasi terdaftar.
    - service_name: (Opsional) Nama service tertentu dalam compose. Jika kosong, mengambil log seluruh services.
    - tail: Jumlah baris terakhir yang ingin diambil (default: 50 baris).
    """
    if app_name not in REGISTERED_APPS:
        return f"Error: Aplikasi '{app_name}' tidak terdaftar."
    
    path = REGISTERED_APPS[app_name]
    if not os.path.isdir(path):
        return f"Error: Direktori '{path}' untuk aplikasi '{app_name}' tidak ditemukan."
    
    cmd = ["docker", "compose", "logs", f"--tail={tail}"]
    if service_name.strip():
        cmd.append(service_name.strip())
        
    logs = run_cmd(cmd, path, timeout=60)
    target = f"service '{service_name}'" if service_name.strip() else "semua service"
    return f"--- LOG DOCKER ({app_name} - {target}, {tail} baris terakhir) ---\n{logs}"


def cleanup_or_remove_app_resources(app_name: str, target_action: str) -> str:
    """
    Tugas: Melakukan tindakan destruktif (stop, down, remove container, hapus volume/cache, atau file/direktori).
    GUARDRAIL WAJIB:
    - Fungsi ini memiliki dampak fatal (downtime layanan, kehilangan volume data permanen, hilangnya file/database).
    - OLEH KARENA ITU, FUNGSI INI DILINDUNGI HUMAN-IN-THE-LOOP (HITL) DAN TIDAK BOLEH DIEKSEKUSI TANPA PERSETUJUAN EKSPLISIT DARI ADMINISTRATOR.
    Parameter:
    - app_name: Nama aplikasi terdaftar.
    - target_action: Jenis tindakan, pilihan:
        * 'stop_containers': Menghentikan container/proses yang berjalan.
        * 'remove_containers': docker compose down (menghapus container & network).
        * 'remove_with_volumes': docker compose down -v (HATI-HATI: menghapus volume data persisten/database).
        * 'clean_build_artifacts': Menghapus node_modules, build folder (dist/.next), atau .venv cache.
    """
    if app_name not in REGISTERED_APPS:
        return f"Error: Aplikasi '{app_name}' tidak terdaftar."
    
    path = REGISTERED_APPS[app_name]
    if not os.path.isdir(path):
        return f"Error: Direktori '{path}' untuk aplikasi '{app_name}' tidak ditemukan."

    actions_meta = {
        "stop_containers": {
            "title": "MENGHENTIKAN CONTAINER / LAYANAN (DOWNTIME SEMENTARA)",
            "impact": "Layanan aplikasi akan offline dan tidak dapat melayani traffic pengguna.",
            "cmd": ["docker", "compose", "stop"]
        },
        "remove_containers": {
            "title": "MENGHAPUS CONTAINER & NETWORK (docker compose down)",
            "impact": "Container akan dimatikan dan dihapus dari docker engine. Downtime penuh.",
            "cmd": ["docker", "compose", "down"]
        },
        "remove_with_volumes": {
            "title": "MENGHAPUS CONTAINER BESERTA VOLUME DATABASE / PERSISTENT DATA (docker compose down -v)",
            "impact": "BAHAYA KRITIS: Seluruh data volume database atau penyimpanan persisten akan HILANG SECARA PERMANEN dan TIDAK BISA DIKEMBALIKAN!",
            "cmd": ["docker", "compose", "down", "-v"]
        },
        "clean_build_artifacts": {
            "title": "MEMBERSIHKAN ARTIFAK BUILD & DEPENDENSI (node_modules/dist/.venv)",
            "impact": "File hasil build/cache akan dihapus. Memerlukan build ulang sebelum dapat dijalankan kembali.",
            "cmd": ["rm", "-rf", "node_modules", "dist", ".next", ".venv"]
        }
    }

    if target_action not in actions_meta:
        return f"Error: target_action '{target_action}' tidak dikenal. Pilihan valid: {list(actions_meta.keys())}"

    meta = actions_meta[target_action]

    # ========================================================
    # GUARDRAIL HUMAN-IN-THE-LOOP (HITL) CHECK
    # ========================================================
    print("\n" + "=" * 65)
    print(f"🛑 [GUARDRAIL KEAMANAN KRITIS - HUMAN IN THE LOOP (HITL)]")
    print("=" * 65)
    print(f"Aplikasi Target : {app_name} ({path})")
    print(f"Aksi Diminta    : {meta['title']}")
    print(f"Dampak Risiko   : {meta['impact']}")
    print(f"Perintah Shell  : {' '.join(meta['cmd'])}")
    print("-" * 65)
    print("ALASAN KEBIJAKAN GUARDRAIL:")
    print("Agent DILARANG KERAS mengeksekusi penghapusan/terminasi secara otonom")
    print("tanpa persetujuan manusia guna mencegah penghapusan data produksi yang")
    print("tidak disengaja, downtime tak terencana, atau kerusakan infrastruktur.")
    print("=" * 65)

    konfirmasi = input(f"\nApakah Anda yakin ingin MELANJUTKAN tindakan destruktif ini untuk '{app_name}'? Ketik 'DELETE' untuk konfirmasi: ")

    if konfirmasi.strip() != "DELETE":
        print("[SISTEM] Dibatalkan: Administrator menolak otorisasi penghapusan/terminasi.\n")
        return (
            f"Tindakan '{target_action}' untuk '{app_name}' DIBATALKAN oleh administrator.\n"
            f"Alasan: Penjaga keamanan Human-in-the-Loop menolak eksekusi karena konfirmasi token 'DELETE' tidak cocok."
        )

    print(f"\n[SISTEM] Administrator menyetujui. Mengeksekusi {' '.join(meta['cmd'])}...")
    res = run_cmd(meta["cmd"], path, timeout=120)
    print("[SISTEM] Tindakan selesai dieksekusi.\n")
    return f"Tindakan '{target_action}' berhasil dieksekusi oleh izin administrator.\nLog Output:\n{res}"


# ==========================================
# 3. CLI CHAT INTERFACE
# ==========================================

def main():
    validate_environment()
    client = genai.Client(api_key=API_KEY)
    
    config = types.GenerateContentConfig(
        system_instruction=(
            "Anda adalah AI Server Ops Senior. Tugas Anda merespons permintaan user terkait aplikasi berikut: "
            f"{list(REGISTERED_APPS.keys())}.\n\n"
            "Aturan Penggunaan Tools:\n"
            "1. Gunakan 'detect_framework_and_strategy' jika ditanya framework apa yang dipakai aplikasi atau strategi deployment apa yang akan dijalankan (baik Docker maupun Native/Non-Docker).\n"
            "2. Gunakan 'check_status' jika ditanya status git repository atau status container/proses yang sedang berjalan.\n"
            "3. Gunakan 'deploy_app' jika diminta deploy, update repo, atau build/restart aplikasi. Tool ini secara cerdas mendukung Docker Compose dan Non-Docker native stack (Node.js, Next.js, Python, Django, Laravel, Go, dll).\n"
            "4. Gunakan 'get_compose_file' jika diminta melihat isi konfigurasi docker-compose.yml atau mengevaluasi susunan servicenya.\n"
            "5. Gunakan 'validate_compose_syntax' jika diminta mengecek apakah sintaks docker compose valid atau ada error penulisan YAML/schema.\n"
            "6. Gunakan 'get_container_logs' jika diminta memeriksa log aplikasi/container di dalam docker compose untuk mendiagnosis crash/bug runtime.\n"
            "7. Gunakan 'cleanup_or_remove_app_resources' jika user meminta menghentikan (stop), menghapus (down/remove container), menghapus volume, atau membersihkan file build aplikasi.\n\n"
            "KEBIJAKAN GUARDRAIL & HUMAN-IN-THE-LOOP (HITL) UNTUK TINDAKAN PENGHAPUSAN / DELETE:\n"
            "- Setiap operasi yang bersifat destruktif (menghapus container, down compose, drop volume, hapus file/direktori, dsb.) WAJIB melalui guardrail HITL via tool 'cleanup_or_remove_app_resources'.\n"
            "- ALASAN MENGAPA TIDAK BOLEH DIEKSEKUSI TANPA HITL: AI dilarang mengeksekusi aksi destruktif secara otonom karena risiko kehilangan data permanen (irreversible data loss), downtime aplikasi produksi tanpa mitigasi, serta potensi salah target aplikasi.\n"
            "- Anda HARUS selalu mengedukasi dan mengingatkan user tentang dampak risiko destruktif sebelum dan sesudah aksi tersebut dipanggil.\n\n"
            "Aturan Root Cause Analysis (RCA) saat Terjadi Kegagalan:\n"
            "Jika hasil dari deploy_app atau check_status mengindikasikan kegagalan/ERROR:\n"
            "- Anda diperbolehkan secara proaktif memanggil 'get_compose_file', 'validate_compose_syntax', 'get_container_logs', atau 'detect_framework_and_strategy' jika memerlukan investigasi lebih lanjut.\n"
            "- JELASKAN ringkasan error secara gamblang.\n"
            "- LAKUKAN ROOT CAUSE ANALYSIS (RCA): Identifikasi kemungkinan penyebab akar masalah berdasarkan log "
            "(misal: merge conflict, uncommitted changes, dependensi npm/pip/composer gagal install, build compilation error, database migration failure, out of memory, dll).\n"
            "- BERIKAN SOLUSI & PERINTAH PERBAIKAN: Berikan panduan langkah demi langkah beserta perintah shell/git/docker yang tepat."
        ),
        tools=[
            detect_framework_and_strategy,
            check_status,
            deploy_app,
            get_compose_file,
            validate_compose_syntax,
            get_container_logs,
            cleanup_or_remove_app_resources
        ]
    )
    
    chat = client.chats.create(
        model="gemini-3.8-flash",
        config=config
    )
    
    print("=================================================")
    print(" 🤖 AI DEPLOYMENT AGENT (Gemini 3.8 Flash)")
    print("=================================================")
    print(f" App Terdaftar : {list(REGISTERED_APPS.keys())}")
    print(" Ketik 'exit' atau 'quit' untuk keluar.")
    print("=================================================\n")
    
    while True:
        try:
            user_msg = input("Admin ❯ ")
            if user_msg.lower() in ['exit', 'quit']:
                print("Sesi ditutup.")
                break
            if not user_msg.strip():
                continue
                
            response = chat.send_message(user_msg)
            print(f"Agent ❯ {response.text}\n")
            
        except KeyboardInterrupt:
            print("\nSesi ditutup.")
            break
        except Exception as e:
            print(f"\n[Error] {e}\n")

if __name__ == "__main__":
    main()