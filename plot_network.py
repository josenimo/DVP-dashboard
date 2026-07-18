#!/usr/bin/env python
"""
DVP Collaborator & Bipartite Network Analysis and Plotting Tutorial
-------------------------------------------------------------------
This script demonstrates how to load the exported DVP collaborator datasets 
(one-mode co-authorship and bipartite author-paper networks) using NetworkX,
perform network analysis (centrality, degree distribution), and generate
beautiful plots using Matplotlib and Seaborn.

Requirements:
    pip install networkx pandas matplotlib seaborn
"""

import os
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
import seaborn as sns

# Set style for plotting
sns.set_theme(style="whitegrid")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "Inter", "DejaVu Sans"]

def analyze_one_mode_coauthorship():
    print("=== 1. Analyzing One-Mode Co-authorship Network ===")
    
    # Paths to files
    nodes_file = "dvp_coauthorship_nodes.csv"
    edges_file = "dvp_coauthorship_edges.csv"
    
    if not (os.path.exists(nodes_file) and os.path.exists(edges_file)):
        print(f"Error: Required files '{nodes_file}' and '{edges_file}' not found.")
        print("Please run the scraper pipeline first (e.g. 'python main.py') to generate them.\n")
        return
        
    # Load nodes and edges DataFrames
    nodes_df = pd.read_csv(nodes_file)
    edges_df = pd.read_csv(edges_file)
    
    # Initialize NetworkX Graph
    G = nx.Graph()
    
    # Add nodes with attributes
    for _, row in nodes_df.iterrows():
        G.add_node(
            row["Id"],
            label=row["Label"],
            publications=row["Publications"],
            country=row["Country"],
            institution=row["Institution"]
        )
        
    # Add edges with weights
    for _, row in edges_df.iterrows():
        G.add_edge(
            row["Source"],
            row["Target"],
            weight=row["Weight"]
        )
        
    print(f"Graph loaded successfully.")
    print(f"Number of nodes (researchers): {G.number_of_nodes()}")
    print(f"Number of edges (co-authorship ties): {G.number_of_edges()}")
    
    # Compute Network Metrics
    degree_dict = dict(G.degree())
    degree_cent = nx.degree_centrality(G)
    between_cent = nx.betweenness_centrality(G, weight="weight")
    
    # Add metrics back to nodes DataFrame for easy ranking
    nodes_df["Degree"] = nodes_df["Id"].map(degree_dict).fillna(0).astype(int)
    nodes_df["Degree Centrality"] = nodes_df["Id"].map(degree_cent).fillna(0)
    nodes_df["Betweenness Centrality"] = nodes_df["Id"].map(between_cent).fillna(0)
    
    print("\nTop 5 Researchers by Degree (Number of Collaborators):")
    print(nodes_df.sort_values(by="Degree", ascending=False)[["Id", "Degree", "Publications", "Country"]].head().to_string(index=False))
    
    print("\nTop 5 Researchers by Betweenness Centrality (Collaboration Hubs):")
    print(nodes_df.sort_values(by="Betweenness Centrality", ascending=False)[["Id", "Betweenness Centrality", "Country"]].head().to_string(index=False))
    
    # Plotting the One-Mode Network
    plt.figure(figsize=(12, 10))
    plt.title("DVP Researcher Co-authorship Network", fontsize=16, fontweight="bold", pad=20)
    
    # Position nodes using spring layout
    pos = nx.spring_layout(G, k=0.15, seed=42)
    
    # Filter nodes with degree > 1 for cleaner plotting
    hubs = [node for node, degree in G.degree() if degree > 2]
    subG = G.subgraph(hubs)
    sub_pos = {k: pos[k] for k in subG.nodes()}
    
    # Color nodes by country
    unique_countries = nodes_df["Country"].unique()
    palette = sns.color_palette("Set2", len(unique_countries))
    country_color_map = dict(zip(unique_countries, palette))
    node_colors = [country_color_map[G.nodes[n]["country"]] for n in subG.nodes()]
    
    # Node sizes based on publication counts
    node_sizes = [G.nodes[n]["publications"] * 80 for n in subG.nodes()]
    
    # Draw elements
    nx.draw_networkx_nodes(
        subG, 
        sub_pos, 
        node_size=node_sizes, 
        node_color=node_colors, 
        edgecolors="#2c3e50", 
        linewidths=1.2, 
        alpha=0.9
    )
    
    # Draw edges with width relative to weight
    weights = [subG[u][v]["weight"] * 1.5 for u, v in subG.edges()]
    nx.draw_networkx_edges(subG, sub_pos, width=weights, edge_color="#bdc3c7", alpha=0.6)
    
    # Draw labels for top researchers (degree > 5)
    labels = {n: n for n in subG.nodes() if G.degree(n) > 5}
    nx.draw_networkx_labels(subG, sub_pos, labels=labels, font_size=8, font_weight="bold", font_color="#1a252f")
    
    # Create legend manually
    legend_elements = [
        plt.Line2D([0], [0], marker="o", color="w", label=country, markerfacecolor=color, markersize=10, markeredgecolor="#2c3e50")
        for country, color in country_color_map.items() if country in nodes_df[nodes_df["Id"].isin(subG.nodes())]["Country"].unique()
    ]
    plt.legend(handles=legend_elements, loc="upper right", title="Countries", title_fontsize="11", frameon=True, facecolor="white", edgecolor="#e2e8f0")
    
    plt.axis("off")
    plt.tight_layout()
    
    plot_path = "dvp_coauthorship_network_plot.png"
    plt.savefig(plot_path, dpi=300)
    print(f"\nSaved co-authorship plot to '{plot_path}'\n")
    plt.close()

def analyze_bipartite_network():
    print("=== 2. Analyzing Bipartite Author-Paper Network ===")
    
    # Paths to files
    nodes_file = "dvp_bipartite_nodes.csv"
    edges_file = "dvp_bipartite_edges.csv"
    
    if not (os.path.exists(nodes_file) and os.path.exists(edges_file)):
        print(f"Error: Required files '{nodes_file}' and '{edges_file}' not found.\n")
        return
        
    # Load nodes and edges
    nodes_df = pd.read_csv(nodes_file)
    edges_df = pd.read_csv(edges_file)
    
    # Initialize bipartite graph
    B = nx.Graph()
    
    # Add Author nodes (bipartite=0) and Paper nodes (bipartite=1)
    for _, row in nodes_df.iterrows():
        is_author = row["Type"] == "Author"
        B.add_node(
            row["Id"],
            label=row["Label"],
            type=row["Type"],
            bipartite=0 if is_author else 1,
            publications=row["Publications"] if is_author else 0,
            country=row["Country"] if is_author else "",
            institution=row["Institution"] if is_author else "",
            year=row["Year"] if not is_author else 0,
            citations=row["Citations"] if not is_author else 0
        )
        
    # Add edges between authors and papers
    for _, row in edges_df.iterrows():
        B.add_edge(row["Source"], row["Target"], type=row["Type"])
        
    print("Bipartite graph loaded successfully.")
    
    # Check if network is indeed bipartite
    is_bipartite = nx.is_bipartite(B)
    print(f"Is Bipartite: {is_bipartite}")
    
    authors = {n for n, d in B.nodes(data=True) if d["bipartite"] == 0}
    papers = {n for n, d in B.nodes(data=True) if d["bipartite"] == 1}
    
    print(f"Number of Author nodes: {len(authors)}")
    print(f"Number of Paper nodes: {len(papers)}")
    print(f"Number of Author-Paper connections: {B.number_of_edges()}")
    
    # Bipartite degree centrality
    # (normalized by the number of nodes in the other partition)
    degree_cent = nx.bipartite.degree_centrality(B, authors)
    
    nodes_df["Bipartite Degree Centrality"] = nodes_df["Id"].map(degree_cent)
    
    print("\nTop 5 Researchers by Bipartite Degree Centrality (Co-authored the most papers):")
    print(nodes_df[nodes_df["Type"] == "Author"].sort_values(by="Bipartite Degree Centrality", ascending=False)[["Id", "Bipartite Degree Centrality", "Country"]].head().to_string(index=False))
    
    print("\nTop 5 Papers by Bipartite Degree (Papers with the most co-authors):")
    print(nodes_df[nodes_df["Type"] == "Paper"].sort_values(by="Publications", ascending=False)[["Id", "Label", "Year"]].head().to_string(index=False))

    # Project Bipartite Graph to Author one-mode network (alternative to what we did in visualize.py)
    # This proves that our bipartite graph holds the necessary data to compute one-mode projections
    print("\nProjecting Bipartite Graph to Author one-mode network using NetworkX...")
    author_projection = nx.bipartite.projected_graph(B, authors)
    print(f"Projected author nodes: {author_projection.number_of_nodes()}")
    print(f"Projected author edges (collaboration connections): {author_projection.number_of_edges()}")
    
    # Plotting Bipartite Graph (sub-network for visual clarity)
    # We will plot top papers and their co-authors
    plt.figure(figsize=(14, 10))
    plt.title("Bipartite Network Layout: Top Curated DVP Papers & Authors", fontsize=16, fontweight="bold", pad=20)
    
    # Select top 5 papers by citation count, and get their authors
    top_papers = nodes_df[nodes_df["Type"] == "Paper"].sort_values(by="Citations", ascending=False).head(5)["Id"].tolist()
    sub_nodes = set(top_papers)
    for p in top_papers:
        sub_nodes.update(B.neighbors(p))
        
    subB = B.subgraph(sub_nodes)
    
    # Layout bipartite graph with two columns
    sub_authors = {n for n, d in subB.nodes(data=True) if d["bipartite"] == 0}
    sub_papers = {n for n, d in subB.nodes(data=True) if d["bipartite"] == 1}
    
    pos = nx.bipartite_layout(subB, sub_authors, align="vertical")
    
    # Shift paper nodes right and author nodes left to create columns
    # and add labels
    node_colors = ["#3b82f6" if subB.nodes[n]["bipartite"] == 0 else "#eab308" for n in subB.nodes()]
    node_sizes = [150 if subB.nodes[n]["bipartite"] == 0 else 600 for n in subB.nodes()]
    
    nx.draw_networkx_nodes(
        subB, 
        pos, 
        node_size=node_sizes, 
        node_color=node_colors, 
        edgecolors="#2c3e50", 
        linewidths=1.2, 
        alpha=0.9
    )
    
    nx.draw_networkx_edges(subB, pos, width=1.0, edge_color="#bdc3c7", alpha=0.5)
    
    # Label layout: offset text for clarity
    label_pos = {}
    for node, (x, y) in pos.items():
        if x < 0: # Author column
            label_pos[node] = (x - 0.08, y)
        else: # Paper column
            label_pos[node] = (x + 0.08, y)
            
    # For authors, use their name. For papers, truncate title for visual space.
    labels = {}
    for n in subB.nodes():
        if subB.nodes[n]["bipartite"] == 0:
            labels[n] = n
        else:
            title = subB.nodes[n]["label"]
            labels[n] = (title[:30] + "...") if len(title) > 30 else title
            
    nx.draw_networkx_labels(subB, label_pos, labels=labels, font_size=8, font_color="#1a252f")
    
    # Custom partition legends
    plt.Line2D([0], [0], marker="o", color="w", label="Author", markerfacecolor="#3b82f6", markersize=12)
    plt.legend(
        handles=[
            plt.Line2D([0], [0], marker="o", color="w", label="Author Nodes", markerfacecolor="#3b82f6", markersize=10, markeredgecolor="#2c3e50"),
            plt.Line2D([0], [0], marker="o", color="w", label="Paper Nodes", markerfacecolor="#eab308", markersize=12, markeredgecolor="#2c3e50")
        ], 
        loc="upper center", 
        bbox_to_anchor=(0.5, -0.05),
        ncol=2, 
        frameon=True, 
        facecolor="white", 
        edgecolor="#e2e8f0"
    )
    
    plt.axis("off")
    plt.xlim(-1.5, 1.5) # Expand x limits to fit labels
    plt.tight_layout()
    
    bipartite_plot_path = "dvp_bipartite_network_plot.png"
    plt.savefig(bipartite_plot_path, dpi=300)
    print(f"Saved bipartite plot to '{bipartite_plot_path}'\n")
    plt.close()

if __name__ == "__main__":
    analyze_one_mode_coauthorship()
    analyze_bipartite_network()
    print("Analysis finished successfully!")
