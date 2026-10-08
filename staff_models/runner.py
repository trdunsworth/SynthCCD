"""Registry mapping staffing models to parameterized entry points.

Each model declares a parameter spec (name, kind, default, help) and a
``run(params) -> dict[str, object]`` that returns a flat mapping of
metric labels to values. The TUI and any other front end consume this
registry, so a model becomes invocable by adding one entry here.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

import allen_cunneen
import efpa
import engset
import erlang_a
import erlang_b
import erlang_c
import erlang_r
import mm_c_k
import occupancy_staffing
import psa_staffing
import square_root_staffing


@dataclass
class Param:
    name: str
    kind: str
    default: Any
    help: str


@dataclass
class ModelSpec:
    key: str
    label: str
    description: str
    params: list[Param]
    run: Callable[[dict[str, Any]], dict[str, object]]


def _f(s: str) -> float:
    return float(s)


def _i(s: str) -> int:
    return int(float(s))


def parse_params(spec: ModelSpec, raw: dict[str, str]) -> dict[str, Any]:
    """Convert raw string inputs into typed parameter values."""
    out: dict[str, Any] = {}
    for p in spec.params:
        text = raw.get(p.name, "").strip()
        if p.kind == "float":
            out[p.name] = _f(text) if text else float(p.default)
        elif p.kind == "int":
            out[p.name] = _i(text) if text else int(p.default)
        elif p.kind == "ratelist":
            if text:
                out[p.name] = [float(x) for x in text.split(",")]
            else:
                out[p.name] = list(p.default)
        elif p.kind == "json":
            import json

            out[p.name] = json.loads(text) if text else p.default
        else:
            out[p.name] = text or p.default
    return out


def _run_erlang_b(p: dict[str, Any]) -> dict[str, object]:
    return {
        "blocking_probability": erlang_b.blocking_probability(p["erlangs"], p["servers"]),
        "trunks_for_1pct_blocking": erlang_b.required_servers(p["erlangs"], 0.01),
    }


def _run_erlang_c(p: dict[str, Any]) -> dict[str, object]:
    mu = 1.0 / p["mean_handle_seconds"]
    return {
        "wait_probability": erlang_c.wait_probability(p["erlangs"], p["servers"]),
        "asa_seconds": erlang_c.average_speed_of_answer(p["erlangs"], p["servers"], mu),
        f"service_level_at_{p['threshold_seconds']}s": erlang_c.service_level(
            p["erlangs"], p["servers"], mu, p["threshold_seconds"]
        ),
    }


def _run_erlang_a(p: dict[str, Any]) -> dict[str, object]:
    mu = 1.0 / p["mean_handle_seconds"]
    theta = 1.0 / p["mean_patience_seconds"]
    return cast(dict[str, object], erlang_a.analyze(p["lam_per_sec"], mu, p["agents"], theta))


def _run_engset(p: dict[str, Any]) -> dict[str, object]:
    return {
        "time_congestion": engset.time_congestion(p["sources"], p["servers"], p["gamma_over_mu"]),
        "call_congestion": engset.call_congestion(p["sources"], p["servers"], p["gamma_over_mu"]),
        "carried_traffic_erlangs": engset.carried_traffic(p["sources"], p["servers"], p["gamma_over_mu"]),
    }


def _run_mm_c_k(p: dict[str, Any]) -> dict[str, object]:
    return {
        "blocking_probability": mm_c_k.blocking_probability(p["erlangs"], p["servers"], p["capacity"]),
        "delay_probability": mm_c_k.delay_probability(p["erlangs"], p["servers"], p["capacity"]),
        "mean_queue_length": mm_c_k.mean_queue_length(p["erlangs"], p["servers"], p["capacity"]),
    }


def _run_allen_cunneen(p: dict[str, Any]) -> dict[str, object]:
    mu = 1.0 / p["mean_handle_seconds"]
    return {
        "wait_probability_mg": allen_cunneen.wait_probability_mg(p["erlangs"], p["servers"], p["scv"]),
        "mean_wait_seconds": allen_cunneen.mean_wait_mg(p["erlangs"], p["servers"], mu, p["scv"]),
    }


def _run_erlang_r(p: dict[str, Any]) -> dict[str, object]:
    mu = 1.0 / p["mean_handle_seconds"]
    return {
        "effective_offered_load": erlang_r.effective_offered_load(p["lam_per_sec"], mu, p["servers"], p["retry_probability"]),
        "blocking_probability": erlang_r.retry_adjusted_blocking(p["lam_per_sec"], mu, p["servers"], p["retry_probability"]),
    }


def _run_psa(p: dict[str, Any]) -> dict[str, object]:
    mu = 1.0 / p["mean_handle_seconds"]
    plan = psa_staffing.intraday_staffing(p["rates_per_sec"], mu, p["threshold_seconds"], p["target_sl"])
    return {f"interval_{i}_agents": c for i, c in enumerate(plan)}


def _run_occupancy(p: dict[str, Any]) -> dict[str, object]:
    c = occupancy_staffing.staffing_level(p["erlangs"], p["target_occupancy"])
    return {
        "agents": c,
        "achieved_occupancy": occupancy_staffing.achieved_occupancy(p["erlangs"], c),
    }


def _run_square_root(p: dict[str, Any]) -> dict[str, object]:
    c = square_root_staffing.staffing_level(p["erlangs"], p["beta"])
    return {
        "agents": c,
        "implied_occupancy": square_root_staffing.implied_occupancy(p["erlangs"], p["beta"]),
        "delay_probability": square_root_staffing.delay_probability(p["erlangs"], p["beta"]),
    }


_EFPA_DEFAULT = {
    "capacities": [20, 15, 25],
    "routes": [
        {"name": "law", "erlangs": 12.0, "links": [0, 2]},
        {"name": "fire", "erlangs": 8.0, "links": [1, 2]},
        {"name": "ems_shared", "erlangs": 5.0, "links": [2]},
    ],
}


def _run_efpa(p: dict[str, Any]) -> dict[str, object]:
    cfg = p["network_json"]
    routes = [efpa.Route(r["name"], float(r["erlangs"]), list(r["links"])) for r in cfg["routes"]]
    result = efpa.analyze([int(c) for c in cfg["capacities"]], routes)
    out: dict[str, object] = {}
    for j, b in enumerate(result["pool_blocking"]):
        out[f"pool_{j}_blocking"] = b
    for name, stats in result["routes"].items():
        out[f"route_{name}_blocking"] = stats["blocking"]
        out[f"route_{name}_carried_erlangs"] = stats["carried_erlangs"]
    return out


MODELS: list[ModelSpec] = [
    ModelSpec(
        "erlang_b", "Erlang B", "Loss system blocking probability",
        [Param("erlangs", "float", 10.0, "Offered load (erlangs)"),
         Param("servers", "int", 15, "Number of trunks")],
        _run_erlang_b,
    ),
    ModelSpec(
        "erlang_c", "Erlang C", "Delay system wait probability / SL",
        [Param("erlangs", "float", 8.0, "Offered load (erlangs)"),
         Param("servers", "int", 10, "Agents"),
         Param("mean_handle_seconds", "float", 300.0, "Mean AHT"),
         Param("threshold_seconds", "float", 20.0, "SL threshold")],
        _run_erlang_c,
    ),
    ModelSpec(
        "erlang_a", "Erlang A", "Delay with abandonment",
        [Param("lam_per_sec", "float", 0.05, "Arrival rate /s"),
         Param("mean_handle_seconds", "float", 240.0, "Mean AHT"),
         Param("agents", "int", 15, "Agents"),
         Param("mean_patience_seconds", "float", 60.0, "Mean patience")],
        _run_erlang_a,
    ),
    ModelSpec(
        "engset", "Engset", "Finite-source loss model",
        [Param("sources", "int", 50, "Calling sources"),
         Param("servers", "int", 8, "Trunks"),
         Param("gamma_over_mu", "float", 0.2, "Arrival/service ratio per source")],
        _run_engset,
    ),
    ModelSpec(
        "mm_c_k", "M/M/c/K", "Finite-capacity delay-loss",
        [Param("erlangs", "float", 8.0, "Offered load"),
         Param("servers", "int", 10, "Agents"),
         Param("capacity", "int", 15, "System capacity")],
        _run_mm_c_k,
    ),
    ModelSpec(
        "allen_cunneen", "Allen-Cunneen", "M/G/c approximation",
        [Param("erlangs", "float", 8.0, "Offered load"),
         Param("servers", "int", 10, "Agents"),
         Param("mean_handle_seconds", "float", 300.0, "Mean AHT"),
         Param("scv", "float", 1.0, "Service-time SCV^2")],
        _run_allen_cunneen,
    ),
    ModelSpec(
        "erlang_r", "Erlang R", "Retry amplification",
        [Param("lam_per_sec", "float", 0.2, "Arrival rate /s"),
         Param("mean_handle_seconds", "float", 180.0, "Mean AHT"),
         Param("servers", "int", 40, "Trunks"),
         Param("retry_probability", "float", 0.5, "Probability of retry")],
        _run_erlang_r,
    ),
    ModelSpec(
        "psa", "PSA", "Pointwise stationary intraday staffing",
        [Param("rates_per_sec", "ratelist", [0.05, 0.08, 0.14, 0.20], "Comma-separated rates /s"),
         Param("mean_handle_seconds", "float", 300.0, "Mean AHT"),
         Param("threshold_seconds", "float", 20.0, "SL threshold"),
         Param("target_sl", "float", 0.8, "Target service level")],
        _run_psa,
    ),
    ModelSpec(
        "occupancy", "Occupancy", "Utilization-based floor",
        [Param("erlangs", "float", 12.0, "Offered load"),
         Param("target_occupancy", "float", 0.85, "Target occupancy")],
        _run_occupancy,
    ),
    ModelSpec(
        "square_root", "Square-root (QED)", "Halfin-Whitt staffing",
        [Param("erlangs", "float", 50.0, "Offered load"),
         Param("beta", "float", 1.0, "QED slack parameter")],
        _run_square_root,
    ),
    ModelSpec(
        "efpa", "EFPA", "Skill-based routing fixed point",
        [Param("network_json", "json", _EFPA_DEFAULT, "JSON: capacities + routes")],
        _run_efpa,
    ),
]


def get_model(key: str) -> ModelSpec:
    for spec in MODELS:
        if spec.key == key:
            return spec
    raise KeyError(f"unknown model {key!r}")
