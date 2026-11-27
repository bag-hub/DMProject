#!/usr/bin/env python3
import os, subprocess, sys, time, urllib.request

CONCURRENCIES = [1, 2, 4, 8, 16, 32, 64]

def run_cmd(cmd, env=None, check=True):
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, env=env)
    if check and res.returncode != 0:
        raise RuntimeError(f"Échec : {' '.join(cmd)}")

def get_info(version):
    res = subprocess.run(
        ["gcloud", "app", "versions", "describe", version, "--service", "default", "--format=value(servingStatus,versionUrl)"],
        capture_output=True, text=True
    )
    if res.returncode != 0 or not res.stdout.strip():
        return None, None
    p = res.stdout.strip().split()
    return p[0], (p[1] if len(p) > 1 else "")

def ensure_started(n):
    v = f"fixed{n}"
    st, url = get_info(v)
    if st == "SERVING":
        return url
    if st == "STOPPED":
        run_cmd(["gcloud", "app", "versions", "start", v, "--quiet"])
        return get_info(v)[1]
    run_cmd(["gcloud", "config", "set", "app/cloud_build_timeout", "1200"], check=False)
    run_cmd(["bash", "./deploy_fixed.sh", str(n)])
    return get_info(v)[1]

def safe_stop(n):
    v = f"fixed{n}"
    for _ in range(12):
        st, _ = get_info(v)
        if st in (None, "STOPPED"):
            return
        if subprocess.run(["gcloud", "app", "versions", "stop", v, "--quiet"], check=False).returncode == 0:
            return
        time.sleep(10)

def warmup(url):
    for _ in range(12):
        try:
            with urllib.request.urlopen(f"{url}/api/timeline?user=base_u00001", timeout=15) as r:
                if r.status == 200 and r.headers.get("X-Instance"):
                    return
        except Exception:
            time.sleep(3)

for n in [1, 2, 4]:
    missing = [c for c in CONCURRENCIES if not os.path.exists(f"raw/p2_n{n}_c{c:02d}.csv") or os.path.getsize(f"raw/p2_n{n}_c{c:02d}.csv") < 100]
    if not missing:
        safe_stop(n)
        continue
    try:
        url = ensure_started(n)
        warmup(url)
        for c in missing:
            env = os.environ.copy()
            env.update({"TINY_PREFIX": "base", "TINY_USERS": "1000", "TINY_LIMIT": "20", "TINY_LOG": f"raw/p2_n{n}_c{c:02d}.csv"})
            run_cmd([sys.executable, "-m", "locust", "-f", "bench/locustfile.py", "--headless", "-u", str(c), "-r", str(c), "-t", "20s", "--only-summary", "--host", url], env=env, check=False)
            time.sleep(1)
    finally:
        safe_stop(n)
