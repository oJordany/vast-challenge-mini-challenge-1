#!/usr/bin/env python3
"""Build Task 2(b) visualization: Oceanus Folk influence network."""
from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "MC1_graph.json"
OUT_HTML = ROOT / "src" / "task2b" / "task2b.html"
OUT_JSON = ROOT / "src" / "task2b" / "task2b.json"
TEMPLATE_HTML = ROOT / "src" / "task2b" / "task2b.template.html"

INFLUENCE_TYPES = {
    "DirectlySamples",
    "InterpolatesFrom",
    "CoverOf",
    "LyricalReferenceTo",
    "InStyleOf",
}

CONTRIB_TYPES = {
    "PerformerOf": "Performer",
    "ComposerOf": "Composer",
    "ProducerOf": "Producer",
    "LyricistOf": "Lyricist",
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


def lighten(hex_color: str, amount: float = 0.45) -> str:
    """Blend hex color with white by amount (0-1)."""
    color = hex_color.lstrip("#")
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


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

    oceanus_ids = {
        wid
        for wid, work in works.items()
        if (work.get("genre") or "").strip().lower() == "oceanus folk"
    }

    influenced_work_ids: set[int] = set()
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

        influenced_work_ids.add(source_id)

    influenced_works = {
        wid: {
            "title": work.get("name", "Unknown"),
            "genre": work.get("genre") or "Unknown",
        }
        for wid, work in works.items()
        if wid in influenced_work_ids
    }

    contributions: list[dict[str, str]] = []
    for edge in graph["links"]:
        edge_type = edge.get("Edge Type")
        if edge_type not in CONTRIB_TYPES:
            continue
        target_id = edge["target"]
        if target_id not in influenced_work_ids:
            continue
        artist_node = artists.get(edge["source"])
        work_node = influenced_works.get(target_id)
        if not artist_node or not work_node:
            continue

        contributions.append(
            {
                "artist": artist_node.get("name", "Unknown"),
                "title": work_node["title"],
                "genre": work_node["genre"],
                "role": CONTRIB_TYPES[edge_type],
            }
        )

    # Build json matching repo structure
    artist_roles: dict[str, list[dict[str, str]]] = defaultdict(list)
    for c in contributions:
        artist_roles[c["artist"]].append(
            {"title": c["title"], "genre": c["genre"], "role": c["role"]}
        )

    artists_list = [
        {"id": artist, "roles": roles}
        for artist, roles in sorted(artist_roles.items(), key=lambda x: x[0])
    ]

    works_list = [
        {"id": info["title"], "genre": info["genre"]}
        for info in sorted(influenced_works.values(), key=lambda x: x["title"])
    ]

    links_list = [
        {
            "source": c["artist"],
            "target": c["title"],
            "role": c["role"],
            "genre": c["genre"],
        }
        for c in contributions
    ]

    hierarchy_map: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for c in contributions:
        hierarchy_map[c["genre"]][c["title"]].append(
            {"artist": c["artist"], "role": c["role"]}
        )

    hierarchy_list = []
    for genre in sorted(hierarchy_map.keys()):
        works_entries = []
        for title in sorted(hierarchy_map[genre].keys()):
            works_entries.append(
                {"title": title, "contributors": hierarchy_map[genre][title]}
            )
        hierarchy_list.append({"genre": genre, "works": works_entries})

    preprocessed = {
        "artists": artists_list,
        "works": works_list,
        "links": links_list,
        "hierarchy": hierarchy_list,
    }
    OUT_JSON.write_text(json.dumps(preprocessed, ensure_ascii=True), encoding="utf-8")

    # Network graph data
    artist_counts = Counter({artist: len(roles) for artist, roles in artist_roles.items()})
    filtered_artists = {artist for artist, count in artist_counts.items() if count >= 3}

    artist_genre_counts: dict[str, Counter[str]] = defaultdict(Counter)
    artist_role_counts: dict[str, Counter[str]] = defaultdict(Counter)
    artist_work_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for c in contributions:
        artist = c["artist"]
        if artist not in filtered_artists:
            continue
        group = map_genre(c["genre"])
        artist_genre_counts[artist][group] += 1
        artist_role_counts[artist][c["role"]] += 1
        artist_work_counts[artist][c["title"]] += 1

    group_work_titles: dict[str, set[str]] = defaultdict(set)
    for info in influenced_works.values():
        group = map_genre(info["genre"])
        group_work_titles[group].add(info["title"])

    links = []
    for group in GROUP_ORDER:
        if group not in group_work_titles:
            continue
        count = len(group_work_titles[group])
        if count == 0:
            continue
        links.append(
            {
                "source": "Oceanus Folk",
                "target": group,
                "value": count,
                "lineStyle": {
                    "color": "#111827",
                    "opacity": 0.5,
                    "width": round(1.0 + count / 6, 2),
                },
            }
        )

    for artist in sorted(filtered_artists):
        for group, count in artist_genre_counts[artist].items():
            if count <= 0:
                continue
            links.append(
                {
                    "source": group,
                    "target": artist,
                    "value": count,
                    "lineStyle": {
                        "color": GROUP_COLORS.get(group, "#94a3b8"),
                        "opacity": 0.45,
                        "width": round(1.0 + count * 0.7, 2),
                    },
                }
            )

    max_artist = max(artist_counts[artist] for artist in filtered_artists) if filtered_artists else 1
    max_genre = max((len(v) for v in group_work_titles.values()), default=1)

    nodes = []
    nodes.append(
        {
            "id": "Oceanus Folk",
            "name": "Oceanus Folk",
            "category": 0,
            "symbol": "roundRect",
            "symbolSize": 44,
            "value": sum(len(v) for v in group_work_titles.values()),
            "itemStyle": {"color": "#111827"},
            "label": {
                "show": True,
                "color": "#0f172a",
                "fontWeight": "bold",
                "textBorderColor": "#ffffff",
                "textBorderWidth": 2,
            },
            "tooltip": "<strong>Oceanus Folk</strong><br/>Reference source for influence",
        }
    )

    genre_top_artists: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for artist in filtered_artists:
        for group, count in artist_genre_counts[artist].items():
            genre_top_artists[group].append((artist, count))

    for group in GROUP_ORDER:
        if group not in group_work_titles:
            continue
        count = len(group_work_titles[group])
        if count == 0:
            continue
        top_artists = sorted(genre_top_artists.get(group, []), key=lambda x: (-x[1], x[0]))[:3]
        lines = [f"<strong>{html.escape(group)}</strong>", f"Influenced works: {count}"]
        if top_artists:
            lines.append("<span style='color:#94a3b8'>Top artists</span>")
            for artist, c in top_artists:
                lines.append(f"• {html.escape(artist)} ({c})")
        tooltip_html = "<br/>".join(lines)
        size = 24 + (count / max_genre) ** 1.2 * 32
        nodes.append(
            {
                "id": group,
                "name": group,
                "category": 1,
                "symbol": "diamond",
                "symbolSize": round(size, 1),
                "value": count,
                "itemStyle": {"color": GROUP_COLORS.get(group, "#94a3b8")},
                "label": {"show": True, "color": "#0f172a", "fontWeight": 600},
                "tooltip": tooltip_html,
            }
        )

    artist_nodes = []
    for artist in filtered_artists:
        total = artist_counts[artist]
        by_genre = artist_genre_counts[artist]
        by_role = artist_role_counts[artist]
        top_genre = max(by_genre.items(), key=lambda x: x[1])[0] if by_genre else "Rock"
        base_color = GROUP_COLORS.get(top_genre, "#94a3b8")
        fill_color = lighten(base_color, 0.5)

        lines = [f"<strong>{html.escape(artist)}</strong>", f"Total roles: {total}"]
        if by_genre:
            lines.append("<span style='color:#94a3b8'>Genres</span>")
            for genre, count in sorted(by_genre.items(), key=lambda x: (-x[1], x[0])):
                lines.append(f"• {genre}: {count}")
        if by_role:
            lines.append("<span style='color:#94a3b8'>Roles</span>")
            for role, count in sorted(by_role.items(), key=lambda x: (-x[1], x[0])):
                lines.append(f"• {role}: {count}")
        top_works = artist_work_counts[artist].most_common(5)
        if top_works:
            lines.append("<span style='color:#94a3b8'>Top works</span>")
            for title, count in top_works:
                lines.append(f"• {html.escape(title)} ({count})")

        size = 12 + (total / max_artist) ** 1.3 * 30
        artist_nodes.append(
            {
                "id": artist,
                "name": artist,
                "category": 2,
                "symbol": "circle",
                "symbolSize": round(size, 1),
                "value": total,
                "itemStyle": {
                    "color": fill_color,
                    "borderColor": base_color,
                    "borderWidth": 1.2,
                },
                "label": {"show": total >= 4, "color": "#0f172a"},
                "tooltip": "<br/>".join(lines),
            }
        )

    nodes.extend(sorted(artist_nodes, key=lambda x: x["name"]))

    artist_ranking = [
        {"name": artist, "count": artist_counts[artist]}
        for artist in sorted(filtered_artists, key=lambda a: (-artist_counts[a], a))
    ]

    total_influenced_works = len(works_list)
    total_influenced_artists = len(filtered_artists)
    top_genre = max(group_work_titles.items(), key=lambda x: len(x[1])) if group_work_titles else ("—", set())
    top_genre_label = f"{top_genre[0]} ({len(top_genre[1])})"
    top_artist_label = (
        f"{artist_ranking[0]['name']} ({artist_ranking[0]['count']})"
        if artist_ranking
        else "—"
    )

    payload = {
        "nodes": nodes,
        "links": links,
        "topArtists": artist_ranking,
        "artistRanking": artist_ranking,
        "artistDetails": {},
        "artistTotals": {artist: int(artist_counts[artist]) for artist in filtered_artists},
        "artistGenreCounts": {
            artist: dict(counts) for artist, counts in artist_genre_counts.items()
        },
        "kpis": {
            "works": total_influenced_works,
            "artists": total_influenced_artists,
            "topGenre": top_genre_label,
            "topArtist": top_artist_label,
        },
    }

    artist_details: dict[str, list[dict[str, str]]] = defaultdict(list)
    for c in contributions:
        artist = c["artist"]
        if artist not in filtered_artists:
            continue
        artist_details[artist].append(
            {"genre": c["genre"], "title": c["title"], "role": c["role"]}
        )

    for artist, entries in artist_details.items():
        entries.sort(key=lambda x: (x["genre"], x["title"], x["role"]))

    payload["artistDetails"] = {k: v for k, v in artist_details.items()}

    html_template = TEMPLATE_HTML.read_text(encoding="utf-8")
    placeholders = {
        "__DATA__": json.dumps(payload, ensure_ascii=True),
        "__KPI_WORKS__": str(total_influenced_works),
        "__KPI_ARTISTS__": str(total_influenced_artists),
        "__KPI_TOP_GENRE__": top_genre_label,
        "__KPI_TOP_ARTIST__": top_artist_label,
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
