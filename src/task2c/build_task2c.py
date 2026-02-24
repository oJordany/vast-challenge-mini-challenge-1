#!/usr/bin/env python3
"""Build Task 2(c) visualization: Oceanus Folk change & Sailor Shift rise."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "MC1_graph.json"
OUT_HTML = ROOT / "src" / "task2c" / "task2c.html"
OUT_JSON = ROOT / "src" / "task2c" / "task2c.json"
TEMPLATE_HTML = ROOT / "src" / "task2c" / "task2c.template.html"

SAILOR_NAME = "Sailor Shift"

INFLUENCE_TYPES = {
    "DirectlySamples",
    "InterpolatesFrom",
    "CoverOf",
    "LyricalReferenceTo",
    "InStyleOf",
}

CONTRIB_TYPES = {
    "PerformerOf",
    "ComposerOf",
    "ProducerOf",
    "LyricistOf",
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
    artists = {
        node["id"]: node
        for node in graph["nodes"]
        if node.get("Node Type") in ("Person", "MusicalGroup")
    }

    sailor_id = None
    for node_id, node in artists.items():
        if (node.get("name") or "").strip() == SAILOR_NAME:
            sailor_id = node_id
            break

    oceanus_ids = {
        wid
        for wid, work in works.items()
        if (work.get("genre") or "").strip().lower() == "oceanus folk"
    }

    oceanus_by_year: Counter[int] = Counter()
    oceanus_work_years: dict[int, int] = {}
    for wid in oceanus_ids:
        work = works.get(wid)
        year = parse_year(work.get("release_date") if work else None)
        if year is None:
            continue
        oceanus_by_year[year] += 1
        oceanus_work_years[wid] = year

    years = sorted(oceanus_by_year.keys())
    if not years:
        raise RuntimeError("No Oceanus Folk works found.")

    sailor_work_ids: set[int] = set()
    if sailor_id is not None:
        for edge in graph["links"]:
            if edge.get("Edge Type") not in CONTRIB_TYPES:
                continue
            if edge.get("source") != sailor_id:
                continue
            target_id = edge.get("target")
            if target_id in oceanus_work_years:
                sailor_work_ids.add(target_id)

    sailor_by_year: Counter[int] = Counter()
    for wid in sailor_work_ids:
        year = oceanus_work_years.get(wid)
        if year is not None:
            sailor_by_year[year] += 1

    inspiration_counts: Counter[tuple[int, str]] = Counter()
    for edge in graph["links"]:
        if edge.get("Edge Type") not in INFLUENCE_TYPES:
            continue
        source_id = edge.get("source")
        target_id = edge.get("target")
        if source_id not in oceanus_ids:
            continue
        if target_id not in works:
            continue
        if target_id in oceanus_ids:
            continue
        source_year = oceanus_work_years.get(source_id)
        target_year = parse_year(works[target_id].get("release_date"))
        if source_year is None or target_year is None:
            continue
        if target_year >= source_year:
            continue
        genre = works[target_id].get("genre") or "Unknown"
        inspiration_counts[(source_year, genre)] += 1

    total_oceanus = int(sum(oceanus_by_year.values()))
    total_sailor = int(sum(sailor_by_year.values()))

    genre_totals: Counter[str] = Counter()
    for (_year, genre), count in inspiration_counts.items():
        genre_totals[genre] += count
    top_genre = None
    top_genre_count = 0
    if genre_totals:
        top_genre, top_genre_count = genre_totals.most_common(1)[0]

    peak_share_year = None
    peak_share = 0.0
    for year in years:
        oceanus_count = oceanus_by_year.get(year, 0)
        if oceanus_count <= 0:
            continue
        sailor_count = sailor_by_year.get(year, 0)
        share = sailor_count / oceanus_count
        if share > peak_share:
            peak_share = share
            peak_share_year = year

    peak_share_label = (
        f"{peak_share_year} ({peak_share*100:.0f}%)" if peak_share_year else "—"
    )

    rows: list[dict[str, object]] = []
    combined_counts: Counter[tuple[int, str]] = Counter()
    combined_counts.update(inspiration_counts)
    for year, count in oceanus_by_year.items():
        combined_counts[(year, "Oceanus Folk")] += count
    for year, count in sailor_by_year.items():
        combined_counts[(year, "Sailor Oceanus Folk")] += count

    for year in sorted({y for (y, _g) in combined_counts.keys()}):
        year_items = [
            (genre, combined_counts[(year, genre)])
            for (_y, genre) in combined_counts
            if _y == year
        ]
        for genre, count in sorted(
            year_items,
            key=lambda x: (
                x[0] != "Oceanus Folk",
                x[0] != "Sailor Oceanus Folk",
                x[0],
            ),
        ):
            if count <= 0:
                continue
            rows.append({"year": year, "genre": genre, "count": int(count)})

    payload = rows

    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    html_template = TEMPLATE_HTML.read_text(encoding="utf-8")
    placeholders = {
        "__DATA__": json.dumps(payload, ensure_ascii=True),
        "__DATA_URL__": "task2c.json",
        "__KPI_OCEANUS__": str(total_oceanus),
        "__KPI_SAILOR__": f"{total_sailor}",
        "__KPI_TOP_GENRE__": f"{top_genre} ({top_genre_count})" if top_genre else "—",
        "__KPI_PEAK_SHARE__": peak_share_label,
    }

    for key, value in placeholders.items():
        if key not in html_template:
            raise RuntimeError(f"Missing {key} placeholder in template")
        html_template = html_template.replace(key, value)

    OUT_HTML.write_text(html_template, encoding="utf-8")
    print("Wrote", OUT_HTML)
    print("Wrote", OUT_JSON)


if __name__ == "__main__":
    main()
