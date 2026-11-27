#!/usr/bin/env python3
"""
Génère en une seule commande tous les fichiers CSV agrégés (figures/fig*.csv)
et toutes les figures PNG (figures/fig*.png) à partir des journaux bruts dans raw/.
"""
import csv
import glob
import os
import statistics
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW_DIR = "raw"
FIG_DIR = "figures"
os.makedirs(FIG_DIR, exist_ok=True)


def summarize_csv(path: str, trim_warmup_s: float = 2.0):
    """Calcule les métriques d'un fichier log Locust brut."""
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                t_start = float(r["T_START"])
                lat = float(r["LATENCY_MS"])
                status = int(r["STATUS"])
                inst = (r.get("INSTANCE") or "").strip()
                srv = float(r["SERVER_MS"]) if r.get("SERVER_MS") else None
                rows.append((t_start, lat, status, inst, srv))
            except (ValueError, KeyError):
                continue

    if not rows:
        return None

    t0 = min(r[0] for r in rows)
    t_max = max(r[0] + r[1] / 1000.0 for r in rows)
    total_span = t_max - t0

    # Ignorer les 2 premières secondes si le run dure au moins 15s (régime établi)
    if total_span >= 15.0:
        steady = [r for r in rows if r[0] >= t0 + trim_warmup_s]
        if steady:
            rows = steady
            t0 = min(r[0] for r in rows)
            t_max = max(r[0] + r[1] / 1000.0 for r in rows)

    duration_s = max(t_max - t0, 0.001)
    ok_rows = [r for r in rows if r[2] == 200]
    err_count = len(rows) - len(ok_rows)

    latencies = [r[1] for r in ok_rows]
    server_times = [r[4] for r in ok_rows if r[4] is not None]
    instances = sorted({r[3] for r in ok_rows if r[3]})

    med_lat = statistics.median(latencies) if latencies else 0.0
    med_srv = statistics.median(server_times) if server_times else 0.0
    med_net = max(0.0, med_lat - med_srv)
    throughput = len(ok_rows) / duration_s

    return {
        "n_total": len(rows),
        "n_ok": len(ok_rows),
        "n_err": err_count,
        "duration_s": round(duration_s, 3),
        "throughput_rps": round(throughput, 3),
        "client_med_ms": round(med_lat, 2),
        "server_med_ms": round(med_srv, 2),
        "network_med_ms": round(med_net, 2),
        "active_instances": len(instances),
        "instance_ids": ";".join(instances),
    }


def write_csv(filename: str, fieldnames: list, data: list):
    out_path = os.path.join(FIG_DIR, filename)
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)
    print(f"[CSV] {out_path}")


def build_part1():
    # Fig 1a : temps serveur médian en fonction de U et de P
    u_vals = [100, 1000, 10000]
    p_vals = [10, 100, 1000]
    records_1a = []

    u_srv, u_cli = [], []
    for u in u_vals:
        s = summarize_csv(os.path.join(RAW_DIR, f"p1_u_{u}.csv"))
        if s:
            u_srv.append(s["server_med_ms"])
            u_cli.append(s["client_med_ms"])
            records_1a.append({"facteur": "U", "valeur": u, "U": u, "P": 20, "F": 20, **s})

    p_srv, p_cli = [], []
    for p in p_vals:
        s = summarize_csv(os.path.join(RAW_DIR, f"p1_p_{p}.csv"))
        if s:
            p_srv.append(s["server_med_ms"])
            p_cli.append(s["client_med_ms"])
            records_1a.append({"facteur": "P", "valeur": p, "U": 100, "P": p, "F": 20, **s})

    if records_1a:
        fields = ["facteur", "valeur", "U", "P", "F", "n_total", "n_ok", "n_err",
                  "server_med_ms", "client_med_ms", "network_med_ms", "throughput_rps",
                  "active_instances", "instance_ids"]
        write_csv("fig1a.csv", fields, records_1a)

        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
        axes[0].plot(u_vals, u_srv, "o-", linewidth=2, label="Temps serveur médian (ms)")
        axes[0].plot(u_vals, u_cli, "s--", alpha=0.75, label="Latence client médiane (ms)")
        axes[0].set_xscale("log")
        axes[0].set_xticks(u_vals)
        axes[0].set_xticklabels([str(x) for x in u_vals])
        axes[0].set_xlabel("Utilisateurs U (P=20, F=20, N=1, C=1)")
        axes[0].set_ylabel("Temps médian (ms)")
        axes[0].set_title("Impact du nombre d'utilisateurs (U)")
        axes[0].grid(True, linestyle=":")
        axes[0].legend()

        axes[1].plot(p_vals, p_srv, "o-", linewidth=2, label="Temps serveur médian (ms)")
        axes[1].plot(p_vals, p_cli, "s--", alpha=0.75, label="Latence client médiane (ms)")
        axes[1].set_xscale("log")
        axes[1].set_xticks(p_vals)
        axes[1].set_xticklabels([str(x) for x in p_vals])
        axes[1].set_xlabel("Posts par utilisateur P (U=100, F=20, N=1, C=1)")
        axes[1].set_title("Impact du nombre de posts (P)")
        axes[1].grid(True, linestyle=":")
        axes[1].legend()

        plt.tight_layout()
        plt.savefig(os.path.join(FIG_DIR, "fig1a.png"), dpi=160)
        plt.close()
        print("[PNG] figures/fig1a.png")

    # Fig 1b : temps serveur médian et latence client médiane en fonction de F
    f_vals = list(range(5, 105, 5))
    records_1b = []
    for f in f_vals:
        s = summarize_csv(os.path.join(RAW_DIR, f"p1_f_f{f:02d}.csv"))
        if s:
            records_1b.append({"F": f, "U": 120, "P": 20, **s})

    if records_1b:
        fields = ["F", "U", "P", "n_total", "n_ok", "n_err",
                  "server_med_ms", "client_med_ms", "network_med_ms", "throughput_rps",
                  "active_instances", "instance_ids"]
        write_csv("fig1b.csv", fields, records_1b)

        xs = [r["F"] for r in records_1b]
        srv = [r["server_med_ms"] for r in records_1b]
        cli = [r["client_med_ms"] for r in records_1b]

        plt.figure(figsize=(8.5, 4.8))
        plt.plot(xs, cli, "s-", linewidth=2, label="Latence client médiane (ms)")
        plt.plot(xs, srv, "o-", linewidth=2, label="Temps serveur médian (ms)")
        plt.axvline(30, color="red", linestyle="--", alpha=0.7, label="Seuil F=30 (limite filtre IN Datastore)")
        plt.xlabel("Nombre de comptes suivis F (U=120, P=20, N=1, C=1)")
        plt.ylabel("Temps médian (ms)")
        plt.title("Coût d'une timeline en fonction de F")
        plt.grid(True, linestyle=":")
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(FIG_DIR, "fig1b.png"), dpi=160)
        plt.close()
        print("[PNG] figures/fig1b.png")


def build_part2():
    ns = [1, 2, 4]
    cs = [1, 2, 4, 8, 16, 32, 64]
    records_2 = []

    for n in ns:
        for c in cs:
            path = os.path.join(RAW_DIR, f"p2_n{n}_c{c:02d}.csv")
            if not os.path.exists(path):
                continue
            s = summarize_csv(path)
            if s:
                little_ms = round((1000.0 * c / s["throughput_rps"]), 2) if s["throughput_rps"] > 0 else 0.0
                records_2.append({
                    "N_instances_cible": n,
                    "C_concurrence": c,
                    "U": 1000,
                    "P": 20,
                    "F": 20,
                    "little_pred_ms": little_ms,
                    **s,
                })

    if not records_2:
        print("[Info] Aucun fichier p2_n*_c*.csv trouvé pour le moment.")
        return

    fields = ["N_instances_cible", "C_concurrence", "U", "P", "F", "n_total", "n_ok", "n_err",
              "throughput_rps", "client_med_ms", "server_med_ms", "little_pred_ms",
              "active_instances", "instance_ids"]
    write_csv("fig2a.csv", fields, records_2)
    write_csv("fig2b.csv", fields, records_2)

    # Fig 2a : Débit en fonction de C par valeur de N
    plt.figure(figsize=(8.5, 4.8))
    for n in ns:
        sub = [r for r in records_2 if r["N_instances_cible"] == n]
        if sub:
            plt.plot([r["C_concurrence"] for r in sub], [r["throughput_rps"] for r in sub],
                     "o-", linewidth=2, label=f"N = {n} instance(s)")
    plt.xlabel("Concurrence C (utilisateurs Locust simultanés, jeu base)")
    plt.ylabel("Débit (requêtes / seconde)")
    plt.title("Capacité : Débit en fonction de la concurrence C et de N")
    plt.grid(True, linestyle=":")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "fig2a.png"), dpi=160)
    plt.close()
    print("[PNG] figures/fig2a.png")

    # Fig 2b : Latence médiane vs C + prédiction loi de Little
    plt.figure(figsize=(8.5, 4.8))
    for n in ns:
        sub = [r for r in records_2 if r["N_instances_cible"] == n]
        if sub:
            cx = [r["C_concurrence"] for r in sub]
            plt.plot(cx, [r["client_med_ms"] for r in sub], "o-", linewidth=2, label=f"Mesurée N={n} (ms)")
            plt.plot(cx, [r["little_pred_ms"] for r in sub], "--", alpha=0.75, label=f"Loi de Little C/Débit N={n}")
    plt.xlabel("Concurrence C (utilisateurs Locust simultanés, jeu base)")
    plt.ylabel("Latence client médiane (ms)")
    plt.title("Latence médiane vs Concurrence C et Loi de Little")
    plt.grid(True, linestyle=":")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "fig2b.png"), dpi=160)
    plt.close()
    print("[PNG] figures/fig2b.png")


def build_part3():
    # Compare avant (p1_f_f*.csv) et après (p3_f_f*.csv) sur le facteur F
    f_vals = list(range(5, 105, 5))
    records_3 = []
    for f in f_vals:
        before = summarize_csv(os.path.join(RAW_DIR, f"p1_f_f{f:02d}.csv"))
        p3_path = os.path.join(RAW_DIR, f"p3_f_f{f:02d}.csv")
        after = summarize_csv(p3_path) if os.path.exists(p3_path) else None
        if before and after:
            records_3.append({
                "F": f,
                "avant_server_med_ms": before["server_med_ms"],
                "apres_server_med_ms": after["server_med_ms"],
                "avant_client_med_ms": before["client_med_ms"],
                "apres_client_med_ms": after["client_med_ms"],
                "gain_serveur_pct": round(
                    100.0 * (before["server_med_ms"] - after["server_med_ms"]) / max(before["server_med_ms"], 0.1), 1
                ),
            })

    if not records_3:
        print("[Info] Aucun fichier p3_f_f*.csv trouvé pour le moment.")
        return

    fields = ["F", "avant_server_med_ms", "apres_server_med_ms",
              "avant_client_med_ms", "apres_client_med_ms", "gain_serveur_pct"]
    write_csv("fig3.csv", fields, records_3)

    xs = [r["F"] for r in records_3]
    plt.figure(figsize=(8.5, 4.8))
    plt.plot(xs, [r["avant_server_med_ms"] for r in records_3], "o-", linewidth=2, label="Avant (requêtes séquentielles F>=30)")
    plt.plot(xs, [r["apres_server_med_ms"] for r in records_3], "s-", linewidth=2, label="Après (requêtes IN par lots de 30)")
    plt.axvline(30, color="gray", linestyle="--", alpha=0.7)
    plt.xlabel("Nombre de comptes suivis F (U=120, P=20, N=1, C=1)")
    plt.ylabel("Temps serveur médian (ms)")
    plt.title("Partie 3 : Temps serveur avant vs après optimisation du filtre IN")
    plt.grid(True, linestyle=":")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "fig3.png"), dpi=160)
    plt.close()
    print("[PNG] figures/fig3.png")


if __name__ == "__main__":
    build_part1()
    build_part2()
    build_part3()
