import pandas as pd
import json
import os
import re
import networkx as nx

def get_last_name(fullname):
    """Extracts the last name from a full name string."""
    parts = fullname.strip().split()
    if not parts:
        return "Unknown"
    # Return the last word, e.g. "Andreas Mund" -> "Mund"
    return parts[-1]

def make_academic_citation(pmid, year, df_authors):
    """Formats authors into academic citation labels, e.g. 'Mund et al., 2022'."""
    relevant_authors = df_authors[df_authors["PMID"] == pmid].sort_values("Author Order")
    if relevant_authors.empty:
        return f"Unknown, {year}"
    
    if "Last Name" in relevant_authors.columns:
        last_names = relevant_authors["Last Name"].tolist()
    else:
        last_names = [get_last_name(a) for a in relevant_authors["Author Name"].tolist()]
        
    last_names = [str(n).strip() if (n and pd.notna(n)) else "Unknown" for n in last_names]
    
    if len(last_names) == 1:
        return f"{last_names[0]}, {year}"
    elif len(last_names) == 2:
        return f"{last_names[0]} & {last_names[1]}, {year}"
    else:
        return f"{last_names[0]} et al., {year}"

def generate_dashboard():
    # Read the scraped data
    if not os.path.exists("deep_visual_proteomics_papers.csv") or \
       not os.path.exists("dvp_authors.csv"):
        print("Required CSV files not found. Run main.py first.")
        return

    df_papers = pd.read_csv("deep_visual_proteomics_papers.csv")
    df_authors = pd.read_csv("dvp_authors.csv")

    # Fill NaN values
    df_papers = df_papers.fillna("")
    df_authors = df_authors.fillna("Unknown")

    # --- 1. Compute High-Level Metrics ---
    total_papers = len(df_papers)
    total_authors = df_authors["Author Name"].nunique()
    total_journals = df_papers["Journal"].nunique()
    total_countries = df_authors[df_authors["Country"] != "Unknown"]["Country"].nunique()
    total_institutions = df_authors[df_authors["Institution"] != "Unknown"]["Institution"].nunique()
    total_citations = int(df_papers["Citations"].sum())

    # --- 2. Timeline Aggregation ---
    years = sorted(df_papers["Publication Year"].unique())

    # --- 3. Top Journals ---
    journal_counts = df_papers["Journal"].value_counts().head(10).to_dict()

    # --- 4. Top Countries ---
    paper_countries = df_authors[df_authors["Country"] != "Unknown"].groupby("Country")["PMID"].nunique()
    top_countries = paper_countries.sort_values(ascending=False).head(10).to_dict()

    # --- 5. Top Institutions ---
    paper_insts = df_authors[df_authors["Institution"] != "Unknown"].groupby("Institution")["PMID"].nunique()
    top_institutions = paper_insts.sort_values(ascending=False).head(10).to_dict()

    # --- 8. Collaborator Network (vis.js format) ---
    author_paper_counts = df_authors.groupby("Author Name")["PMID"].nunique().to_dict()
    
    author_info = {}
    for _, row in df_authors.iterrows():
        auth = row["Author Name"]
        country = row["Country"]
        inst = row["Institution"]
        if auth not in author_info:
            author_info[auth] = {"country": country, "institution": inst}
        else:
            if author_info[auth]["country"] == "Unknown" and country != "Unknown":
                author_info[auth]["country"] = country
            if author_info[auth]["institution"] == "Unknown" and inst != "Unknown":
                author_info[auth]["institution"] = inst

    # Second pass: for any author whose country or institution is "Unknown",
    # find the most common non-Unknown country/institution of co-authors across all their papers.
    paper_to_authors = df_authors.groupby("PMID")["Author Name"].apply(list).to_dict()
    from collections import Counter

    for auth, info in author_info.items():
        if info["country"] == "Unknown" or info["institution"] == "Unknown":
            author_pmids = df_authors[df_authors["Author Name"] == auth]["PMID"].unique()
            co_countries = []
            co_institutions = []
            
            for pmid in author_pmids:
                co_auths = paper_to_authors.get(pmid, [])
                for ca in co_auths:
                    if ca == auth:
                        continue
                    ca_info = author_info.get(ca, {})
                    ca_country = ca_info.get("country", "Unknown")
                    ca_inst = ca_info.get("institution", "Unknown")
                    
                    if ca_country != "Unknown":
                        co_countries.append(ca_country)
                    if ca_inst != "Unknown":
                        co_institutions.append(ca_inst)
            
            if info["country"] == "Unknown" and co_countries:
                most_common_country = Counter(co_countries).most_common(1)[0][0]
                info["country"] = most_common_country
                
            if info["institution"] == "Unknown" and co_institutions:
                most_common_inst = Counter(co_institutions).most_common(1)[0][0]
                info["institution"] = most_common_inst

    # Group authors by PMID
    paper_authors_grp = df_authors.groupby("PMID")["Author Name"].apply(list).to_dict()
    
    country_colors = {
        "Denmark": "#ef4444",
        "Germany": "#eab308",
        "United States": "#3b82f6",
        "Sweden": "#a855f7",
        "Switzerland": "#10b981",
        "China": "#f97316",
        "United Kingdom": "#ec4899",
        "Unknown": "#64748b"
    }
    extended_colors = ["#14b8a6", "#06b6d4", "#6366f1", "#84cc16", "#d946ef", "#059669"]
    unique_countries = sorted(list(set(info["country"] for info in author_info.values() if info["country"] != "Unknown")))
    for i, c in enumerate(unique_countries):
        if c not in country_colors:
            country_colors[c] = extended_colors[i % len(extended_colors)]

    nodes = []
    for auth, p_count in author_paper_counts.items():
        info = author_info.get(auth, {"country": "Unknown", "institution": "Unknown"})
        color = country_colors.get(info["country"], country_colors["Unknown"])
        
        nodes.append({
            "id": auth,
            "label": auth,
            "title": f"{auth}\nPublications: {p_count}\nInstitution: {info['institution']}\nCountry: {info['country']}",
            "value": p_count,
            "color": {
                "background": color,
                "border": "#0f172a",
                "highlight": {
                    "background": "#ffffff",
                    "border": color
                }
            },
            "group": info["country"]
        })

    coauthorships = {}
    for pmid, authors_list in paper_authors_grp.items():
        for i in range(len(authors_list)):
            for j in range(i + 1, len(authors_list)):
                a1, a2 = (authors_list[i], authors_list[j]) if authors_list[i] < authors_list[j] else (authors_list[j], authors_list[i])
                pair = (a1, a2)
                coauthorships[pair] = coauthorships.get(pair, 0) + 1

    edges = []
    for (a1, a2), weight in coauthorships.items():
        edges.append({
            "from": a1,
            "to": a2,
            "value": weight,
            "title": f"Co-authored {weight} paper(s)"
        })

    # --- Export Network Data for NetworkX / Matplotlib / Seaborn ---
    # 1. One-mode co-authorship nodes CSV
    nodes_df_data = []
    for n in nodes:
        nodes_df_data.append({
            "Id": n["id"],
            "Label": n["label"],
            "Publications": n["value"],
            "Country": n["group"],
            "Institution": author_info.get(n["id"], {}).get("institution", "Unknown")
        })
    pd.DataFrame(nodes_df_data).to_csv("dvp_coauthorship_nodes.csv", index=False)
    print("Saved 'dvp_coauthorship_nodes.csv'")
    
    # 2. One-mode co-authorship edges CSV
    edges_df_data = []
    for e in edges:
        edges_df_data.append({
            "Source": e["from"],
            "Target": e["to"],
            "Weight": e["value"]
        })
    pd.DataFrame(edges_df_data).to_csv("dvp_coauthorship_edges.csv", index=False)
    print("Saved 'dvp_coauthorship_edges.csv'")
    
    # 3. One-mode GraphML using NetworkX
    G = nx.Graph()
    for n in nodes_df_data:
        G.add_node(
            n["Id"],
            label=n["Label"],
            publications=int(n["Publications"]),
            country=n["Country"],
            institution=n["Institution"]
        )
    for e in edges_df_data:
        G.add_edge(
            e["Source"],
            e["Target"],
            weight=int(e["Weight"])
        )
    nx.write_graphml(G, "dvp_coauthorship_network.graphml")
    print("Saved 'dvp_coauthorship_network.graphml'")

    # 4. Bipartite author-paper nodes CSV
    bipartite_nodes = []
    # Add Author nodes
    for n in nodes_df_data:
        bipartite_nodes.append({
            "Id": n["Id"],
            "Label": n["Label"],
            "Type": "Author",
            "Publications": n["Publications"],
            "Country": n["Country"],
            "Institution": n["Institution"],
            "Year": "",
            "Citations": ""
        })
    # Add Paper nodes
    for _, row in df_papers.iterrows():
        pmid_str = str(row["PMID"])
        year_val = int(row["Publication Year"]) if pd.notna(row["Publication Year"]) else 0
        bipartite_nodes.append({
            "Id": pmid_str,
            "Label": row["Title"],
            "Type": "Paper",
            "Publications": "",
            "Country": "",
            "Institution": "",
            "Year": year_val,
            "Citations": int(row["Citations"]) if pd.notna(row["Citations"]) else 0
        })
    pd.DataFrame(bipartite_nodes).to_csv("dvp_bipartite_nodes.csv", index=False)
    print("Saved 'dvp_bipartite_nodes.csv'")

    # 5. Bipartite author-paper edges CSV
    bipartite_edges = []
    for _, row in df_authors.iterrows():
        bipartite_edges.append({
            "Source": row["Author Name"],
            "Target": str(row["PMID"]),
            "Type": "Author-Paper"
        })
    pd.DataFrame(bipartite_edges).to_csv("dvp_bipartite_edges.csv", index=False)
    print("Saved 'dvp_bipartite_edges.csv'")

    # 6. Bipartite GraphML using NetworkX
    B = nx.Graph()
    for n in bipartite_nodes:
        B.add_node(
            n["Id"],
            label=n["Label"],
            type=n["Type"],
            bipartite=0 if n["Type"] == "Author" else 1,
            publications=n["Publications"] if n["Publications"] != "" else 0,
            country=n["Country"],
            institution=n["Institution"],
            year=n["Year"] if n["Year"] != "" else 0,
            citations=n["Citations"] if n["Citations"] != "" else 0
        )
    for e in bipartite_edges:
        B.add_edge(e["Source"], e["Target"], type=e["Type"])
    nx.write_graphml(B, "dvp_bipartite_network.graphml")
    print("Saved 'dvp_bipartite_network.graphml'")

    # --- 9. Papers & Citations List ---
    papers_list = []
    for _, row in df_papers.iterrows():
        p_authors = df_authors[df_authors["PMID"] == row["PMID"]].sort_values("Author Order")["Author Name"].tolist()
        author_str = ", ".join(p_authors)
        
        year_val = str(int(row["Publication Year"])) if row["Publication Year"] else ""
        citation_label = make_academic_citation(row["PMID"], year_val, df_authors)
        
        # Safely parse Preprint PMID (could be a number or a 'PPR...' string)
        preprint_pmid_raw = str(row["Preprint PMID"]).strip() if pd.notna(row["Preprint PMID"]) else ""
        if preprint_pmid_raw.lower() in ("nan", ""):
            preprint_pmid_val = ""
        else:
            try:
                # If it's a numeric float/int, parse to int string (e.g. '12345.0' -> '12345')
                preprint_pmid_val = str(int(float(preprint_pmid_raw)))
            except ValueError:
                # Keep string identifier as-is (e.g. 'PPR1047858')
                preprint_pmid_val = preprint_pmid_raw

        papers_list.append({
            "pmid": str(row["PMID"]),
            "title": row["Title"],
            "journal": row["Journal"],
            "year": year_val,
            "doi": row["DOI"],
            "type": row["Paper Type"],
            "authors": author_str,
            "abstract": row["Abstract"],
            "citations": int(row["Citations"]),
            "citationLabel": citation_label,
            "preprintPmid": preprint_pmid_val,
            "preprintDoi": str(row["Preprint DOI"]) if pd.notna(row["Preprint DOI"]) and str(row["Preprint DOI"]).strip() != "" and str(row["Preprint DOI"]).lower() != "nan" else ""
        })

    # --- 10. Top Cited Chart ---
    df_top_cited = df_papers.sort_values("Citations", ascending=False).head(10)
    top_cited_labels = [make_academic_citation(row["PMID"], str(int(row["Publication Year"])), df_authors) for _, row in df_top_cited.iterrows()]
    top_cited_citations = df_top_cited["Citations"].astype(int).tolist()

    # Serialize data to JSON
    data_json = json.dumps({
        "metrics": {
            "papers": total_papers,
            "authors": total_authors,
            "journals": total_journals,
            "countries": total_countries,
            "institutions": total_institutions,
            "citations": total_citations
        },
        "journals": {
            "labels": list(journal_counts.keys()),
            "values": list(journal_counts.values())
        },
        "countries": {
            "labels": list(top_countries.keys()),
            "values": list(top_countries.values())
        },
        "institutions": {
            "labels": list(top_institutions.keys()),
            "values": list(top_institutions.values())
        },
        "topCited": {
            "labels": top_cited_labels,
            "values": top_cited_citations
        },
        "network": {
            "nodes": nodes,
            "edges": edges
        },
        "papers": papers_list,
        "authorsList": df_authors.to_dict(orient="records"),
        "countryColors": country_colors
    }, indent=2)

    # Load HTML template
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Deep Visual Proteomics Publication Dashboard</title>
    <!-- Google Fonts: Inter -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <!-- Vis.js CDN (for Network Graph) -->
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>

    <style>
        :root {{
            --bg-main: #0f172a;
            --bg-card: #1e293b;
            --bg-hover: #334155;
            --border-color: #475569;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-purple: #8b5cf6;
            --accent-yellow: #eab308;
            --accent-pink: #f472b6;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Inter', sans-serif;
            -webkit-font-smoothing: antialiased;
        }}

        body {{
            background-color: var(--bg-main);
            color: var(--text-main);
            padding: 2rem;
            min-height: 100vh;
        }}

        .dashboard-container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            margin-bottom: 2.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.5rem;
        }}

        h1 {{
            font-size: 2.25rem;
            font-weight: 800;
            background: linear-gradient(135deg, #60a5fa, #c084fc, #f472b6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.05em;
        }}

        .header-subtitle {{
            color: var(--text-muted);
            font-size: 0.95rem;
            margin-top: 0.25rem;
        }}

        .last-updated {{
            font-size: 0.85rem;
            color: var(--text-muted);
            background: var(--bg-card);
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            border: 1px solid var(--border-color);
        }}

        /* Metrics grid */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2.5rem;
        }}

        .metric-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 1rem;
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}

        .metric-card:hover {{
            transform: translateY(-2px);
            border-color: #64748b;
        }}

        .metric-card::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
        }}

        .metric-card.papers::after {{ background: var(--accent-blue); }}
        .metric-card.authors::after {{ background: var(--accent-purple); }}
        .metric-card.journals::after {{ background: var(--accent-green); }}
        .metric-card.countries::after {{ background: var(--accent-red); }}
        .metric-card.citations::after {{ background: var(--accent-yellow); }}

        .metric-label {{
            font-size: 0.75rem;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .metric-value {{
            font-size: 2.25rem;
            font-weight: 700;
            margin-top: 0.5rem;
            letter-spacing: -0.02em;
        }}

        /* Navigation Tabs */
        .tabs {{
            display: flex;
            gap: 0.75rem;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 2rem;
            padding-bottom: 0.5rem;
            overflow-x: auto;
        }}

        .tab-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 1rem;
            font-weight: 600;
            padding: 0.75rem 1.25rem;
            cursor: pointer;
            border-radius: 0.5rem;
            transition: all 0.2s ease;
            white-space: nowrap;
        }}

        .tab-btn:hover {{
            color: var(--text-main);
            background: var(--bg-card);
        }}

        .tab-btn.active {{
            color: var(--text-main);
            background: var(--accent-blue);
        }}

        /* Tab Content */
        .tab-content {{
            display: none;
        }}

        .tab-content.active {{
            display: block;
        }}

        /* Cards and Layouts */
        .dashboard-grid {{
            display: grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 1.5rem;
        }}

        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 1rem;
            padding: 1.75rem;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        }}

        .col-12 {{ grid-column: span 12; }}
        .col-8 {{ grid-column: span 8; }}
        .col-6 {{ grid-column: span 6; }}
        .col-4 {{ grid-column: span 4; }}

        @media (max-width: 900px) {{
            .col-6, .col-8, .col-4 {{ grid-column: span 12; }}
        }}

        .card-title {{
            font-size: 1.2rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-left: 3px solid var(--accent-blue);
            padding-left: 0.75rem;
        }}

        .chart-container {{
            position: relative;
            width: 100%;
            height: 380px;
        }}

        /* Switch styling */
        .switch {{
            position: relative;
            display: inline-block;
            width: 34px;
            height: 20px;
        }}
        .switch input {{
            opacity: 0;
            width: 0;
            height: 0;
        }}
        .slider {{
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #334155;
            transition: .4s;
        }}
        .slider.round {{
            border-radius: 34px;
        }}
        .switch input:checked + .slider {{
            background-color: #3b82f6 !important;
        }}
        .slider:before {{
            position: absolute;
            content: "";
            height: 14px;
            width: 14px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }}
        .switch input:checked + .slider:before {{
            transform: translateX(14px);
        }}

        /* Timeline SVG Container */
        #timeline-container {{
            width: 100%;
            height: auto;
            background: #0b0f19;
            border-radius: 0.75rem;
            border: 1px solid var(--border-color);
            position: relative;
            overflow: visible;
        }}

        /* Custom Interactive SVG styling */
        .timeline-bar {{
            transition: all 0.2s ease;
        }}
        .timeline-bar:hover {{
            fill-opacity: 1.0 !important;
            filter: url(#glow);
        }}

        /* Interactive Timeline Tooltip */
        #timeline-tooltip {{
            position: absolute;
            background: #1e293b;
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            color: #f8fafc;
            padding: 0.75rem;
            font-size: 0.85rem;
            box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.4);
            display: none;
            pointer-events: none;
            z-index: 100;
            max-width: 320px;
            line-height: 1.4;
        }}

        /* Network Graph Spec */
        #network-container {{
            width: 100%;
            height: 800px;
            background-color: #0b0f19;
            border-radius: 0.75rem;
            border: 1px solid var(--border-color);
        }}

        .network-layout {{
            display: grid;
            grid-template-columns: 4.2fr 1.2fr;
            gap: 1.5rem;
        }}

        @media (max-width: 1024px) {{
            .network-layout {{
                grid-template-columns: 1fr;
            }}
        }}

        .network-sidebar {{
            background: #0f172a;
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            padding: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.85rem;
            max-height: 800px;
            overflow-y: auto;
        }}

        .sidebar-title {{
            font-weight: 700;
            font-size: 0.9rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 0.4rem;
            color: #f8fafc;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }}

        .legend-list {{
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
            margin-top: 0.25rem;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.775rem;
            color: var(--text-muted);
        }}

        .legend-color {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            border: 1px solid #0f172a;
        }}

        /* Slider Styling */
        .slider {{
            -webkit-appearance: none;
            width: 100%;
            height: 6px;
            border-radius: 3px;
            background: #1e293b;
            outline: none;
            margin: 0.5rem 0;
        }}
        .slider::-webkit-slider-thumb {{
            -webkit-appearance: none;
            appearance: none;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: #3b82f6;
            cursor: pointer;
            transition: transform 0.1s ease;
        }}
        .slider::-webkit-slider-thumb:hover {{
            transform: scale(1.2);
        }}

        /* Search and Table Styles */
        .table-controls {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.25rem;
            gap: 1rem;
            flex-wrap: wrap;
        }}

        .btn-download {{
            background: var(--bg-hover);
            color: var(--text-main);
            border: 1px solid var(--border-color);
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            transition: all 0.2s ease;
        }}
        .btn-download:hover {{
            background: var(--border-color);
            border-color: #64748b;
            transform: translateY(-1px);
        }}
        .btn-download svg {{
            flex-shrink: 0;
        }}
        .dropdown {{
            position: relative;
            display: inline-block;
        }}
        .dropdown-content {{
            display: none;
            position: absolute;
            right: 0;
            background-color: var(--bg-card);
            min-width: 240px;
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            box-shadow: 0px 10px 15px -3px rgba(0,0,0,0.5), 0px 4px 6px -4px rgba(0,0,0,0.5);
            z-index: 1000;
            margin-top: 0.25rem;
            overflow: hidden;
        }}
        .dropdown-content a {{
            color: var(--text-main);
            padding: 0.6rem 0.85rem;
            text-decoration: none;
            display: block;
            font-size: 0.8rem;
            font-weight: 500;
            transition: background 0.15s ease;
            text-align: left;
        }}
        .dropdown-content a:hover {{
            background-color: var(--bg-hover);
        }}
        .dropdown:hover .dropdown-content {{
            display: block;
        }}

        .search-input {{
            background: var(--bg-main);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            padding: 0.6rem 1rem;
            border-radius: 0.5rem;
            width: 300px;
            font-size: 0.9rem;
            outline: none;
            transition: border-color 0.2s ease;
        }}

        .search-input:focus {{
            border-color: var(--accent-blue);
        }}

        .filter-select {{
            background: var(--bg-main);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            padding: 0.6rem 1rem;
            border-radius: 0.5rem;
            font-size: 0.9rem;
            outline: none;
            cursor: pointer;
        }}

        .papers-table-wrapper {{
            overflow-x: auto;
            border-radius: 0.5rem;
            border: 1px solid var(--border-color);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }}

        th {{
            background-color: #1e293b;
            color: var(--text-muted);
            padding: 1rem;
            font-weight: 600;
            border-bottom: 2px solid var(--border-color);
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }}

        td {{
            padding: 1rem;
            border-bottom: 1px solid var(--border-color);
            vertical-align: top;
            line-height: 1.45;
        }}

        tr:hover td {{
            background-color: var(--bg-hover);
        }}

        .badge {{
            display: inline-block;
            padding: 0.25rem 0.6rem;
            font-size: 0.75rem;
            font-weight: 600;
            border-radius: 9999px;
            text-transform: uppercase;
        }}

        .badge-methodology {{ background: #3b82f620; color: #60a5fa; border: 1px solid #3b82f640; }}
        .badge-improvement {{ background: #c084fc20; color: #d8b4fe; border: 1px solid #c084fc40; }}
        .badge-application {{ background: #10b98120; color: #34d399; border: 1px solid #10b98140; }}
        .badge-protocol {{ background: #eab30820; color: #fef08a; border: 1px solid #eab30840; }}
        .badge-review {{ background: #f472b620; color: #fbcfe8; border: 1px solid #f472b640; }}

        .external-link {{
            color: var(--accent-blue);
            text-decoration: none;
            font-weight: 500;
        }}

        .external-link:hover {{
            text-decoration: underline;
        }}

        .abstract-truncate {{
            max-width: 450px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            cursor: pointer;
        }}

        .abstract-full {{
            display: none;
            margin-top: 0.5rem;
            padding: 0.75rem;
            background: #0f172a;
            border-radius: 0.375rem;
            border: 1px solid var(--border-color);
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        /* Tooltip styling for vis.js */
        div.vis-network div.vis-tooltip {{
            background-color: #1e293b !important;
            border: 1px solid #475569 !important;
            color: #f8fafc !important;
            border-radius: 0.5rem !important;
            padding: 0.75rem !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 0.85rem !important;
            box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.3) !important;
        }}
    </style>
</head>
<body>

<div class="dashboard-container">
    <header>
        <div>
            <h1>Deep Visual Proteomics (DVP)</h1>
            <div class="header-subtitle">Scientific Literature & Collaboration Analytics Platform</div>
        </div>
        <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 0.5rem;">
            <div class="last-updated">Last updated: Jun 2026</div>
            <div style="display: flex; align-items: center; gap: 1rem;">
                <!-- Download Data Dropdown -->
                <div class="dropdown">
                    <button class="btn-download" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; height: 32px;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                        Download Data
                    </button>
                    <div class="dropdown-content">
                        <div style="font-size: 0.7rem; font-weight: 700; color: var(--text-muted); padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--border-color); text-transform: uppercase; letter-spacing: 0.05em; background: rgba(0,0,0,0.2);">Scraped Databases</div>
                        <a href="deep_visual_proteomics_papers.csv" download>Publications (CSV)</a>
                        <a href="dvp_authors.csv" download>Authors (CSV)</a>
                        <a href="dvp_keywords.csv" download>Keywords (CSV)</a>
                        
                        <div style="font-size: 0.7rem; font-weight: 700; color: var(--text-muted); padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--border-color); border-top: 1px solid var(--border-color); text-transform: uppercase; letter-spacing: 0.05em; background: rgba(0,0,0,0.2);">Co-authorship Network</div>
                        <a href="dvp_coauthorship_nodes.csv" download>Nodes (CSV)</a>
                        <a href="dvp_coauthorship_edges.csv" download>Edges (CSV)</a>
                        <a href="dvp_coauthorship_network.graphml" download>Network GraphML</a>
                        
                        <div style="font-size: 0.7rem; font-weight: 700; color: var(--text-muted); padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--border-color); border-top: 1px solid var(--border-color); text-transform: uppercase; letter-spacing: 0.05em; background: rgba(0,0,0,0.2);">Bipartite Network</div>
                        <a href="dvp_bipartite_nodes.csv" download>Bipartite Nodes (CSV)</a>
                        <a href="dvp_bipartite_edges.csv" download>Bipartite Edges (CSV)</a>
                        <a href="dvp_bipartite_network.graphml" download>Bipartite GraphML</a>
                    </div>
                </div>

                <!-- Toggle Container -->
                <div style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                    <label class="switch" style="position: relative; display: inline-block; width: 34px; height: 20px; margin: 0;">
                        <input type="checkbox" id="include-preprints-toggle" style="opacity: 0; width: 0; height: 0;" onchange="drawBarTimeline()">
                        <span class="slider round" style="position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #334155; transition: .4s; border-radius: 34px;"></span>
                    </label>
                    <span style="font-size: 0.8rem; font-weight: 600; color: #cbd5e1; user-select: none;">Include Preprints</span>
                </div>
            </div>
        </div>
    </header>

    <!-- Metrics Cards -->
    <div class="metrics-grid">
        <div class="metric-card papers">
            <span class="metric-label">Unique Publications</span>
            <span class="metric-value" id="metric-papers">0</span>
        </div>
        <div class="metric-card citations">
            <span class="metric-label">Total Citations</span>
            <span class="metric-value" id="metric-citations">0</span>
        </div>
        <div class="metric-card authors">
            <span class="metric-label">Unique Researchers</span>
            <span class="metric-value" id="metric-authors">0</span>
        </div>
        <div class="metric-card journals">
            <span class="metric-label">Key Journals</span>
            <span class="metric-value" id="metric-journals">0</span>
        </div>
        <div class="metric-card countries">
            <span class="metric-label">Countries Involved</span>
            <span class="metric-value" id="metric-countries">0</span>
        </div>
    </div>

    <!-- Navigation Tabs -->
    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('tab-overview')">Overview & Timeline</button>
        <button class="tab-btn" onclick="switchTab('tab-journals-geography')">Journals & Geography</button>
        <button class="tab-btn" onclick="switchTab('tab-network')">Collaborator Network</button>
        <button class="tab-btn" onclick="switchTab('tab-publications')">Publications Directory</button>
    </div>

    <!-- TAB 1: OVERVIEW & TIMELINE -->
    <div id="tab-overview" class="tab-content active">
        <div class="dashboard-grid">
            <div class="card col-12" style="position: relative; overflow: visible;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;">
                    <div class="card-title" style="margin: 0;">Interactive DVP Publications Chronological Citation Bar Chart</div>
                    <div style="display: flex; gap: 1rem; font-size: 0.8rem; font-weight: 600;">
                        <div style="display: flex; align-items: center; gap: 0.35rem;">
                            <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background-color: #3b82f6;"></span>
                            <span style="color: #94a3b8;">Peer-Reviewed Publications</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 0.35rem;">
                            <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background-color: #a855f7;"></span>
                            <span style="color: #94a3b8;">Preprints</span>
                        </div>
                    </div>
                </div>
                <div id="timeline-container"></div>
                <div id="timeline-tooltip"></div>
            </div>
        </div>
    </div>

    <!-- TAB 2: JOURNALS & GEOGRAPHY -->
    <div id="tab-journals-geography" class="tab-content">
        <div class="dashboard-grid">
            <div class="card col-6">
                <div class="card-title">Top Publishing Journals</div>
                <div class="chart-container">
                    <canvas id="journalsChart"></canvas>
                </div>
            </div>
            <div class="card col-6">
                <div class="card-title">Top Contributing Countries</div>
                <div class="chart-container">
                    <canvas id="countriesChart"></canvas>
                </div>
            </div>
            <div class="card col-12">
                <div class="card-title">Top Contributing Institutions</div>
                <div class="chart-container" style="height: 420px;">
                    <canvas id="institutionsChart"></canvas>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 4: COLLABORATOR NETWORK -->
    <div id="tab-network" class="tab-content">
        <div class="dashboard-grid">
            <div class="card col-12">
                <div class="card-title">Researcher Collaboration & Hub Network Map</div>
                <div class="network-layout">
                    <div id="network-container"></div>
                    <div class="network-sidebar">
                        <div class="sidebar-title">Network Directory</div>
                        <div>
                            <p style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.5rem;">
                                Nodes represent authors. Node size represents DVP paper count. Colors represent primary countries. Drag to rearrange, scroll to zoom.
                            </p>
                        </div>
                        
                        <div class="sidebar-title">Highlight by Paper</div>
                        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                            <select id="network-paper-select" class="filter-select" style="width: 100%; font-size: 0.775rem; padding: 0.35rem 0.5rem;" onchange="highlightPaperAuthors()">
                                <option value="">-- All Papers --</option>
                            </select>
                        </div>

                        <div class="sidebar-title">Name Visibility</div>
                        <div style="display: flex; flex-direction: column; gap: 0.4rem;">
                            <div style="display: flex; justify-content: space-between; font-size: 0.725rem; color: var(--text-muted);">
                                <span>Show more names</span>
                                <span>Show key hubs</span>
                            </div>
                            <input type="range" id="network-threshold-slider" min="2" max="15" value="10" class="slider" oninput="updateNameThreshold()">
                            <div style="font-size: 0.725rem; text-align: center; color: var(--text-muted);">
                                Threshold: <span id="threshold-val">10</span>px
                            </div>
                        </div>

                        <div class="sidebar-title">Geographic Legend</div>
                        <div class="legend-list" id="country-legend" style="margin-bottom: 1.5rem;"></div>

                        <div class="sidebar-title">Export Graph Data</div>
                        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                            <div style="font-size: 0.725rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Co-authorship Network</div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem;">
                                <a href="dvp_coauthorship_nodes.csv" download class="btn-download" style="font-size: 0.7rem; padding: 0.35rem 0.5rem; justify-content: center;">Nodes CSV</a>
                                <a href="dvp_coauthorship_edges.csv" download class="btn-download" style="font-size: 0.7rem; padding: 0.35rem 0.5rem; justify-content: center;">Edges CSV</a>
                            </div>
                            <a href="dvp_coauthorship_network.graphml" download class="btn-download" style="font-size: 0.7rem; padding: 0.35rem 0.5rem; justify-content: center;">Download GraphML</a>
                            
                            <div style="font-size: 0.725rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-top: 0.4rem;">Bipartite Network</div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem;">
                                <a href="dvp_bipartite_nodes.csv" download class="btn-download" style="font-size: 0.7rem; padding: 0.35rem 0.5rem; justify-content: center;">Nodes CSV</a>
                                <a href="dvp_bipartite_edges.csv" download class="btn-download" style="font-size: 0.7rem; padding: 0.35rem 0.5rem; justify-content: center;">Edges CSV</a>
                            </div>
                            <a href="dvp_bipartite_network.graphml" download class="btn-download" style="font-size: 0.7rem; padding: 0.35rem 0.5rem; justify-content: center;">Bipartite GraphML</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 5: PUBLICATIONS DIRECTORY -->
    <div id="tab-publications" class="tab-content">
        <div class="card col-12">
            <div class="card-title">Directory of Enriched DVP Publications</div>
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; flex-wrap: wrap; gap: 0.75rem; border-bottom: 1px solid var(--border-color); padding-bottom: 1rem;">
                <div style="font-size: 0.85rem; color: var(--text-muted);">
                    Explore the complete curated DVP publications dataset. You can also download the raw structured databases:
                </div>
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <a href="deep_visual_proteomics_papers.csv" download class="btn-download" style="font-size: 0.75rem; padding: 0.4rem 0.75rem;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                        Papers CSV
                    </a>
                    <a href="dvp_authors.csv" download class="btn-download" style="font-size: 0.75rem; padding: 0.4rem 0.75rem;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                        Authors CSV
                    </a>
                    <a href="dvp_keywords.csv" download class="btn-download" style="font-size: 0.75rem; padding: 0.4rem 0.75rem;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                        Keywords CSV
                    </a>
                </div>
            </div>
            
            <div class="table-controls">
                <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
                    <input type="text" class="search-input" id="tableSearch" placeholder="Search by title, author, journal..." onkeyup="filterTable()">
                </div>
                <div>
                    <span style="font-size: 0.85rem; color: var(--text-muted); margin-right: 0.5rem; font-weight: 500;">Sort by:</span>
                    <select class="filter-select" id="tableSort" onchange="sortPapers()">
                        <option value="year-desc">Year (Newest)</option>
                        <option value="year-asc">Year (Oldest)</option>
                        <option value="citations-desc">Citations (Highest)</option>
                        <option value="title-asc">Title (A-Z)</option>
                    </select>
                </div>
            </div>

            <div class="papers-table-wrapper">
                <table id="papersTable">
                    <thead>
                        <tr>
                            <th>PMID</th>
                            <th>Year</th>
                            <th>Title & Authors</th>
                            <th>Journal</th>
                            <th style="cursor: pointer;" onclick="document.getElementById('tableSort').value='citations-desc'; sortPapers();">Citations ▼</th>
                            <th>Links</th>
                        </tr>
                    </thead>
                    <tbody id="papersTableBody">
                        <!-- Filled by JS -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<script>
    // Embedded Data injected by Python
    const dbData = {data_json};

    // Load High-Level Metrics
    // Load High-Level Metrics (automatically calculated via drawLollipopTimeline)

    // Navigation logic
    function switchTab(tabId) {{
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        
        document.getElementById(tabId).classList.add('active');
        event.currentTarget.classList.add('active');

        // Draw network graph / timeline if the tab becomes active
        if (tabId === 'tab-network') {{
            drawNetworkGraph();
        }}
        if (tabId === 'tab-overview') {{
            drawBarTimeline();
        }}
    }}

    // --- Timeline Bar SVG Chart (Interactive & Merged) ---
    function drawBarTimeline() {{
        const container = document.getElementById('timeline-container');
        const width = container.clientWidth || 1000;
        const paddingTop = 70;
        const paddingBottom = 70;
        const axisX = 85; // baseline for the bars (left edge)
        const rowHeight = 36; // vertical spacing per paper row
        
        // Sort papers chronologically (earliest to newest)
        let papers = [...dbData.papers].sort((a, b) => {{
            if (a.year !== b.year) return parseInt(a.year) - parseInt(b.year);
            return b.citations - a.citations;
        }});
        
        // Filter based on preprint toggle
        const includePreprintsToggle = document.getElementById('include-preprints-toggle');
        const includePreprints = includePreprintsToggle ? includePreprintsToggle.checked : false;
        if (!includePreprints) {{
            papers = papers.filter(p => !isNaN(Number(p.pmid)) && !p.pmid.startsWith('PPR'));
        }}
        
        // Update stats metrics dynamically!
        if (dbData.authorsList) {{
            const filteredPmids = new Set(papers.map(p => p.pmid));
            const filteredAuthors = dbData.authorsList.filter(a => filteredPmids.has(String(a.PMID)));
            
            document.getElementById('metric-papers').innerText = papers.length;
            
            const totalCitations = papers.reduce((sum, p) => sum + p.citations, 0);
            document.getElementById('metric-citations').innerText = totalCitations.toLocaleString();
            
            const uniqueResearchers = new Set(filteredAuthors.map(a => a['Author Name'])).size;
            document.getElementById('metric-authors').innerText = uniqueResearchers;
            
            const uniqueJournals = new Set(papers.map(p => p.journal)).size;
            document.getElementById('metric-journals').innerText = uniqueJournals;
            
            const uniqueCountries = new Set(filteredAuthors.map(a => a['Country']).filter(c => c && c !== 'Unknown')).size;
            document.getElementById('metric-countries').innerText = uniqueCountries;
        }}
        
        const count = papers.length;
        const height = paddingTop + paddingBottom + (count * rowHeight);
        
        let svgContent = `<svg width="100%" height="${{height}}" viewBox="0 0 ${{width}} ${{height}}" xmlns="http://www.w3.org/2000/svg">`;
        
        // Glow filter
        svgContent += `
            <defs>
                <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="3" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
            </defs>
        `;
        
        const maxCitations = Math.max(...papers.map(p => p.citations), 1);
        const maxBarWidth = width - axisX - 60;
        
        function getBarWidth(citations) {{
            const minW = 20; // Minimum width to remain hoverable/visible
            const ratio = Math.sqrt(citations) / Math.sqrt(maxCitations);
            return minW + ratio * (maxBarWidth - minW);
        }}
        
        // Ticks calculations (Square-root scale aligned)
        let ticks = [0];
        if (maxCitations > 100) {{
            ticks = [0, 5, 15, 30, 60, 100, Math.round(maxCitations)];
        }} else if (maxCitations > 50) {{
            ticks = [0, 5, 10, 20, 35, 50, Math.round(maxCitations)];
        }} else {{
            ticks = [0, 2, 5, 10, 15, 25, Math.round(maxCitations)];
        }}
        
        // Draw grid lines and x-axis ticks at top and bottom
        ticks.forEach(t => {{
            const xPos = axisX + getBarWidth(t);
            // Vertical dashed grid line
            svgContent += `
                <line x1="${{xPos}}" y1="${{paddingTop - 10}}" x2="${{xPos}}" y2="${{height - paddingBottom + 10}}" 
                      stroke="#1e293b" stroke-dasharray="3,3" stroke-width="1.5" />
            `;
            // Top tick text and tick line
            svgContent += `
                <text x="${{xPos}}" y="${{paddingTop - 24}}" fill="#94a3b8" font-size="10" font-weight="600" text-anchor="middle">
                    ${{t}}
                </text>
                <line x1="${{xPos}}" y1="${{paddingTop - 15}}" x2="${{xPos}}" y2="${{paddingTop - 10}}" stroke="#475569" stroke-width="1.5" />
            `;
            // Bottom tick text and tick line
            svgContent += `
                <text x="${{xPos}}" y="${{height - paddingBottom + 27}}" fill="#94a3b8" font-size="10" font-weight="600" text-anchor="middle">
                    ${{t}}
                </text>
                <line x1="${{xPos}}" y1="${{height - paddingBottom + 10}}" x2="${{xPos}}" y2="${{height - paddingBottom + 15}}" stroke="#475569" stroke-width="1.5" />
            `;
        }});
        
        // Axis Title Labels
        svgContent += `
            <text x="${{axisX - 18}}" y="${{paddingTop - 24}}" fill="#cbd5e1" font-size="10" font-weight="700" text-anchor="end">Citations:</text>
            <text x="${{axisX - 18}}" y="${{height - paddingBottom + 27}}" fill="#cbd5e1" font-size="10" font-weight="700" text-anchor="end">Citations:</text>
        `;
        
        // Top and Bottom Horizontal Axis Lines
        svgContent += `<line x1="${{axisX}}" y1="${{paddingTop - 10}}" x2="${{axisX + maxBarWidth}}" y2="${{paddingTop - 10}}" stroke="#475569" stroke-width="2" />`;
        svgContent += `<line x1="${{axisX}}" y1="${{height - paddingBottom + 10}}" x2="${{axisX + maxBarWidth}}" y2="${{height - paddingBottom + 10}}" stroke="#475569" stroke-width="2" />`;
        
        // Vertical axis line
        svgContent += `<line x1="${{axisX}}" y1="${{paddingTop - 10}}" x2="${{axisX}}" y2="${{height - paddingBottom + 10}}" stroke="#475569" stroke-width="2" />`;
        
        papers.forEach((p, idx) => {{
            const y = paddingTop + 15 + idx * rowHeight;
            const barHeight = 24;
            const barWidth = getBarWidth(p.citations);
            
            const isPreprint = isNaN(Number(p.pmid)) || p.pmid.startsWith('PPR');
            const color = isPreprint ? "#a855f7" : "#3b82f6";
            
            // Render the horizontal bar
            svgContent += `
                <rect id="bar-${{p.pmid}}" x="${{axisX}}" y="${{y}}" width="${{barWidth}}" height="${{barHeight}}" 
                      fill="${{color}}" fill-opacity="0.85" rx="3" ry="3" class="timeline-bar" style="cursor: pointer;"
                      onmouseover="showTimelineTooltip(event, '${{p.pmid}}')" 
                      onmouseout="hideTimelineTooltip()"
                      onclick="window.open(isNaN(Number('${{p.pmid}}')) ? 'https://doi.org/${{p.doi}}' : 'https://pubmed.ncbi.nlm.nih.gov/${{p.pmid}}/', '_blank')" />
            `;
            
            // Text Label: horizontal, inside or outside based on bar width
            const isLongEnough = barWidth >= 140;
            const textX = isLongEnough ? (axisX + 12) : (axisX + barWidth + 10);
            const textColor = isLongEnough ? "#ffffff" : "#cbd5e1";
            
            svgContent += `
                <text x="${{textX}}" y="${{y + barHeight / 2}}" fill="${{textColor}}" font-size="11" font-weight="600"
                      text-anchor="start" dominant-baseline="central"
                      style="cursor: pointer; pointer-events: none; letter-spacing: 0.02em;">
                    ${{p.citationLabel}}
                </text>
            `;
            
            // Year ticks on the left
            const showYear = idx === 0 || papers[idx - 1].year !== p.year;
            if (showYear) {{
                svgContent += `
                    <circle cx="${{axisX}}" cy="${{y + barHeight / 2}}" r="3.5" fill="#475569" />
                    <text x="${{axisX - 16}}" y="${{y + barHeight / 2}}" fill="#94a3b8" font-size="12" font-weight="700" text-anchor="end" dominant-baseline="central">
                        ${{p.year}}
                    </text>
                `;
            }}
        }});
        
        svgContent += `</svg>`;
        container.innerHTML = svgContent;
    }}

    // Timeline tooltip logic
    function showTimelineTooltip(event, pmid) {{
        const p = dbData.papers.find(x => x.pmid === pmid);
        const tooltip = document.getElementById('timeline-tooltip');
        const container = document.getElementById('timeline-container');
        
        // Highlight elements
        const bar = document.getElementById(`bar-${{pmid}}`);
        if (bar) {{
            bar.setAttribute('fill-opacity', '1.0');
            bar.setAttribute('stroke', '#ffffff');
            bar.setAttribute('stroke-width', '1.5');
        }}
        
        let preprintInfo = '';
        if (p.preprintPmid) {{
            preprintInfo = `<br><span style="color:#60a5fa; font-weight:600; font-size:0.75rem;">Includes Preprint (PMID: ${{p.preprintPmid}})</span>`;
        }} else if (p.preprintDoi) {{
            preprintInfo = `<br><span style="color:#60a5fa; font-weight:600; font-size:0.75rem;">Includes Preprint (DOI: ${{p.preprintDoi}})</span>`;
        }}
        
        tooltip.innerHTML = `
            <div style="font-weight: 700; color: #f8fafc; font-size: 0.85rem; margin-bottom: 0.25rem;">${{p.title}}</div>
            <div style="color: #94a3b8; font-size: 0.75rem; margin-bottom: 0.5rem; font-style: italic;">${{p.authors}}</div>
            <div style="display: flex; gap: 0.75rem; font-size: 0.75rem;">
                <span>Journal: <strong style="color: #e2e8f0;">${{p.journal}}</strong></span>
                <span>Citations: <strong style="color: #fef08a;">${{p.citations}}</strong></span>
            </div>
            ${{preprintInfo}}
        `;
        
        tooltip.style.display = 'block';
        const rect = container.getBoundingClientRect();
        tooltip.style.left = (event.clientX - rect.left + 15) + 'px';
        tooltip.style.top = (event.clientY - rect.top - 20) + 'px';
    }}

    function hideTimelineTooltip() {{
        const tooltip = document.getElementById('timeline-tooltip');
        tooltip.style.display = 'none';
        
        dbData.papers.forEach(p => {{
            const bar = document.getElementById(`bar-${{p.pmid}}`);
            if (bar) {{
                bar.setAttribute('fill-opacity', '0.85');
                bar.removeAttribute('stroke');
                bar.removeAttribute('stroke-width');
            }}
        }});
    }}

    window.addEventListener('resize', drawBarTimeline);

    // --- Charts Configurations ---
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = 'Inter';


    // 3. Journals Chart (Horizontal Bar)
    new Chart(document.getElementById('journalsChart').getContext('2d'), {{
        type: 'bar',
        data: {{
            labels: dbData.journals.labels.map(l => l.length > 30 ? l.substring(0, 27) + '...' : l),
            datasets: [{{
                label: 'Publications count',
                data: dbData.journals.values,
                backgroundColor: '#3b82f6',
                borderRadius: 4
            }}]
        }},
        options: {{
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {{
                x: {{ grid: {{ color: '#334155' }}, ticks: {{ stepSize: 1 }} }},
                y: {{ grid: {{ display: false }} }}
            }},
            plugins: {{ legend: {{ display: false }} }}
        }}
    }});

    // 4. Countries Chart (Horizontal Bar)
    new Chart(document.getElementById('countriesChart').getContext('2d'), {{
        type: 'bar',
        data: {{
            labels: dbData.countries.labels,
            datasets: [{{
                label: 'Publications involved',
                data: dbData.countries.values,
                backgroundColor: '#ef4444',
                borderRadius: 4
            }}]
        }},
        options: {{
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {{
                x: {{ grid: {{ color: '#334155' }}, ticks: {{ stepSize: 1 }} }},
                y: {{ grid: {{ display: false }} }}
            }},
            plugins: {{ legend: {{ display: false }} }}
        }}
    }});

    // 5. Institutions Chart (Horizontal Bar)
    new Chart(document.getElementById('institutionsChart').getContext('2d'), {{
        type: 'bar',
        data: {{
            labels: dbData.institutions.labels.map(l => l.length > 40 ? l.substring(0, 37) + '...' : l),
            datasets: [{{
                label: 'Publications involved',
                data: dbData.institutions.values,
                backgroundColor: '#10b981',
                borderRadius: 4
            }}]
        }},
        options: {{
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {{
                x: {{ grid: {{ color: '#334155' }}, ticks: {{ stepSize: 1 }} }},
                y: {{ grid: {{ display: false }} }}
            }},
            plugins: {{ legend: {{ display: false }} }}
        }}
    }});


    // --- Tab 4: vis.js Collaborator Network Graph ---
    // --- Tab 4: vis.js Collaborator Network Graph ---
    let networkInitialized = false;
    let network = null;
    let networkNodesDataSet = null;
    let networkEdgesDataSet = null;
    let networkEdges = [];

    function drawNetworkGraph() {{
        if (networkInitialized) return;
        
        const container = document.getElementById('network-container');
        
        // Setup legend
        const legendDiv = document.getElementById('country-legend');
        legendDiv.innerHTML = '';
        for (const [country, color] of Object.entries(dbData.countryColors)) {{
            if (country === 'Unknown') continue;
            legendDiv.innerHTML += `
                <div class="legend-item">
                    <span class="legend-color" style="background-color: ${{color}};"></span>
                    <span>${{country}}</span>
                </div>
            `;
        }}
        legendDiv.innerHTML += `
            <div class="legend-item">
                <span class="legend-color" style="background-color: ${{dbData.countryColors.Unknown}};"></span>
                <span>Unknown / Other</span>
            </div>
        `;

        // Setup paper selector options
        const paperSelect = document.getElementById('network-paper-select');
        if (paperSelect && paperSelect.options.length <= 1) {{
            // Sort papers by year descending, then title
            let sortedPapers = [...dbData.papers].sort((a, b) => b.year - a.year);
            sortedPapers.forEach(p => {{
                const opt = document.createElement('option');
                opt.value = p.pmid;
                // Truncate title for dropdown if too long
                const displayTitle = p.title.length > 55 ? p.title.substring(0, 52) + '...' : p.title;
                opt.textContent = `${{p.year}} - ${{p.citationLabel.split(' ')[0]}} : ${{displayTitle}}`;
                paperSelect.appendChild(opt);
            }});
        }}

        // Add standard edge IDs for styling manipulation
        const edgeData = dbData.network.edges.map(e => ({{
            id: `${{e.from}}-${{e.to}}`,
            from: e.from,
            to: e.to,
            value: e.value,
            title: e.title
        }}));
        networkEdges = edgeData;

        networkNodesDataSet = new vis.DataSet(dbData.network.nodes);
        networkEdgesDataSet = new vis.DataSet(edgeData);

        const data = {{
            nodes: networkNodesDataSet,
            edges: networkEdgesDataSet
        }};

        const options = {{
            nodes: {{
                shape: 'dot',
                scaling: {{
                    min: 6,
                    max: 30,
                    label: {{
                        min: 8,
                        max: 20,
                        drawThreshold: 10,
                        maxVisible: 20
                    }}
                }},
                font: {{
                    face: 'Inter',
                    color: '#f8fafc',
                    strokeWidth: 2,
                    strokeColor: '#0f172a'
                }}
            }},
            edges: {{
                width: 1,
                color: {{ color: '#475569', highlight: '#3b82f6', hover: '#3b82f6' }},
                smooth: {{ type: 'continuous' }}
            }},
            physics: {{
                forceAtlas2Based: {{
                    gravitationalConstant: -100,
                    centralGravity: 0.01,
                    springLength: 240,
                    springConstant: 0.08
                }},
                maxVelocity: 50,
                solver: 'forceAtlas2Based',
                timestep: 0.35,
                stabilization: {{
                    iterations: 150,
                    updateInterval: 25
                }}
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 200,
                hideEdgesOnDrag: true
            }}
        }};

        network = new vis.Network(container, data, options);
        
        network.on("stabilizationFinished", function () {{
            network.setOptions({{ physics: false }});
        }});
        
        // Hard stop physics after 2 seconds to guarantee it freezes
        setTimeout(() => {{
            network.setOptions({{ physics: false }});
        }}, 2000);
        
        networkInitialized = true;
    }}

    function highlightPaperAuthors() {{
        if (!network || !networkNodesDataSet || !networkEdgesDataSet) return;
        
        const selectedPmid = document.getElementById('network-paper-select').value;
        const allNodes = dbData.network.nodes;
        
        if (!selectedPmid) {{
            // Reset nodes
            const resetNodes = allNodes.map(node => {{
                const countryInfo = dbData.authorsList.find(a => a['Author Name'] === node.id);
                const country = countryInfo ? countryInfo.Country : 'Unknown';
                const defaultColor = dbData.countryColors[country] || dbData.countryColors.Unknown;
                return {{
                    id: node.id,
                    color: {{
                        background: defaultColor,
                        border: "#0f172a"
                    }},
                    font: {{ color: '#f8fafc' }}
                }};
            }});
            const resetEdges = networkEdges.map(e => ({{
                id: e.id,
                color: {{ color: '#475569', opacity: 1.0 }}
            }}));
            networkNodesDataSet.update(resetNodes);
            networkEdgesDataSet.update(resetEdges);
            network.unselectNodes();
            return;
        }}
        
        const paperAuthors = new Set(dbData.authorsList.filter(a => String(a.PMID) === selectedPmid).map(a => a['Author Name']));
        
        const updatedNodes = allNodes.map(node => {{
            const isAssociated = paperAuthors.has(node.id);
            const countryInfo = dbData.authorsList.find(a => a['Author Name'] === node.id);
            const country = countryInfo ? countryInfo.Country : 'Unknown';
            const defaultColor = dbData.countryColors[country] || dbData.countryColors.Unknown;
            
            return {{
                id: node.id,
                color: {{
                    background: isAssociated ? defaultColor : '#1e293b',
                    border: isAssociated ? '#ffffff' : '#0f172a'
                }},
                font: {{
                    color: isAssociated ? '#f8fafc' : '#475569'
                }}
            }};
        }});
        networkNodesDataSet.update(updatedNodes);
        
        const updatedEdges = networkEdges.map(e => {{
            const active = paperAuthors.has(e.from) && paperAuthors.has(e.to);
            return {{
                id: e.id,
                color: {{
                    color: active ? '#3b82f6' : '#1e293b',
                    opacity: active ? 1.0 : 0.03
                }}
            }};
        }});
        networkEdgesDataSet.update(updatedEdges);
        
        network.selectNodes(Array.from(paperAuthors));
    }}

    function updateNameThreshold() {{
        if (!network) return;
        const val = parseInt(document.getElementById('network-threshold-slider').value);
        document.getElementById('threshold-val').innerText = val;
        network.setOptions({{
            nodes: {{
                scaling: {{
                    label: {{
                        drawThreshold: val
                    }}
                }}
            }}
        }});
    }}

    // --- Tab 5: Publications Directory List & Sorting ---
    const tableBody = document.getElementById('papersTableBody');
    
    function renderTable() {{
        tableBody.innerHTML = '';
        dbData.papers.forEach(p => {{
            const doiLink = p.doi ? `<a href="https://doi.org/${{p.doi}}" class="external-link" target="_blank">DOI</a>` : '-';
            
            let preprintInfo = '';
            if (p.preprintPmid) {{
                preprintInfo = `<div style="color: #60a5fa; font-size: 0.75rem; font-weight:600; margin-top:0.25rem;">Includes Preprint (PMID: <a href="https://pubmed.ncbi.nlm.nih.gov/${{p.preprintPmid}}/" class="external-link" target="_blank">${{p.preprintPmid}}</a>)</div>`;
            }} else if (p.preprintDoi) {{
                preprintInfo = `<div style="color: #60a5fa; font-size: 0.75rem; font-weight:600; margin-top:0.25rem;">Includes Preprint (DOI: <a href="https://doi.org/${{p.preprintDoi}}" class="external-link" target="_blank">${{p.preprintDoi}}</a>)</div>`;
            }}

            const pmidCol = isNaN(Number(p.pmid)) ? 'Preprint' : `<a href="https://pubmed.ncbi.nlm.nih.gov/${{p.pmid}}/" class="external-link" target="_blank">${{p.pmid}}</a>`;
            
            let linksHtml = '';
            if (!isNaN(Number(p.pmid))) {{
                linksHtml += `<a href="https://pubmed.ncbi.nlm.nih.gov/${{p.pmid}}/" class="external-link" target="_blank">PubMed</a>`;
            }}
            if (p.doi) {{
                if (linksHtml) {{
                    linksHtml += '<br>';
                }}
                linksHtml += `<a href="https://doi.org/${{p.doi}}" class="external-link" target="_blank">DOI</a>`;
            }}
            if (!linksHtml) {{
                linksHtml = '-';
            }}
            
            tableBody.innerHTML += `
                <tr id="row-${{p.pmid}}">
                    <td style="font-weight: 500;">
                        ${{pmidCol}}
                    </td>
                    <td>${{p.year}}</td>
                    <td>
                        <div style="font-weight: 600; color: #f8fafc; font-size: 0.95rem; margin-bottom: 0.25rem;">${{p.title}}</div>
                        <div style="color: var(--text-muted); font-size: 0.825rem; font-style: italic;">${{p.authors}}</div>
                        ${{preprintInfo}}
                        <div class="abstract-truncate" onclick="toggleAbstract('${{p.pmid}}')">▶ View Abstract</div>
                        <div class="abstract-full" id="abs-${{p.pmid}}">${{p.abstract}}</div>
                    </td>
                    <td style="font-size: 0.85rem; color: #e2e8f0; font-weight: 500;">${{p.journal}}</td>
                    <td style="font-weight: 700; color: #fef08a; font-size: 0.95rem;">${{p.citations}}</td>
                    <td>
                        <div style="display: flex; flex-direction: column; gap: 0.25rem;">
                            ${{linksHtml}}
                        </div>
                    </td>
                </tr>
            `;
        }});
    }}

    function toggleAbstract(pmid) {{
        const el = document.getElementById(`abs-${{pmid}}`);
        const trigger = el.previousElementSibling;
        if (el.style.display === 'block') {{
            el.style.display = 'none';
            trigger.innerText = '▶ View Abstract';
        }} else {{
            el.style.display = 'block';
            trigger.innerText = '▼ Hide Abstract';
        }}
    }}

    function filterTable() {{
        const searchVal = document.getElementById('tableSearch').value.toLowerCase();
        
        dbData.papers.forEach(p => {{
            const row = document.getElementById(`row-${{p.pmid}}`);
            const titleMatch = p.title.toLowerCase().includes(searchVal);
            const authorMatch = p.authors.toLowerCase().includes(searchVal);
            const journalMatch = p.journal.toLowerCase().includes(searchVal);
            const pmidMatch = p.pmid.includes(searchVal);
            const searchMatch = titleMatch || authorMatch || journalMatch || pmidMatch;

            if (searchMatch) {{
                row.style.display = '';
            }} else {{
                row.style.display = 'none';
            }}
        }});
    }}

    function sortPapers() {{
        const sortVal = document.getElementById('tableSort').value;
        
        dbData.papers.sort((a, b) => {{
            if (sortVal === 'year-desc') {{
                return parseInt(b.year) - parseInt(a.year);
            }} else if (sortVal === 'year-asc') {{
                return parseInt(a.year) - parseInt(b.year);
            }} else if (sortVal === 'citations-desc') {{
                return b.citations - a.citations;
            }} else if (sortVal === 'title-asc') {{
                return a.title.localeCompare(b.title);
            }}
            return 0;
        }});
        
        renderTable();
        filterTable(); // Keep the current search filter active
    }}

    // Initial render & Draw Timeline
    renderTable();
    drawBarTimeline();
</script>

</body>
</html>
"""

    with open("dvp_dashboard.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Dashboard saved to 'dvp_dashboard.html'")

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Dashboard saved to 'index.html' (for GitHub Pages)")

if __name__ == "__main__":
    generate_dashboard()
