#!/usr/bin/env python3
"""Automatisation Partie 2 : N in {1, 2, 4}, C in {1, 2, 4, 8, 16, 32, 64}."""
import argparse
import os
import subprocess
import sys
import time
import urllib.request

CONCURRENCIES = [1, 2, 4, 8, 16, 32, 64]


def run_cmd(cmd, env=None, check=True):
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, env=env)
    if check and res.returncode != 0:
        raise RuntimeError(f"Échec ({res.returncode}) : {' '.join(cmd)}")
    return res.returncode


def get_version_info(version: str):
    """Retourne (status, url) si la version existe, sinon (None, None)."""
    res = subprocess.run(
        [
            "gcloud", "app", "versions", "describe", version,
            "--service", "default",
            "--format=value(servingStatus,versionUrl)",
        ],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return None, None
    parts = res.stdout.strip().split()
    status = parts[0]
    url = parts[1] if len(parts) > 1 else ""
    return status, url


def ensure_started(n: int) -> str:
    version = f"fixed{n}"
    status, url = get_version_info(version)
    if status == "SERVING":
        print(f"[Info] {version} est déjà active (SERVING).")
        return url
    if status == "STOPPED":
        run_cmd(["gcloud", "app", "versions", "start", version, "--quiet"])
        _, url = get_version_info(version)
        return url
    # Sinon, premier déploiement de la version
    run_cmd(["gcloud", "config", "set", "app/cloud_build_timeout", "1200"], check=False)
    run_cmd(["bash", "./deploy_fixed.sh", str(n)])
    _, url = get_version_info(version)
    return url


def safe_stop(version: str):
    """Arrête la version en réessayant si une opération GCP est encore en cours."""
    print(f"\n[Sécurité Budget] Arrêt obligatoire de {version}...", flush=True)
    for attempt in range(12):
        status, _ = get_version_info(version)
        if status in (None, "STOPPED"):
            print(f"[OK] {version} est bien arrêtée ({status}).")
            return
        rc = subprocess.run(
            ["gcloud", "app", "versions", "stop", version, "--quiet"],
            check=False,
        ).returncode
        if rc == 0:
            print(f"[OK] {version} arrêtée avec succès.")
            return
        print(f"[Attente] Opération en cours sur {version}, nouvel essai dans 10s...")
        time.sleep(10)


def warmup_and_check(url: str):
    target = f"{url}/api/timeline?user=base_u00001"
    for attempt in range(12):
        try:
            with urllib.request.urlopen(target, timeout=15) as resp:
                inst = resp.headers.get("X-Instance")
                timing = resp.headers.get("Server-Timing")
                if resp.status == 200 and inst:
                    print(f"[OK] Prête : X-Instance={inst}, Server-Timing={timing}")
                    return
        except Exception as e:
            print(f"[Attente instance] {attempt + 1}/12 ({e})")
            time.sleep(3)
    raise RuntimeError(f"Impossible de joindre {target}")


def run_for_n(n: int, duration: str, raw_dir: str):
    version = f"fixed{n}"
    try:
        url = ensure_started(n)
        warmup_and_check(url)
        for c in CONCURRENCIES:
            log_path = os.path.join(raw_dir, f"p2_n{n}_c{c:02d}.csv")
            env = os.environ.copy()
            env.update({
                "TINY_PREFIX": "base",
                "TINY_USERS": "1000",
                "TINY_LIMIT": "20",
                "TINY_LOG": log_path,
            })
            cmd = [
                sys.executable, "-m", "locust",
                "-f", "bench/locustfile.py",
                "--headless",
                "-u", str(c),
                "-r", str(c),
                "-t", duration,
                "--only-summary",
                "--host", url,
            ]
            run_cmd(cmd, env=env)
            time.sleep(2)
    finally:
        safe_stop(version)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", nargs="+", type=int, default=[1, 2, 4])
    parser.add_argument("--duration", default="30s")
    parser.add_argument("--raw-dir", default="raw")
    args = parser.parse_args()

    os.makedirs(args.raw_dir, exist_ok=True)
    for n in args.instances:
        run_for_n(n, args.duration, args.raw_dir)
    print("\n[Terminé] Partie 2 complète et toutes les versions fixedN arrêtées.")


if __name__ == "__main__":
    main()
