import urllib.request
import json
import urllib.parse
import re
import pandas as pd
import time
import subprocess
from tqdm import tqdm

# Standardized country mapping for author affiliations
COUNTRY_MAPPING = {
    'usa': 'United States',
    'united states': 'United States',
    'united states of america': 'United States',
    'uk': 'United Kingdom',
    'united kingdom': 'United Kingdom',
    'england': 'United Kingdom',
    'scotland': 'United Kingdom',
    'germany': 'Germany',
    'deutschland': 'Germany',
    'denmark': 'Denmark',
    'sweden': 'Sweden',
    'switzerland': 'Switzerland',
    'china': 'China',
    'pr china': 'China',
    'p.r. china': 'China',
    'japan': 'Japan',
    'france': 'France',
    'netherlands': 'Netherlands',
    'norway': 'Norway',
    'italy': 'Italy',
    'spain': 'Spain',
    'canada': 'Canada',
    'australia': 'Australia',
    'singapore': 'Singapore',
    'austria': 'Austria',
    'belgium': 'Belgium',
    'czech republic': 'Czech Republic',
    'czechia': 'Czech Republic',
    'finland': 'Finland',
    'india': 'India',
    'israel': 'Israel',
    'south korea': 'South Korea',
    'korea': 'South Korea',
    'republic of korea': 'South Korea',
}

# Known manual classifications for maximum precision
CLASSIFICATION_OVERRIDES = {
    "35590073": "Methodology",          # Original Nature Biotech paper (2022)
    "37602975": "Workflow Improvement",  # Robust dimethyl-based multiplex-DIA (2023)
    "37683827": "Workflow Improvement",  # Membrane Glass Slides G-HIER (2023)
    "37783884": "Workflow Improvement",  # Spatial single-cell mass spectrometry / scDVP (2023)
    "40536875": "Protocol",              # STAR Protocols tonsil cancer (2025)
    "40027887": "Review",                 # Toward spatial glycomics/glycoproteomics (2025)
    "40360936": "Review",                 # Nature Reviews Gastroenterology AATD (2025)
    "40680990": "Review",                 # Journal of Proteomics perspective (2025)
    "41655216": "Review",                 # Advanced Science spatial proteogenomics review (2026)
}

def clean_affiliation(aff):
    """Removes email addresses, electronic address pointers, and trailing punctuation."""
    aff = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', aff)
    aff = re.sub(r'(?i)\belectronic\s+address\b.*$', '', aff)
    return aff.strip().rstrip('.;:, ')

def parse_country(aff):
    """Extracts and standardizes the country from an affiliation string."""
    cleaned = clean_affiliation(aff).lower()
    parts = [p.strip() for p in cleaned.split(',')]
    
    for part in reversed(parts):
        words = re.findall(r'\b\w+\b', part)
        for i in range(len(words)):
            for length in [3, 2, 1]:
                if i + length <= len(words):
                    phrase = " ".join(words[i:i+length])
                    if phrase in COUNTRY_MAPPING:
                        return COUNTRY_MAPPING[phrase]
    
    for term, standard in COUNTRY_MAPPING.items():
        if re.search(r'\b' + re.escape(term) + r'\b', cleaned):
            return standard
            
    return "Unknown"

def parse_institution(aff):
    """Extracts the main institution name from an affiliation string."""
    cleaned = clean_affiliation(aff)
    parts = [p.strip() for p in cleaned.split(',')]
    
    inst_keywords = ['university', 'univ', 'institute', 'inst', 'center', 'ctr', 'clinic', 'hospital', 'hosp', 'college', 'school', 'academy', 'riken', 'max planck', 'novartis', 'roche']
    
    matching_parts = []
    for part in parts:
        part_lower = part.lower()
        if any(re.search(r'\b' + re.escape(kw) + r'\b', part_lower) for kw in inst_keywords):
            matching_parts.append(part)
            
    if matching_parts:
        return matching_parts[-1]
    
    if len(parts) >= 2:
        return parts[-2] if len(parts) == 2 else parts[-3]
        
    return "Unknown"

def search_europe_pmc(query):
    """Searches Europe PMC using paging to retrieve all relevant publications (including preprints)."""
    encoded_query = urllib.parse.quote(query)
    cursor = "*"
    results = []
    
    print("Querying Europe PMC API for literature records...")
    while True:
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={encoded_query}&resultType=core&cursorMark={cursor}&pageSize=100&format=json"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'AntigravityDVPScraper/1.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            chunk = data.get('resultList', {}).get('result', [])
            if not chunk:
                break
            results.extend(chunk)
            
            next_cursor = data.get('nextCursorMark')
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        except Exception as e:
            print(f"Error fetching from Europe PMC: {e}")
            break
        time.sleep(0.5)
            
    return results

def fetch_paper_by_id(identifier):
    """Fetches a single paper's core details from Europe PMC using DOI or PMID."""
    if str(identifier).startswith('10.'):
        query = f'doi:"{identifier}"'
    else:
        query = f'ext_id:"{identifier}"'
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={encoded_query}&resultType=core&format=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'AntigravityDVPScraper/1.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            results = data.get('resultList', {}).get('result', [])
            return results[0] if results else None
    except Exception as e:
        print(f"Error fetching paper {identifier}: {e}")
        return None

def fetch_missing_linked_papers(raw_results):
    """
    Scans raw results for explicit preprint-to-publication links in commentCorrectionList,
    and fetches the linked papers from Europe PMC if they are not already in raw_results.
    """
    existing_ids = {r.get('id') for r in raw_results if r.get('id')}
    to_fetch = set()
    
    for r in raw_results:
        cc_list = r.get('commentCorrectionList', {}).get('commentCorrection', [])
        for cc in cc_list:
            cc_type = cc.get('type', '')
            cc_id = cc.get('id', '')
            if cc_type == 'Preprint of' and cc_id and cc_id not in existing_ids:
                to_fetch.add(cc_id)
            elif cc_type == 'Preprint in' and cc_id and cc_id not in existing_ids:
                to_fetch.add(cc_id)
                
    if to_fetch:
        print(f"Found {len(to_fetch)} linked peer-reviewed papers not in search results. Fetching them...")
        for pmid in sorted(to_fetch):
            print(f"Fetching linked paper PMID: {pmid}")
            paper = fetch_paper_by_id(pmid)
            if paper:
                raw_results.append(paper)
                existing_ids.add(pmid)

def merge_preprints(papers_data, authors_data, keywords_data):
    """Identifies preprints matching peer-reviewed articles and merges them."""
    def clean_text(t):
        if not t:
            return ""
        return t.lower()
        
    def get_words(t):
        return set(re.findall(r'\b\w{3,}\b', clean_text(t)))
        
    def jaccard(s1, s2):
        if not s1 or not s2:
            return 0
        return len(s1.intersection(s2)) / len(s1.union(s2))

    # Map PMID -> list of author details sorted by order
    paper_author_details = {}
    for auth in authors_data:
        pmid = auth['PMID']
        if pmid not in paper_author_details:
            paper_author_details[pmid] = []
        paper_author_details[pmid].append(auth)
        
    for pmid in paper_author_details:
        paper_author_details[pmid].sort(key=lambda x: x['Author Order'])

    # Separate preprint papers from peer-reviewed journals
    preprints = [p for p in papers_data if p.get('is_preprint')]
    peer_reviewed_papers = [p for p in papers_data if not p.get('is_preprint')]
    
    # Establish explicit/manual mappings first
    preprint_mappings = {}  # preprint_pmid -> peer_reviewed_pmid
    
    # Manual overrides for cases not linked by Europe PMC
    manual_mappings = {
        "PPR758328": "39415009",   # Nordmann 2023 (medRxiv -> Nature)
        "PPR934792": "40240610",   # Rosenberger 2024 (bioRxiv -> Nature)
        "PPR855498": "41044418",   # Wünemann 2024 (bioRxiv -> Nature Cardiovascular Research)
        "PPR992828": "41233595",   # Makhmut 2025 (bioRxiv -> Molecular Systems Biology)
    }
    
    # Extract links from data
    for p in papers_data:
        pmid = p['PMID']
        if p.get('preprint_of'):
            preprint_mappings[pmid] = p['preprint_of']
        if p.get('preprint_in'):
            preprint_mappings[p['preprint_in']] = pmid

    # Merge manual mappings
    for prep_id, pub_id in manual_mappings.items():
        if prep_id not in preprint_mappings:
            preprint_mappings[prep_id] = pub_id

    matched_preprint_pmids = set(preprint_mappings.keys())
    
    # Run fuzzy matching for any unmapped preprints
    for prep in preprints:
        prep_pmid = prep['PMID']
        if prep_pmid in matched_preprint_pmids:
            continue
            
        # Find matches in peer-reviewed papers
        best_match = None
        
        prep_title_words = get_words(prep['Title'])
        prep_author_details = paper_author_details.get(prep_pmid, [])
        prep_first_author = prep_author_details[0]['Last Name'].lower() if prep_author_details else ""
        prep_authors_set = {auth['Last Name'].lower() for auth in prep_author_details}
        prep_abs_words = get_words(prep['Abstract'])
        
        for pub in peer_reviewed_papers:
            pub_pmid = pub['PMID']
            pub_title_words = get_words(pub['Title'])
            title_sim = jaccard(prep_title_words, pub_title_words)
            
            # 1. High Title Similarity (>= 0.70) -> Match
            if title_sim >= 0.70:
                best_match = pub
                break
                
            # 2. Fuzzy match by author and abstract/title overlap
            pub_author_details = paper_author_details.get(pub_pmid, [])
            pub_first_author = pub_author_details[0]['Last Name'].lower() if pub_author_details else ""
            pub_authors_set = {auth['Last Name'].lower() for auth in pub_author_details}
            
            first_author_match = (prep_first_author and pub_first_author and prep_first_author == pub_first_author)
            author_sim = jaccard(prep_authors_set, pub_authors_set)
            shared_authors_count = len(prep_authors_set.intersection(pub_authors_set))
            
            if first_author_match and (author_sim >= 0.50 or shared_authors_count >= 5):
                # Author match succeeds, now check text overlap
                pub_abs_words = get_words(pub['Abstract'])
                abs_sim = jaccard(prep_abs_words, pub_abs_words)
                
                # Match if abstract similarity is high, OR title similarity is high
                if (prep_abs_words and pub_abs_words and abs_sim >= 0.25) or title_sim >= 0.35:
                    best_match = pub
                    break
                        
        if best_match:
            preprint_mappings[prep_pmid] = best_match['PMID']
            matched_preprint_pmids.add(prep_pmid)
            print(f"Fuzzy matched preprint (PMID {prep_pmid}) with peer-reviewed publication (PMID {best_match['PMID']}): '{best_match['Title'][:60]}...'")

    # Apply merges to peer-reviewed papers
    merged_papers = []
    
    # Keep track of which peer_reviewed PMIDs received a preprint
    for pub in peer_reviewed_papers:
        pub_pmid = pub['PMID']
        # Check if any preprint mapped to this pub
        preprints_linked = [prep for prep_pmid, p_id in preprint_mappings.items() if p_id == pub_pmid for prep in preprints if prep['PMID'] == prep_pmid]
        
        if preprints_linked:
            # Sort preprints to choose the primary one if multiple (rare)
            preprints_linked.sort(key=lambda x: x.get('Citations', 0), reverse=True)
            linked_prep = preprints_linked[0]
            pub['Preprint PMID'] = linked_prep['PMID']
            pub['Preprint DOI'] = linked_prep['DOI']
            # Max citations
            pub['Citations'] = max(pub.get('Citations', 0), linked_prep.get('Citations', 0))
            print(f"Linked preprint {linked_prep['PMID']} to publication {pub_pmid} and updated citations.")
            
        merged_papers.append(pub)

    # Keep preprints that do not have any peer-reviewed counterpart
    for prep in preprints:
        if prep['PMID'] not in matched_preprint_pmids:
            merged_papers.append(prep)

    # Filter out preprint authors and keywords to avoid duplicate counting
    filtered_authors = [a for a in authors_data if a['PMID'] not in preprint_mappings]
    filtered_keywords = [k for k in keywords_data if k['PMID'] not in preprint_mappings]

    return merged_papers, filtered_authors, filtered_keywords

def fetch_and_enrich_details(raw_results):
    """
    Filters results for DVP relevance, extracts metadata,
    categorizes paper types, and parses authors/keywords.
    """
    papers_data = []
    authors_data = []
    keywords_data = []
    
    dvp_regex = re.compile(r'\b(deep[\s\-\u00a0]+visual[\s\-\u00a0]+proteomics|scdvp|mipdvp)\b', re.IGNORECASE)
    core_authors = {'mann', 'coscia', 'mund', 'makhmut', 'brunner'}
    spatial_terms = ['spatial proteomics', 'single-cell proteomics', 'single cell proteomics', 'laser microdissection', 'laser-capture microdissection', 'cellenone']

    for p in tqdm(raw_results, desc="Processing publications"):
        pmid = p.get('id', '')
        if not pmid:
            continue
            
        title = p.get('title', '').strip().rstrip('.')
        abstract_text = p.get('abstractText', '')
        
        # Extract keywords and mesh headings for lenient matching
        keywords = [str(kw).lower() for kw in p.get('keywordList', {}).get('keyword', [])]
        mesh_terms = [str(mh.get('descriptorName', '')).lower() for mh in p.get('meshHeadingList', {}).get('meshHeading', [])]
        keywords_str = " ".join(keywords) + " " + " ".join(mesh_terms)
        
        # Relevance filter
        text_to_search = title + " " + abstract_text + " " + keywords_str
        
        is_matched = False
        if dvp_regex.search(text_to_search):
            is_matched = True
        else:
            # Check for core DVP authors and spatial terms
            authors = [a.get('fullName', '').lower() for a in p.get('authorList', {}).get('author', [])]
            has_core_author = any(any(core in auth for core in core_authors) for auth in authors)
            
            title_abs_lower = (title + " " + abstract_text).lower()
            has_spatial_terms = any(term in title_abs_lower for term in spatial_terms)
            
            if has_core_author and has_spatial_terms:
                is_matched = True
                
        if not is_matched:
            continue
            
        # Parse Journal Name (use publisher for preprints)
        journal = p.get('journalTitle', '')
        if not journal:
            journal = p.get('journalInfo', {}).get('journal', {}).get('title', '')
        if not journal and p.get('source') == 'PPR':
            journal = p.get('bookOrReportDetails', {}).get('publisher', 'bioRxiv')
        if not journal:
            journal = 'bioRxiv'
            
        doi = p.get('doi', '')
        year = p.get('pubYear', '')
        citations = int(p.get('citedByCount', 0))
        
        # Paper classification
        pub_types = p.get('pubTypeList', {}).get('pubType', [])
        pub_types_str = " ".join(pub_types).lower()
        title_lower = title.lower()
        journal_lower = journal.lower()
        
        # Filter out non-publications (meeting abstracts, errata, corrections, retractions)
        is_non_publication = False
        if "abstract" in pub_types_str or "meeting-abstract" in pub_types_str:
            is_non_publication = True
        if any(x in pub_types_str for x in ["erratum", "correction", "retraction", "retracted"]):
            is_non_publication = True
        if any(x in title_lower for x in ["correction to", "erratum to", "retraction note", "author correction"]):
            is_non_publication = True
        # Generic blacklisted titles (case-insensitive checks)
        blacklisted_titles = {"session 1", "session 2", "session 3", "session 4", "session 5", "poster session", "abstracts", "table of contents", "author index"}
        if title_lower.strip() in blacklisted_titles:
            is_non_publication = True
            
        if is_non_publication:
            continue
            
        # Determine if paper is a preprint
        is_preprint = False
        if p.get('source') == 'PPR' or 'preprint' in pub_types_str:
            is_preprint = True
        elif any(x in journal_lower for x in ['biorxiv', 'medrxiv', 'arxiv', 'research square', 'preprints.org']):
            is_preprint = True
            
        # Check for explicit preprint/peer-reviewed links in commentCorrectionList
        preprint_of_id = ""
        preprint_in_id = ""
        cc_list = p.get('commentCorrectionList', {}).get('commentCorrection', [])
        for cc in cc_list:
            cc_type = cc.get('type', '')
            cc_id = cc.get('id', '')
            if cc_type == 'Preprint of' and cc_id:
                preprint_of_id = cc_id
            elif cc_type == 'Preprint in' and cc_id:
                preprint_in_id = cc_id
        
        paper_type = "Disease Application" # Default
        if pmid in CLASSIFICATION_OVERRIDES:
            paper_type = CLASSIFICATION_OVERRIDES[pmid]
        else:
            if "review" in pub_types_str or "review" in journal_lower or "review" in title_lower:
                paper_type = "Review"
            elif "protocol" in title_lower or "protocol" in journal_lower:
                paper_type = "Protocol"
            elif "method" in title_lower or "methodology" in title_lower:
                paper_type = "Workflow Improvement"
        
        # Save Paper metadata
        papers_data.append({
            'PMID': pmid,
            'Title': title,
            'Journal': journal,
            'Publication Year': year,
            'DOI': doi,
            'Paper Type': paper_type,
            'Abstract': abstract_text,
            'Citations': citations,
            'Preprint PMID': '',
            'Preprint DOI': '',
            'is_preprint': is_preprint,
            'preprint_of': preprint_of_id,
            'preprint_in': preprint_in_id
        })
        
        # Parse Authors
        authors = p.get('authorList', {}).get('author', [])
        for idx, author in enumerate(authors, 1):
            try:
                last_name = author.get('lastName', '')
                first_name = author.get('firstName', '')
                fullName = author.get('fullName', '')
                if not fullName:
                    fullName = f"{first_name} {last_name}".strip() if first_name else last_name
                if not fullName:
                    continue
                
                if not last_name:
                    last_name = fullName.split()[0] if fullName else "Unknown"
                    
                aff_text = ""
                aff_details = author.get('authorAffiliationDetailsList', {}).get('authorAffiliation', [])
                if aff_details:
                    aff_text = aff_details[0].get('affiliation', '')
                    
                inst = parse_institution(aff_text) if aff_text else 'Unknown'
                country = parse_country(aff_text) if aff_text else 'Unknown'
                is_corr = '@' in aff_text if aff_text else False
                
                authors_data.append({
                    'PMID': pmid,
                    'Author Name': fullName,
                    'Last Name': last_name,
                    'Author Order': idx,
                    'Institution': inst,
                    'Country': country,
                    'Is Corresponding': is_corr,
                    'Affiliation': aff_text
                })
            except Exception:
                continue
                
        # Parse Keywords (Author Keywords)
        for kw in p.get('keywordList', {}).get('keyword', []):
            keywords_data.append({
                'PMID': pmid,
                'Keyword': str(kw).strip(),
                'Source': 'Author Keyword'
            })
            
        # Parse MeSH Terms
        for mh in p.get('meshHeadingList', {}).get('meshHeading', []):
            desc = mh.get('descriptorName', '')
            if desc:
                keywords_data.append({
                    'PMID': pmid,
                    'Keyword': str(desc).strip(),
                    'Source': 'MeSH Term'
                })
                
    return papers_data, authors_data, keywords_data

def main():
    search_query = '"Deep Visual Proteomics"'
    print(f"Searching Europe PMC for '{search_query}' (includes preprints and peer-reviewed articles)...")
    
    raw_results = search_europe_pmc(search_query)
    if not raw_results:
        print("No publications found.")
        return
        
    # Fetch linked papers (e.g. peer-reviewed publications) that may not contain the exact search query
    fetch_missing_linked_papers(raw_results)
    
    print(f"Found {len(raw_results)} total publications. Enriching details and applying DVP relevance filters...")
    papers_data, authors_data, keywords_data = fetch_and_enrich_details(raw_results)
    
    if not papers_data:
        print("No relevant DVP publications remained after filtering.")
        return
        
    print(f"Filtering complete! {len(papers_data)} high-relevance DVP publications fetched.")
    
    # Merge bioRxiv preprints
    print("Checking for bioRxiv preprints and merging with peer-reviewed publications...")
    merged_papers, filtered_authors, filtered_keywords = merge_preprints(papers_data, authors_data, keywords_data)
    print(f"Preprint merging complete! {len(merged_papers)} unique publications remain.")
    
    # Convert lists to DataFrames
    df_papers = pd.DataFrame(merged_papers)
    df_authors = pd.DataFrame(filtered_authors)
    df_keywords = pd.DataFrame(filtered_keywords)
    
    # Save the datasets
    df_papers.to_csv("deep_visual_proteomics_papers.csv", index=False)
    print("Saved 'deep_visual_proteomics_papers.csv'")
    
    df_authors.to_csv("dvp_authors.csv", index=False)
    print("Saved 'dvp_authors.csv'")
    
    df_keywords.to_csv("dvp_keywords.csv", index=False)
    print("Saved 'dvp_keywords.csv'")
    
    # Launch visualization generator
    print("Generating visualizations dashboard...")
    try:
        subprocess.run([".venv/bin/python", "visualize.py"], check=True)
        print("Successfully generated visualizations dashboard.")
    except Exception as e:
        print(f"Failed to generate visualizations dashboard: {e}")

if __name__ == "__main__":
    main()
