"""EDA for metrics.csv — VRAM per 30s + frames decoded/inferred per camera."""
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

BASE = Path(__file__).parent
CSV = BASE / "metrics.csv"

df = pd.read_csv(CSV)

# --- basic EDA ---
print("=== SHAPE ===")
print(df.shape)
print("\n=== DTYPES ===")
print(df.dtypes)
print("\n=== HEAD ===")
print(df.head().to_string())
print("\n=== DESCRIBE (numeric) ===")
print(df.describe().to_string())
print("\n=== NULLS ===")
print(df.isna().sum().to_string())
print("\n=== camera_status counts ===")
print(df["camera_status"].value_counts().to_string())
print("\n=== n unique timestamps:", df["timestamp_utc"].nunique())
print("=== n cameras:", df["camera_name"].nunique())
ts_sorted = sorted(df["timestamp_utc"].unique())
print(f"first ts={ts_sorted[0]} last ts={ts_sorted[-1]} duration={(ts_sorted[-1]-ts_sorted[0]):.1f}s")

# human time for reference
df["dt"] = pd.to_datetime(df["timestamp_utc"], unit="s", utc=True)
t0 = df["timestamp_utc"].min()
df["elapsed_s"] = df["timestamp_utc"] - t0
df["bin_30s"] = (df["elapsed_s"] // 30).astype(int)
df["bin_start_s"] = df["bin_30s"] * 30
df["bin_label"] = df["bin_start_s"].astype(int).astype(str) + "-" + (df["bin_start_s"] + 30).astype(int).astype(str) + "s"

# --- 1. VRAM every 30s ---
# gpu mem is process-level (same for all cameras in a snapshot); dedupe per timestamp first
snap = df.groupby("timestamp_utc", as_index=False).agg(
    dt=("dt", "first"),
    elapsed_s=("elapsed_s", "first"),
    gpu_mem_used_mb=("gpu_mem_used_mb", "mean"),
    active_cameras=("active_cameras", "max"),
)
snap["bin_30s"] = (snap["elapsed_s"] // 30).astype(int)
vram30 = snap.groupby("bin_30s", as_index=False).agg(
    bin_start_s=("elapsed_s", lambda x: int(x.min() // 30 * 30)),
    n_snapshots=("timestamp_utc", "count"),
    vram_mean=("gpu_mem_used_mb", "mean"),
    vram_first=("gpu_mem_used_mb", "first"),
    vram_last=("gpu_mem_used_mb", "last"),
    vram_min=("gpu_mem_used_mb", "min"),
    vram_max=("gpu_mem_used_mb", "max"),
    active_max=("active_cameras", "max"),
)
vram30 = vram30.sort_values("bin_30s").reset_index(drop=True)
vram30["delta_vs_prev_mb"] = vram30["vram_mean"].diff()
vram30["delta_vs_start_mb"] = vram30["vram_mean"] - vram30["vram_mean"].iloc[0]
vram30["bin_label"] = vram30["bin_start_s"].astype(int).astype(str) + "-" + (vram30["bin_start_s"] + 30).astype(int).astype(str) + "s"

print("\n=== VRAM per 30s bin (MB) ===")
print(vram30.to_string(index=False, float_format="%.2f"))

vram30.to_csv(BASE / "vram_30s_summary.csv", index=False)
print("\nsaved vram_30s_summary.csv")

# plot VRAM 30s
fig, ax = plt.subplots(figsize=(10, 5))
x = vram30["bin_start_s"]
y = vram30["vram_mean"]
ax.plot(x, y, marker="o", label="mean VRAM / 30s bin")
ax.fill_between(x, vram30["vram_min"], vram30["vram_max"], alpha=0.2, label="min-max in bin")
for xi, yi, d in zip(x, y, vram30["delta_vs_prev_mb"]):
    lbl = "start" if pd.isna(d) else f"{d:+.2f} MB"
    ax.annotate(lbl, (xi, yi), textcoords="offset points", xytext=(0, 10), ha="center", fontsize=8)
ax.set_xlabel("Elapsed time (s, 30s bins from first sample)")
ax.set_ylabel("GPU VRAM used (MB)")
ax.set_title(f"VRAM growth per 30s (total Δ {vram30['delta_vs_start_mb'].iloc[-1]:+.2f} MB over {x.max()+30:.0f}s)")
ax.grid(True, alpha=0.3)
ax.legend()
fig.tight_layout()
fig.savefig(BASE / "vram_30s.png", dpi=150)
print("saved vram_30s.png")

# --- 2. Frames decoded (raw_fps) vs inferred (ai_infer_fps) per camera AT THE MOMENT (latest snapshot) ---
latest_ts = df["timestamp_utc"].max()
latest = df[df["timestamp_utc"] == latest_ts].copy()
latest = latest.sort_values("camera_name")
print(f"\n=== Latest snapshot ts={latest_ts} ({latest['dt'].iloc[0]}) rows={len(latest)} ===")
print(latest[["camera_name", "camera_status", "raw_fps", "ai_infer_fps"]].to_string(index=False))
latest.to_csv(BASE / "frames_latest_snapshot.csv", index=False)

cams = latest["camera_name"].tolist()
dec = latest["raw_fps"].tolist()
inf = latest["ai_infer_fps"].tolist()

fig2, ax2 = plt.subplots(figsize=(16, 6))
idx = range(len(cams))
w = 0.4
b1 = ax2.bar([i - w / 2 for i in idx], dec, width=w, label="decoded (raw_fps)")
b2 = ax2.bar([i + w / 2 for i in idx], inf, width=w, label="inferred (ai_infer_fps)")
ax2.set_xticks(list(idx))
ax2.set_xticklabels(cams, rotation=45, ha="right", fontsize=8)
ax2.set_xlabel("Camera")
ax2.set_ylabel("Frames per second")
ax2.set_title(f"Decoded vs Inferred FPS per camera — latest snapshot ({latest['dt'].iloc[0]:%Y-%m-%d %H:%M:%S UTC})")
ax2.grid(True, axis="y", alpha=0.3)
ax2.legend()
# annotate non-zero inferred values
for i, v in enumerate(inf):
    if v > 0:
        ax2.text(i + w / 2, v + 0.05, f"{v:g}", ha="center", fontsize=7)
fig2.tight_layout()
fig2.savefig(BASE / "frames_per_camera_latest.png", dpi=150)
print("saved frames_per_camera_latest.png")

print(f"\nDecoded total @latest: {sum(dec):.1f} fps across {len(cams)} cams | Inferred total @latest: {sum(inf):.1f} fps")
print("ONLINE @latest:", (latest["camera_status"] == "online").sum(), "OFFLINE:", (latest["camera_status"] == "offline").sum())
