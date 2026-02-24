#!/usr/bin/env python3
"""Build Task 3(b) prediction dashboard using linear regression."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "MC1_graph.json"
OUT_DIR = ROOT / "src" / "task3b"
OUT_HTML = OUT_DIR / "task3b.html"
OUT_JSON = OUT_DIR / "task3b.json"
TEMPLATE_HTML = OUT_DIR / "task3b.template.html"

CREATIVE_EDGES = {"PerformerOf", "ProducerOf", "ComposerOf", "LyricistOf"}
ARTIST_TYPES = {"Person", "MusicalGroup"}
WORK_TYPES = {"Song", "Album"}
TARGET_GENRE = "oceanus folk"

PRED_YEARS_AHEAD = 5
RECENT_WINDOW_YEARS = 7  # use recent window for regression
MOMENTUM_WINDOW_YEARS = None
DISPLAY_YEARS = None  # show all years in the detail chart
SCORE_ALPHA = 0.7  # weight for predicted vs delta in forecast score


def parse_year(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def linear_forecast(
    years: List[int],
    values: List[int],
    pred_year: int,
) -> Tuple[float, float, float]:
    """Return (predicted_value, last_value, delta)."""
    if len(years) < 2:
        last_val = float(values[-1]) if values else 0.0
        return last_val, last_val, 0.0

    x = np.array(years, dtype=float)
    y = np.array(values, dtype=float)
    A = np.vstack([x, np.ones(len(x))]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    pred = slope * pred_year + intercept
    last_val = float(values[-1])
    pred = max(pred, last_val)
    return float(pred), last_val, float(max(pred - last_val, 0.0))


def main() -> None:
    graph = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if "links" in graph and "edges" not in graph:
        graph["edges"] = graph.pop("links")

    nodes = {node["id"]: node for node in graph["nodes"]}

    # Identify Oceanus Folk works
    oceanus_works = {
        nid
        for nid, node in nodes.items()
        if node.get("Node Type") in WORK_TYPES
        and (node.get("genre") or "").strip().lower() == TARGET_GENRE
    }

    # Artists with Oceanus Folk credits
    artists_with_oceanus = set()
    for edge in graph["edges"]:
        if edge.get("Edge Type") not in CREATIVE_EDGES:
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if src not in nodes or tgt not in nodes:
            continue
        if nodes[src].get("Node Type") not in ARTIST_TYPES:
            continue
        if tgt in oceanus_works:
            artists_with_oceanus.add(src)

    # Build work -> people index (all works, Person collaborators only)
    work_to_people: Dict[int, set[int]] = defaultdict(set)
    for edge in graph["edges"]:
        if edge.get("Edge Type") not in CREATIVE_EDGES:
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if src not in nodes or tgt not in nodes:
            continue
        if nodes[src].get("Node Type") != "Person":
            continue
        if nodes[tgt].get("Node Type") not in WORK_TYPES:
            continue
        work_to_people[tgt].add(src)

    # Credits rows
    credits = []
    for edge in graph["edges"]:
        if edge.get("Edge Type") not in CREATIVE_EDGES:
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if src not in artists_with_oceanus:
            continue
        if src not in nodes or tgt not in nodes:
            continue
        if nodes[src].get("Node Type") not in ARTIST_TYPES:
            continue
        if nodes[tgt].get("Node Type") not in WORK_TYPES:
            continue
        # Only include artists with at least one Oceanus Folk credit (genre filter is for candidates)
        work = nodes[tgt]
        credits.append(
            {
                "artist_id": src,
                "artist": nodes[src].get("name"),
                "work_id": tgt,
                "notable": bool(work.get("notable")),
                "release_date": work.get("release_date"),
            }
        )

    # Build per-artist yearly metrics (deduplicate by artist name)
    artist_year: Dict[str, Dict[int, Dict[str, set[int]]]] = defaultdict(
        lambda: defaultdict(lambda: {"works": set(), "notable": set(), "collabs": set()})
    )

    for row in credits:
        year = parse_year(row["release_date"])
        if year is None:
            continue
        aid = row["artist_id"]
        artist_name = row["artist"]
        if not artist_name:
            continue
        artist_name = " ".join(str(artist_name).split())
        artist_year[artist_name][year]["works"].add(row["work_id"])
        if row["notable"]:
            artist_year[artist_name][year]["notable"].add(row["work_id"])
        collabs = set(work_to_people.get(row["work_id"], set()))
        collabs.discard(aid)
        artist_year[artist_name][year]["collabs"].update(collabs)

    all_years = sorted({y for aid in artist_year for y in artist_year[aid]})
    if not all_years:
        raise RuntimeError("No Oceanus Folk artist data found.")

    min_year, max_year = min(all_years), max(all_years)
    pred_year = max_year + PRED_YEARS_AHEAD
    if RECENT_WINDOW_YEARS:
        recent_start = max_year - (RECENT_WINDOW_YEARS - 1)
        recent_years = list(range(recent_start, max_year + 1))
    else:
        recent_years = list(range(min_year, max_year + 1))
    if DISPLAY_YEARS:
        display_start = max_year - (DISPLAY_YEARS - 1)
        display_years = list(range(display_start, max_year + 1))
    else:
        display_years = list(range(min_year, max_year + 1))

    artist_payload = []

    for name, yearly in artist_year.items():
        series = []
        cum_releases = 0
        cum_notable = 0
        cum_collabs = 0
        for year in range(min_year, max_year + 1):
            data = yearly.get(year)
            if data:
                releases = len(data["works"])
                notable = len(data["notable"])
                collabs = len(data["collabs"])
            else:
                releases = 0
                notable = 0
                collabs = 0
            cum_releases += releases
            cum_notable += notable
            cum_collabs += collabs
            series.append((year, cum_releases, cum_collabs, cum_notable))

        # Regression window
        window_vals = [row for row in series if row[0] in recent_years]
        if len(window_vals) < 2:
            window_vals = series[-5:]

        win_years = [row[0] for row in window_vals]
        win_activity = [row[1] for row in window_vals]
        win_influence = [row[2] for row in window_vals]
        win_popularity = [row[3] for row in window_vals]

        pred_activity, cur_activity, delta_activity = linear_forecast(
            win_years, win_activity, pred_year
        )
        pred_influence, cur_influence, delta_influence = linear_forecast(
            win_years, win_influence, pred_year
        )
        pred_popularity, cur_popularity, delta_popularity = linear_forecast(
            win_years, win_popularity, pred_year
        )

        display_activity = [row[1] for row in series if row[0] in display_years]
        display_influence = [row[2] for row in series if row[0] in display_years]
        display_popularity = [row[3] for row in series if row[0] in display_years]

        artist_payload.append(
            {
                "name": name,
                "activity": {
                    "current": cur_activity,
                    "predicted": pred_activity,
                    "delta": delta_activity,
                },
                "influence": {
                    "current": cur_influence,
                    "predicted": pred_influence,
                    "delta": delta_influence,
                },
                "popularity": {
                    "current": cur_popularity,
                    "predicted": pred_popularity,
                    "delta": delta_popularity,
                },
                "series": {
                    "years": display_years,
                    "activity": display_activity,
                    "influence": display_influence,
                    "popularity": display_popularity,
                },
            }
        )

    # Normalize forecast signals (predicted level + delta growth)
    def normalize_metric(key: str, field: str) -> Dict[str, float]:
        values = [a[key][field] for a in artist_payload]
        min_val, max_val = min(values), max(values)
        if max_val - min_val == 0:
            return {a["name"]: 0.0 for a in artist_payload}
        return {
            a["name"]: (a[key][field] - min_val) / (max_val - min_val)
            for a in artist_payload
        }

    norm_activity_pred = normalize_metric("activity", "predicted")
    norm_activity_delta = normalize_metric("activity", "delta")
    norm_influence_pred = normalize_metric("influence", "predicted")
    norm_influence_delta = normalize_metric("influence", "delta")
    norm_popularity_pred = normalize_metric("popularity", "predicted")
    norm_popularity_delta = normalize_metric("popularity", "delta")

    for artist in artist_payload:
        name = artist["name"]
        artist["norm"] = {
            "activity": SCORE_ALPHA * norm_activity_pred.get(name, 0.0)
            + (1.0 - SCORE_ALPHA) * norm_activity_delta.get(name, 0.0),
            "influence": SCORE_ALPHA * norm_influence_pred.get(name, 0.0)
            + (1.0 - SCORE_ALPHA) * norm_influence_delta.get(name, 0.0),
            "popularity": SCORE_ALPHA * norm_popularity_pred.get(name, 0.0)
            + (1.0 - SCORE_ALPHA) * norm_popularity_delta.get(name, 0.0),
        }

    # KMeans clustering + elbow/silhouette
    features = np.array(
        [
            [
                artist["norm"]["activity"],
                artist["norm"]["influence"],
                artist["norm"]["popularity"],
            ]
            for artist in artist_payload
        ]
    )
    max_k = min(8, max(2, len(artist_payload) - 1))
    elbow_points = []
    silhouette_points = []
    silhouette_raw_points = []
    best_k = 2
    best_sil = -1.0
    best_k_ge3 = None
    best_sil_ge3 = -1.0
    sailor_idx = next(
        (idx for idx, artist in enumerate(artist_payload) if artist.get("name") == "Sailor Shift"),
        None,
    )
    if len(artist_payload) >= 3:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score

        for k in range(2, max_k + 1):
            km = KMeans(n_clusters=k, n_init=10, random_state=42)
            labels = km.fit_predict(features)
            elbow_points.append({"k": k, "inertia": float(km.inertia_)})
            try:
                sil_raw = float(silhouette_score(features, labels))
            except ValueError:
                sil_raw = -1.0
            sizes = np.bincount(labels)
            sailor_size = None
            sil_adj = sil_raw
            if sailor_idx is not None:
                sailor_cluster = labels[sailor_idx]
                sailor_size = int(sizes[sailor_cluster])
                penalty = min(0.2, 0.01 * max(sailor_size - 1, 0))
                sil_adj = sil_raw * (1.0 - penalty)
                if sailor_size == 1:
                    sil_adj *= 1.1

            silhouette_raw_points.append(
                {"k": k, "score": sil_raw, "sailor_size": sailor_size}
            )
            silhouette_points.append(
                {"k": k, "score": sil_adj, "sailor_size": sailor_size}
            )

            if sil_adj > best_sil:
                best_sil = sil_adj
                best_k = k
            if k >= 3 and sil_adj > best_sil_ge3:
                best_sil_ge3 = sil_adj
                best_k_ge3 = k

        # Favor k>=3 to avoid collapsing to a trivial split around a dominant outlier.
        if best_k_ge3 is not None:
            best_k = best_k_ge3

        km_final = KMeans(n_clusters=best_k, n_init=20, random_state=42)
        final_labels = km_final.fit_predict(features)
    else:
        final_labels = np.zeros(len(artist_payload), dtype=int)

    for artist, label in zip(artist_payload, final_labels):
        # Store clusters as 1..k for consistency in UI labels
        artist["cluster"] = int(label) + 1

    candidates_excl_sailor = len(
        [a for a in artist_payload if a.get("name") != "Sailor Shift"]
    )

    payload = {
        "meta": {
            "max_year": max_year,
            "pred_year": pred_year,
            "recent_years": recent_years,
            "display_years": display_years,
            "candidates": len(artist_payload),
            "candidates_excl_sailor": candidates_excl_sailor,
            "score_alpha": SCORE_ALPHA,
            "cluster_k": best_k,
            "elbow": elbow_points,
            "silhouette": silhouette_points,
            "silhouette_raw": silhouette_raw_points,
        },
        "artists": artist_payload,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    template = TEMPLATE_HTML.read_text(encoding="utf-8")
    template = template.replace("__DATA__", json.dumps(payload, ensure_ascii=True))
    template = template.replace("__DATA_URL__", "task3b.json")
    template = template.replace(
        "__CANDIDATES__", str(payload["meta"]["candidates_excl_sailor"])
    )
    template = template.replace("__MAX_YEAR__", str(max_year))
    template = template.replace("__PRED_YEAR__", str(pred_year))
    template = template.replace("__SCORE_ALPHA__", f"{SCORE_ALPHA:.2f}")

    OUT_HTML.write_text(template, encoding="utf-8")
    print("Wrote", OUT_HTML)
    print("Wrote", OUT_JSON)


if __name__ == "__main__":
    main()
