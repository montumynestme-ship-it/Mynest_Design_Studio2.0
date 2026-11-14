"""Guarded one-room A/B(C) structural-conditioning benchmark runner (NOT production).

Compares, on ONE room with an identical base render / prompt / seed / dimensions:
  Arm A  baseline image-edit          FAL_USE_CONTROLNET=false            -> flux-kontext/dev
  Arm B  canny, BASE as control       USE_CONTROLNET=true STRUCT=false    -> flux-control-lora-canny
  Arm C  canny, STRUCTURAL as control USE_CONTROLNET=true STRUCT=true     -> flux-control-lora-canny

Arm C needs a perspective-structural PNG, captured offline via the dev "Paired Capture" tool
(DevPairedCapture); none exists on disk. See STRUCTURAL_CONDITIONING_BENCHMARK_PLAN.md.

SAFETY: this makes PAID fal calls, so it is HARD-GUARDED and bills nothing unless authorized:
  * Aborts (exit 0, no call) unless BOTH RUN_FAL_BENCHMARK=1 AND FAL_SINGLE_ATTEMPT=true.
  * Hard MAX_CALLS cap (default 3).
  * Refuses Arm C unless a structural fixture is present.
  * Never logs the API key, Authorization header, or base64 image payloads.
It reuses the REAL FalFluxAdapter (per-arm env via importlib.reload): no new conditioning
strategy, no provider/model/flag-default change. With no authorization env it prints the plan.

Usage (ONLY after owner authorization; see the plan's section 8):
    cd backend
    RUN_FAL_BENCHMARK=1 FAL_SINGLE_ATTEMPT=true \
      BENCH_FIXTURES=/path/to/fixtures BENCH_ARMS=A,B,C \
      PYTHONPATH="$(pwd)" ./.venv/Scripts/python.exe benchmarks/structural_ab_benchmark.py

Fixtures dir must contain:  base.png  prompt.txt   (and structural.png for Arm C)
Optional:  config.json  = {"seed": <int>, "room_label": "...", "design_version_id": "..."}
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import time
from pathlib import Path

MAX_CALLS = int(os.getenv("BENCH_MAX_CALLS", "3"))

_ARM_ENV = {
    "A": {"FAL_USE_CONTROLNET": "false", "FAL_CONTROL_STRUCTURAL": "false"},
    "B": {"FAL_USE_CONTROLNET": "true", "FAL_CONTROL_STRUCTURAL": "false"},
    "C": {"FAL_USE_CONTROLNET": "true", "FAL_CONTROL_STRUCTURAL": "true"},
}


def _sha16(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def _authorized() -> bool:
    run = os.getenv("RUN_FAL_BENCHMARK") == "1"
    single = os.getenv("FAL_SINGLE_ATTEMPT", "").lower() == "true"
    return run and single


def _load_fixtures(d: Path) -> dict:
    base = d / "base.png"
    prompt = d / "prompt.txt"
    if not base.is_file():
        sys.exit(f"ABORT: missing base render fixture: {base}")
    if not prompt.is_file():
        sys.exit(f"ABORT: missing prompt.txt fixture: {prompt}")
    cfg: dict = {}
    if (d / "config.json").is_file():
        cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    structural = d / "structural.png"
    return {
        "base_bytes": base.read_bytes(),
        "structural_bytes": structural.read_bytes() if structural.is_file() else None,
        "prompt": prompt.read_text(encoding="utf-8"),
        "seed": int(cfg.get("seed", 1234567)),
        "room_label": cfg.get("room_label", "Bedroom 1"),
        "design_version_id": cfg.get("design_version_id"),
    }


def _run_arm(arm: str, fx: dict, out_dir: Path) -> dict:
    """Reload config+adapter under this arm's flags, submit ONE render, record provenance."""
    for k, v in _ARM_ENV[arm].items():
        os.environ[k] = v
    os.environ["FAL_SINGLE_ATTEMPT"] = "true"  # enforce single submission regardless of arm

    from app.core import config as _config
    importlib.reload(_config)
    from app.services.ai import fal_flux_adapter as _fa
    importlib.reload(_fa)
    from app.services.ai.base import GenerationRequest

    structural = fx["structural_bytes"] if arm == "C" else None
    req = GenerationRequest(
        prompt=fx["prompt"], style=None, count=1, width=1216, height=832,
        seed=fx["seed"], room_label=fx["room_label"],
        control_image=fx["base_bytes"], structural_image=structural,
    )
    adapter = _fa.FalFluxAdapter()
    t0 = time.time()
    out = adapter.generate(req)  # <-- the single PAID call
    png = out[0]
    out_path = out_dir / f"bench_{arm}.png"
    out_path.write_bytes(png)
    strength = None
    if _fa.FAL_USE_CONTROLNET:
        strength = _fa.FAL_CONTROL_STRENGTH if _fa.FAL_CONTROL_STRENGTH is not None else 1.0
    return {
        "arm": arm,
        "model": _fa.FAL_CONTROL_MODEL if _fa.FAL_USE_CONTROLNET else _fa.FAL_IMAGE_MODEL,
        "conditioning_mode": getattr(adapter, "last_conditioning_mode", None),
        "control_source": getattr(adapter, "last_control_source", None),
        "control_strength": strength,
        "base_sha256": hashlib.sha256(fx["base_bytes"]).hexdigest(),
        "structural_sha256": hashlib.sha256(structural).hexdigest() if structural else None,
        "output_sha256": hashlib.sha256(png).hexdigest(),
        "output_bytes": len(png),
        "seed": fx["seed"],
        "provider_request_id": getattr(adapter, "last_request_id", None),
        "effective_prompt": getattr(adapter, "last_effective_prompt", None),
        "design_version_id": fx["design_version_id"],
        "room_label": fx["room_label"],
        "elapsed_s": round(time.time() - t0, 2),
        "output_path": str(out_path),
    }


def main() -> None:
    arms = [a.strip().upper() for a in os.getenv("BENCH_ARMS", "A,B,C").split(",") if a.strip()]
    fixtures_dir = Path(os.getenv("BENCH_FIXTURES", "")).expanduser()

    print(f"[benchmark] arms={arms} fixtures={fixtures_dir or '(unset)'} MAX_CALLS={MAX_CALLS}")
    if not _authorized():
        print(
            "[benchmark] NOT AUTHORIZED - no fal call made. To run a bounded paid benchmark set\n"
            "            RUN_FAL_BENCHMARK=1 FAL_SINGLE_ATTEMPT=true and provide BENCH_FIXTURES.\n"
            "            See STRUCTURAL_CONDITIONING_BENCHMARK_PLAN.md section 8 for authorization."
        )
        sys.exit(0)

    if not fixtures_dir.is_dir():
        sys.exit(f"ABORT: BENCH_FIXTURES is not a directory: {fixtures_dir}")
    fx = _load_fixtures(fixtures_dir)
    if "C" in arms and fx["structural_bytes"] is None:
        sys.exit("ABORT: Arm C requested but no structural.png fixture present.")
    if len(arms) > MAX_CALLS:
        sys.exit(f"ABORT: {len(arms)} arms exceeds MAX_CALLS={MAX_CALLS}.")

    out_dir = fixtures_dir / "output"
    out_dir.mkdir(exist_ok=True)
    s_sha = _sha16(fx["structural_bytes"]) if fx["structural_bytes"] else None
    print(
        f"[benchmark] base sha16={_sha16(fx['base_bytes'])} structural sha16={s_sha} "
        f"seed={fx['seed']} room={fx['room_label']!r}"
    )

    results = []
    for arm in arms:
        print(f"[benchmark] >>> Arm {arm}: submitting ONE render...")
        rec = _run_arm(arm, fx, out_dir)
        print(
            f"[benchmark] <<< Arm {arm}: mode={rec['conditioning_mode']} "
            f"control={rec['control_source']} out_sha16={rec['output_sha256'][:16]} "
            f"req_id={rec['provider_request_id']}"
        )
        results.append(rec)

    prov = out_dir / "structural_ab_provenance.json"
    payload = {"created_at": time.time(), "arms": results}
    prov.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[benchmark] DONE - {len(results)} render(s). Provenance: {prov}")


if __name__ == "__main__":
    main()
