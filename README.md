# Deep Visual Proteomics (DVP) Analytics Pipeline & Dashboard

This repository contains the data scraping pipeline, structured databases, and interactive analytics dashboard for publications related to **Deep Visual Proteomics (DVP)**. 

The dashboard is automatically published via GitHub Pages at:
**[https://josenimo.github.io/DVP-dashboard/](https://josenimo.github.io/DVP-dashboard/)**

---

## Features

1. **Curated DVP Publication Database**: Fetched and enriched in real-time from the **Europe PMC API** (capturing both PubMed peer-reviewed papers and bioRxiv/medRxiv preprints).
2. **Preprint Deduplication & Record Anchoring**: Smart deduplication (using fuzzy string matching on titles/abstracts and citation cross-referencing) automatically links preprints to their peer-reviewed counterparts as soon as they are published.
3. **Interactive Analytics Dashboard (`index.html`)**:
   - **Preprint Toggle**: Client-side switch to dynamically include or exclude preprints across all metrics, charts, and timelines.
   - **Publications Timeline**: Perpendicular lollipop timeline showing publications by year.
   - **Publication Directory**: Fully searchable and filterable directory with expandable abstract drawers and direct links (DOI, PubMed, bioRxiv).
   - **Collaborator & Bipartite Networks**: Interactive network graphs of researcher collaborations.
4. **Data Download & Export Center**:
   - Download the curated publications, authors, and keywords databases directly from the dashboard as CSVs.
   - Export one-mode co-authorship and bipartite author-paper network data in **CSV** and standard **GraphML** formats (compatible with Gephi, Cytoscape, and NetworkX).
5. **Python Network Analysis Tutorial**:
   - Standalone script `plot_network.py` showing how to load the network data in Python, calculate metrics, and plot the graphs.

---

## Repository Structure

- `main.py`: Core pipeline orchestration script (scraping, fuzzy deduplication, database CSV generation).
- `visualize.py`: Generates the interactive HTML dashboard (`index.html`) and exports the network datasets.
- `plot_network.py`: Tutorial script demonstrating how to load and plot the networks in NetworkX.
- `pyproject.toml` / `uv.lock`: Python environment configuration and dependencies managed via `uv`.

### Generated Datasets
- `deep_visual_proteomics_papers.csv`: Cleaned metadata for all matched DVP publications.
- `dvp_authors.csv`: Author names, order, institutions, and country associations.
- `dvp_keywords.csv`: Extracted biological keywords and topics.
- `dvp_coauthorship_nodes.csv` / `edges.csv` / `.graphml`: One-mode researcher network.
- `dvp_bipartite_nodes.csv` / `edges.csv` / `.graphml`: Bipartite author-paper network.

---

## Getting Started

### Prerequisites

Ensure you have [uv](https://github.com/astral-sh/uv) installed.

### Run the Pipeline

To re-run the scraping pipeline, pull fresh literature records, regenerate the databases, and rebuild the dashboard, run:
```bash
uv run main.py
```

### Run the Network Analysis & Plotting Script

To analyze the exported networks (calculate centralities and save visualization plots), run:
```bash
uv run plot_network.py
```
This generates:
- `dvp_coauthorship_network_plot.png` (Co-authorship visualization)
- `dvp_bipartite_network_plot.png` (Bipartite author-paper visualization)

---

## Loading Network Data in Python (NetworkX Example)

### One-Mode Co-authorship Network
```python
import pandas as pd
import networkx as nx

# Load datasets
nodes_df = pd.read_csv("dvp_coauthorship_nodes.csv")
edges_df = pd.read_csv("dvp_coauthorship_edges.csv")

# Build Graph
G = nx.Graph()
for _, row in nodes_df.iterrows():
    G.add_node(row["Id"], label=row["Label"], publications=row["Publications"], country=row["Country"], institution=row["Institution"])
for _, row in edges_df.iterrows():
    G.add_edge(row["Source"], row["Target"], weight=row["Weight"])
```

### Bipartite Author-Paper Network
```python
# Load bipartite datasets
nodes_df = pd.read_csv("dvp_bipartite_nodes.csv")
edges_df = pd.read_csv("dvp_bipartite_edges.csv")

# Build Bipartite Graph
B = nx.Graph()
for _, row in nodes_df.iterrows():
    is_author = row["Type"] == "Author"
    B.add_node(
        row["Id"],
        type=row["Type"],
        bipartite=0 if is_author else 1,
        publications=row["Publications"] if is_author else 0,
        country=row["Country"] if is_author else "",
        year=row["Year"] if not is_author else 0,
        citations=row["Citations"] if not is_author else 0
    )
for _, row in edges_df.iterrows():
    B.add_edge(row["Source"], row["Target"])
```
