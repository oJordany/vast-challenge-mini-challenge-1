#!/usr/bin/env python3
"""Build Task 2(a) visualization: Oceanus Folk influence waves."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "MC1_graph.json"
OUT_HTML = ROOT / "src" / "task2a" / "task2a.html"
OUT_JSON = ROOT / "src" / "task2a" / "task2a.json"
TEMPLATE_HTML = ROOT / "src" / "task2a" / "task2a.template.html"

INFLUENCE_TYPES = {
    "DirectlySamples",
    "InterpolatesFrom",
    "CoverOf",
    "LyricalReferenceTo",
    "InStyleOf",
}

GROUP_ORDER = ["Pop", "Rock", "Metal", "Folk", "Electronic", "Punk"]
GROUP_COLORS = {
    "Pop": "#f97316",
    "Rock": "#3b82f6",
    "Metal": "#64748b",
    "Folk": "#22c55e",
    "Electronic": "#06b6d4",
    "Punk": "#e11d48",
}

GENRE_GROUPS = {
    "Dream Pop": "Pop",
    "Synthpop": "Pop",
    "Indie Pop": "Pop",
    "Indie Rock": "Rock",
    "Alternative Rock": "Rock",
    "Post-Apocalyptic Folk": "Folk",
    "Desert Rock": "Rock",
    "Jazz Surf Rock": "Rock",
    "Doom Metal": "Metal",
    "Speed Metal": "Metal",
    "Symphonic Metal": "Metal",
    "Darkwave": "Electronic",
    "Synthwave": "Electronic",
    "Space Rock": "Rock",
    "Americana": "Folk",
    "Indie Folk": "Folk",
    "Emo/Pop Punk": "Punk",
}


def parse_year(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def map_genre(raw: str | None) -> str:
    if not raw:
        return "Rock"
    return GENRE_GROUPS.get(raw, "Rock")


def main() -> None:
    graph = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    works = {
        node["id"]: node
        for node in graph["nodes"]
        if node.get("Node Type") in ("Song", "Album")
    }

    oceanus_ids = {
        wid
        for wid, work in works.items()
        if (work.get("genre") or "").strip().lower() == "oceanus folk"
    }

    influenced_rows: list[dict[str, object]] = []
    for edge in graph["links"]:
        if edge.get("Edge Type") not in INFLUENCE_TYPES:
            continue
        source_id = edge["source"]
        target_id = edge["target"]
        if target_id not in oceanus_ids:
            continue
        if source_id in oceanus_ids:
            continue

        source = works.get(source_id)
        target = works.get(target_id)
        if not source or not target:
            continue

        source_year = parse_year(source.get("release_date"))
        target_year = parse_year(target.get("release_date"))
        if source_year is None or target_year is None:
            continue
        if source_year <= target_year:
            continue

        influenced_rows.append(
            {
                "year": source_year,
                "group": map_genre(source.get("genre")),
                "subgenre": source.get("genre") or "Unknown",
            }
        )

    influenced_df = pd.DataFrame(influenced_rows)
    counts_df = (
        influenced_df.groupby(["year", "group"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    sub_counts = (
        influenced_df.groupby(["year", "group", "subgenre"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )

    oceanus_rows: list[dict[str, int]] = []
    for wid in oceanus_ids:
        work = works.get(wid)
        if not work:
            continue
        year = parse_year(work.get("release_date"))
        if year is None:
            continue
        oceanus_rows.append({"year": year, "count": 1})

    oceanus_df = pd.DataFrame(oceanus_rows)
    oceanus_df = oceanus_df.groupby("year", as_index=False)["count"].sum()

    if counts_df.empty:
        raise RuntimeError("No influenced works found for Oceanus Folk.")

    count_lookup = {
        (int(row["year"]), row["group"]): int(row["count"])
        for _, row in counts_df.iterrows()
    }

    oceanus_by_year: Counter[int] = Counter()
    for _, row in oceanus_df.iterrows():
        oceanus_by_year[int(row["year"])] = int(row["count"])

    years_set = {year for year, _ in count_lookup.keys()}
    years_set.update(oceanus_by_year.keys())
    years = sorted(years_set)

    totals_by_year = Counter({int(y): 0 for y in years})
    for (year, _group), count in count_lookup.items():
        totals_by_year[int(year)] += int(count)

    group_series: list[dict[str, object]] = []
    for group in GROUP_ORDER:
        data = [count_lookup.get((year, group), 0) for year in years]
        group_series.append({"name": group, "data": data, "color": GROUP_COLORS[group]})

    totals = [totals_by_year.get(year, 0) for year in years]
    oceanus_series = [oceanus_by_year.get(year, 0) for year in years]

    tooltip_data: dict[str, dict[str, dict[str, int]]] = {}
    for _, row in sub_counts.iterrows():
        year = str(int(row["year"]))
        group = str(row["group"])
        subgenre = str(row["subgenre"])
        count = int(row["count"])
        tooltip_data.setdefault(year, {}).setdefault(group, {})[subgenre] = count

    oceanus_by_year_str = {str(year): int(count) for year, count in oceanus_by_year.items()}

    payload = {
        "years": years,
        "groupOrder": GROUP_ORDER,
        "series": group_series,
        "oceanus": {"name": "Oceanus Folk works", "data": oceanus_series, "color": "#111827"},
        "totals": totals,
        "tooltip": tooltip_data,
        "oceanusByYear": oceanus_by_year_str,
    }

    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    totals_df = (
        pd.DataFrame({"year": years, "total": totals})
        if years
        else pd.DataFrame(columns=["year", "total"])
    )
    peak_year = int(totals_df.loc[totals_df["total"].idxmax(), "year"])
    peak_count = int(totals_df["total"].max())
    total_influenced = int(sum(totals))
    oceanus_total = int(sum(oceanus_series))
    top_group = (
        pd.DataFrame({
            "group": [s["name"] for s in group_series],
            "count": [sum(s["data"]) for s in group_series],
        })
        .sort_values("count", ascending=False)
    )
    top_group_name = str(top_group.iloc[0]["group"])
    top_group_count = int(top_group.iloc[0]["count"])

    pulse_years = [year for year in years if 2025 <= year <= 2031]
    pulse_total = int(sum(totals_by_year.get(year, 0) for year in pulse_years))

    payload_json = json.dumps(payload, ensure_ascii=True)
    html = TEMPLATE_HTML.read_text(encoding="utf-8")

    placeholders = {
        "__DATA__": payload_json,
        "__DATA_URL__": "task2a.json",
        "__KPI_TOTAL__": f"{total_influenced}",
        "__KPI_PEAK__": f"{peak_year} ({peak_count})",
        "__KPI_TOP_GROUP__": f"{top_group_name} ({top_group_count})",
        "__KPI_SPAN__": f"{years[0]}-{years[-1]}",
        "__KPI_OCEANUS__": f"{oceanus_total}",
        "__KPI_PULSE__": f"2025-2031: {pulse_total}",
    }

    for key, value in placeholders.items():
        if key not in html:
            raise RuntimeError(f"Missing {key} placeholder in template")
        html = html.replace(key, value)

    OUT_HTML.write_text(html, encoding="utf-8")
    print("Wrote", OUT_HTML)
    print("Wrote", OUT_JSON)


if __name__ == "__main__":
    main()
