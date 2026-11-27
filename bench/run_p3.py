#!/usr/bin/env python3
"""Reprise / exécution Partie 3 : réutilise fixed1-opt et saute les CSV déjà présents."""
import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

VERSION = "fixed1-opt"


def run_cmd(cmd, env=None, check=True):
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, env=env)
    if check and res.returncode != 0:
        raise RuntimeError(f"Échec ({res.returncode}) : {' '.join(cmd)}")
    return res.returncode


def get_version_info():
    res = subprocess.run(
        [
            "gcloud", "app", "versions", "describe", VERSION,
            "--service", "default",
            "--format=value(servingStatus,versionUrl)",
        ],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return None, None
    parts = res.stdout.strip().split()
    return parts[0], (parts[1] if len(parts) > 1 else "")


def ensure_opt_started() -> str:
    status, url = get_version_info()
    if status == "SERVING":
        print(f"[Info] {VERSION} déjà active.")
        return url
    if status == "STOPPED":
        run_cmd(["gcloud", "app", "versions", "start", VERSION, "--quiet"])
        _, url = get_version_info()
        return url

    yaml_content = """runtime: python312
entrypoint: gunicorn -b :$PORT main:app

instance_class: B1
manual_scaling:
  instances: 1

handlers:
- url: /
  script: auto
env_variables:
  SEED_TOKEN: "change-me-seed-token"
"""
    fd, yaml_path = tempfile.mkstemp(prefix="app-fixed1-opt-", suffix=".yaml", dir=".")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(yaml_content)
        run_cmd(["gcloud", "config", "set", "app/cloud_build_timeout", "1200"], check=False)
        run_cmd(["gcloud", "app", "deploy", yaml_path, "--version", VERSION, "--no-promote", "--quiet"])
    finally:
        if os.path.exists(yaml_path):
            os.remove(yaml_path)
    _, url = get_version_info()
    return url


def safe_stop():
    print(f"\n[Sécurité Budget] Arrêt obligatoire de {VERSION}...", flush=True)
    for _ in range(12):
        status, _ = get_version_info()
        if status in (None, "STOPPED"):
            print(f"[OK] {VERSION} arrêtée ({status}).")
            return
        if subprocess.run(["gcloud", "app", "versions", "stop", VERSION, "--quiet"], check=False).returncode == 0:
            print(f"[OK] {VERSION} arrêtée.")
            return
        time.sleep(10)


def warmup(url: str):
    target = f"{url}/api/timeline?user=f05_u00001"
    for attempt in range(12):
        try:
            with urllib.request.urlopen(target, timeout=15) as resp:
                if resp.status == 200 and resp.headers.get("X-Instance"):
                    print(f"[OK] {VERSION} prête.")
                    return
        except Exception:
            time.sleep(3)
    raise RuntimeError(f"Impossible de joindre {target}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", default="30s")
    parser.add_argument("--raw-dir", default="raw")
    args = parser.parse_args()

    os.makedirs(args.raw_dir, exist_ok=True)
    missing = [
        f for f in range(5, 105, 5)
        if not os.path.exists(os.path.join(args.raw_dir, f"p3_f_f{f:02d}.csv"))
        or os.path.getsize(os.path.join(args.raw_dir, f"p3_f_f{f:02d}.csv")) < 100
    ]
    if not missing:
        print("[OK] Tous les fichiers p3_f_*.csv sont déjà présents.")
        safe_stop()
        return

    try:
        url = ensure_opt_started()
        warmup(url)
        for f_val in missing:
            prefix = f"f{f_val:02d}"
            log_path = os.path.join(args.raw_dir, f"p3_f_{prefix}.csv")
            env = os.environ.copy()
            env.update({
                "TINY_PREFIX": prefix,
                "TINY_USERS": "120",
                "TINY_LIMIT": "20",
                "TINY_LOG": log_path,
            })
            run_cmd([
                sys.executable, "-m", "locust",
                "-f", "bench/locustfile.py",
                "--headless", "-u", "1", "-r", "1",
                "-t", args.duration, "--only-summary", "--host", url,
            ], env=env)
            time.sleep(1)
    finally:
        safe_stop()


if __name__ == "__main__":
    main()
