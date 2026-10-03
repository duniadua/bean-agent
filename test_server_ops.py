import os
import sys
import subprocess
import json
import pytest
from unittest.mock import patch, MagicMock

# Import modul target bean_agent
import bean_agent
sys.modules["server_ops"] = bean_agent
server_ops = bean_agent


@pytest.fixture(autouse=True)
def setup_registered_apps(tmp_path):
    """Set up mockup registered apps and environment."""
    app_dir = tmp_path / "test_app"
    app_dir.mkdir()
    server_ops.REGISTERED_APPS = {"test_app": str(app_dir)}
    yield app_dir


# ==========================================
# 1. UNIT TESTS
# ==========================================

class TestRunCmd:
    def test_run_cmd_success(self, tmp_path):
        res = server_ops.run_cmd(["echo", "hello"], cwd=str(tmp_path))
        assert res == "hello"

    def test_run_cmd_failure(self, tmp_path):
        res = server_ops.run_cmd(["ls", "non_existing_file_12345"], cwd=str(tmp_path))
        assert res.startswith("ERROR")

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["test"], timeout=1))
    def test_run_cmd_timeout(self, mock_run, tmp_path):
        res = server_ops.run_cmd(["test"], cwd=str(tmp_path), timeout=1)
        assert "melebihi batas waktu" in res


class TestCheckStatus:
    def test_check_status_unregistered_app(self):
        res = server_ops.check_status("unknown_app")
        assert "tidak terdaftar" in res

    def test_check_status_directory_not_found(self):
        server_ops.REGISTERED_APPS["missing_dir_app"] = "/path/yang/pasti/tidak/ada_12345"
        res = server_ops.check_status("missing_dir_app")
        assert "tidak ditemukan di server" in res

    @patch("server_ops.run_cmd")
    def test_check_status_success(self, mock_run_cmd, setup_registered_apps):
        app_dir = setup_registered_apps
        (app_dir / "docker-compose.yml").write_text("services:\n  web:\n    image: nginx\n")
        mock_run_cmd.side_effect = ["", "On branch main\nnothing to commit", "NAME   STATUS\nweb    running"]
        res = server_ops.check_status("test_app")
        assert "STATUS GIT" in res
        assert "STATUS CONTAINER DOCKER" in res
        assert "running" in res


class TestDeployApp:
    def test_deploy_unregistered(self):
        res = server_ops.deploy_app("unknown_app")
        assert "tidak terdaftar" in res

    @patch("builtins.input", return_value="n")
    @patch("server_ops.run_cmd")
    def test_deploy_cancelled_by_user(self, mock_run_cmd, mock_input):
        mock_run_cmd.return_value = "Everything up to date"
        res = server_ops.deploy_app("test_app")
        assert "User membatalkan" in res

    @patch("builtins.input", return_value="y")
    @patch("server_ops.run_cmd")
    def test_deploy_git_pull_failed_triggers_rca(self, mock_run_cmd, mock_input):
        # 1. git fetch, 2. git status awal, 3. git pull (fails), 4. git status (diagnostik)
        mock_run_cmd.side_effect = [
            "",
            "Behind by 1 commit",
            "ERROR (1): error: Your local changes to the following files would be overwritten by merge",
            "Untracked files: dirty.txt"
        ]
        res = server_ops.deploy_app("test_app")
        assert "Deployment GAGAL pada tahap 'git pull'" in res
        assert "ERROR LOG GIT PULL" in res
        assert "DIAGNOSTIK REPOSITORY" in res
        assert "Tugas Agent: Analisis" in res

    @patch("builtins.input", return_value="y")
    @patch("server_ops.run_cmd")
    def test_deploy_docker_compose_failed(self, mock_run_cmd, mock_input, setup_registered_apps):
        app_dir = setup_registered_apps
        (app_dir / "docker-compose.yml").write_text("services:\n  web:\n    image: nginx\n")
        # 1. git fetch, 2. git status awal, 3. git pull (ok), 4. docker compose (fails)
        mock_run_cmd.side_effect = [
            "",
            "Behind by 1 commit",
            "Fast-forward 2 files changed",
            "ERROR (1): bind: address already in use"
        ]
        res = server_ops.deploy_app("test_app")
        assert "Deployment GAGAL pada perintah 'docker compose up -d --build'" in res
        assert "address already in use" in res

    @patch("builtins.input", return_value="y")
    @patch("server_ops.run_cmd")
    def test_deploy_success(self, mock_run_cmd, mock_input):
        mock_run_cmd.side_effect = [
            "",
            "Behind by 1 commit",
            "Fast-forward 2 files changed",
            "Container test_app Started"
        ]
        res = server_ops.deploy_app("test_app")
        assert "Deploy berhasil!" in res


class TestComposeInspectionTools:
    def test_get_compose_file_success(self, setup_registered_apps):
        app_dir = setup_registered_apps
        compose_path = app_dir / "docker-compose.yml"
        compose_path.write_text("services:\n  web:\n    image: nginx:latest\n")

        content = server_ops.get_compose_file("test_app")
        assert "ISI FILE: docker-compose.yml" in content
        assert "image: nginx:latest" in content

    def test_get_compose_file_not_found(self, setup_registered_apps):
        content = server_ops.get_compose_file("test_app")
        assert "File docker-compose.yml tidak ditemukan" in content

    @patch("server_ops.run_cmd")
    def test_validate_compose_syntax_valid(self, mock_run_cmd):
        mock_run_cmd.return_value = ""
        res = server_ops.validate_compose_syntax("test_app")
        assert "VALID" in res

    @patch("server_ops.run_cmd")
    def test_validate_compose_syntax_invalid(self, mock_run_cmd):
        mock_run_cmd.side_effect = [
            "ERROR (1): yaml syntax error",
            "ERROR (1): yaml syntax error at line 5"
        ]
        res = server_ops.validate_compose_syntax("test_app")
        assert "SINTAKS INVALID / ERROR:" in res
        assert "line 5" in res

    @patch("server_ops.run_cmd")
    def test_get_container_logs(self, mock_run_cmd):
        mock_run_cmd.return_value = "[2026-10-03 09:00:00] Server started on port 8080"
        res = server_ops.get_container_logs("test_app", service_name="web", tail=10)
        assert "LOG DOCKER" in res
        assert "service 'web'" in res
        assert "Server started on port 8080" in res


# ==========================================
# 2. FRAMEWORK DETECTION & NATIVE DEPLOYMENT TESTS
# ==========================================

class TestFrameworkDetection:
    def test_detect_docker_compose(self, setup_registered_apps):
        app_dir = setup_registered_apps
        (app_dir / "docker-compose.yml").write_text("services:\n  app:\n    image: node:alpine\n")
        info = server_ops.detect_project_type(str(app_dir))
        assert info["mode"] == "docker"
        assert info["framework"] == "Docker Compose"

    def test_detect_nextjs(self, setup_registered_apps):
        app_dir = setup_registered_apps
        pkg_json = {
            "dependencies": {"next": "^14.0.0", "react": "^18.0.0"},
            "scripts": {"build": "next build"}
        }
        (app_dir / "package.json").write_text(json.dumps(pkg_json))
        info = server_ops.detect_project_type(str(app_dir))
        assert info["mode"] == "native"
        assert "Next.js" in info["framework"]
        assert ["npm", "install"] in info["deploy_steps"]
        assert ["npm", "run", "build"] in info["deploy_steps"]

    def test_detect_python_django(self, setup_registered_apps):
        app_dir = setup_registered_apps
        (app_dir / "requirements.txt").write_text("Django>=4.2\n")
        (app_dir / "manage.py").write_text("# Django manage.py\n")
        info = server_ops.detect_project_type(str(app_dir))
        assert info["mode"] == "native"
        assert "Django" in info["framework"]
        assert any("migrate" in step for step in info["deploy_steps"])

    def test_detect_laravel(self, setup_registered_apps):
        app_dir = setup_registered_apps
        (app_dir / "composer.json").write_text('{"require": {"php": "^8.2"}}')
        (app_dir / "artisan").write_text("#!/usr/bin/env php\n")
        info = server_ops.detect_project_type(str(app_dir))
        assert info["mode"] == "native"
        assert "Laravel" in info["framework"]
        assert any("artisan" in step for step in info["deploy_steps"])

    def test_detect_framework_tool(self):
        res = server_ops.detect_framework_and_strategy("test_app")
        assert "ANALISIS FRAMEWORK & STRATEGI DEPLOYMENT" in res
        assert "test_app" in res

    @patch("builtins.input", return_value="y")
    @patch("server_ops.run_cmd")
    def test_deploy_native_pipeline_success(self, mock_run_cmd, mock_input, setup_registered_apps):
        app_dir = setup_registered_apps
        pkg_json = {"dependencies": {"express": "^4.18.0"}, "scripts": {"build": "tsc"}}
        (app_dir / "package.json").write_text(json.dumps(pkg_json))

        # 1. fetch, 2. status awal, 3. pull, 4. npm install, 5. npm run build
        mock_run_cmd.side_effect = [
            "",
            "Behind by 1 commit",
            "Fast-forward 1 file changed",
            "added 50 packages in 2s",
            "Build completed successfully"
        ]
        res = server_ops.deploy_app("test_app")
        assert "Deploy berhasil!" in res
        assert "Node.js Backend" in res
        assert "Build completed successfully" in res


# ==========================================
# 3. GUARDRAIL HITL & DESTRUCTIVE ACTION TESTS
# ==========================================

class TestHitlGuardrails:
    def test_cleanup_unregistered(self):
        res = server_ops.cleanup_or_remove_app_resources("unknown_app", "stop_containers")
        assert "tidak terdaftar" in res

    def test_cleanup_invalid_action(self, setup_registered_apps):
        res = server_ops.cleanup_or_remove_app_resources("test_app", "format_harddisk")
        assert "tidak dikenal" in res

    @patch("builtins.input", return_value="NO")
    def test_cleanup_rejected_without_explicit_delete_token(self, mock_input, setup_registered_apps):
        res = server_ops.cleanup_or_remove_app_resources("test_app", "remove_with_volumes")
        assert "DIBATALKAN" in res
        assert "Human-in-the-Loop menolak" in res

    @patch("builtins.input", return_value="DELETE")
    @patch("server_ops.run_cmd")
    def test_cleanup_confirmed_with_explicit_delete_token(self, mock_run_cmd, mock_input, setup_registered_apps):
        mock_run_cmd.return_value = "Network removed. Volume removed."
        res = server_ops.cleanup_or_remove_app_resources("test_app", "remove_with_volumes")
        assert "berhasil dieksekusi oleh izin administrator" in res
        assert "Volume removed" in res


# ==========================================
# 4. SMOKE TESTS
# ==========================================

class TestSmokeSystem:
    def test_tools_registered_with_docstrings(self):
        """Smoke test: Memastikan semua tool memiliki nama, type hint, dan docstring lengkap."""
        tools = [
            server_ops.detect_framework_and_strategy,
            server_ops.check_status,
            server_ops.deploy_app,
            server_ops.get_compose_file,
            server_ops.validate_compose_syntax,
            server_ops.get_container_logs,
            server_ops.cleanup_or_remove_app_resources
        ]
        for t in tools:
            assert callable(t), f"{t} harus berupa callable function"
            assert t.__doc__ is not None and len(t.__doc__.strip()) > 10, f"{t.__name__} harus memiliki docstring jelas"

    @patch("google.genai.Client")
    def test_gemini_config_and_tool_wiring(self, mock_client_cls):
        """Smoke test: Memastikan types.GenerateContentConfig menerima seluruh 7 tool tanpa exception."""
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction="Smoke test system instruction",
            tools=[
                server_ops.detect_framework_and_strategy,
                server_ops.check_status,
                server_ops.deploy_app,
                server_ops.get_compose_file,
                server_ops.validate_compose_syntax,
                server_ops.get_container_logs,
                server_ops.cleanup_or_remove_app_resources
            ]
        )
        assert len(config.tools) == 7
