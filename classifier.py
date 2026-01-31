import streamlit as st
import pandas as pd
import requests
import re
import time
import altair as alt
from datetime import datetime

# ==========================================
# 1. CLASSIFIER LOGIC (REFINED)
# ==========================================

def classify_paper(title):
    """
    Classifies a paper as 'Surgical' or 'Non-Surgical'.
    
    Logic:
    1. Scan for "Medical Transplant" context (Negative Signal).
    2. Scan for "Surgical" patterns (Positive Signal).
    3. If the ONLY positive signal is generic "Transplant" AND a negative signal is present, 
       classify as Non-Surgical.
    4. If a strong surgical signal (e.g., 'Resection') is present, it overrides the negative signal.
    """
    if not isinstance(title, str):
        return "Non-Surgical", 0, "No Title"

    title_lower = title.lower()

    # --- A. NEGATIVE CONTEXT (The "Medical" Trap) ---
    # These terms typically indicate a non-surgical transplant or medical procedure
    # when paired with generic transplant terms.
    medical_context_pattern = r'\b(stem cell|bone marrow|hematopoietic|fecal|fmt|microbiota|mitochondria|corneal|renal replacement)\b'
    has_medical_context = re.search(medical_context_pattern, title_lower)

    # --- B. POSITIVE PATTERNS (Strict) ---
    surgical_patterns = [
        # 1. Strong Roots (Plurals included)
        (r'\bsurg(eries|ery|ical|eons?)\b', "Surgery (General)"),
        (r'\boperat(ions?|ive)\b', "Operative"), 

        # 2. Transplants (Nuanced)
        # Explicitly catch xeno/allo/auto/orthotopic
        (r'\bxeno[\w-]*transplant\w*', "Xenotransplant"), 
        (r'\ballo[\w-]*transplant\w*', "Allotransplant"),
        (r'\borthotopic\b', "Orthotopic Tx"),
        # Generic catch-all for "transplant", "transplantation"
        (r'\w*transplant\w*', "Transplant (Generic)"),

        # 3. Suffixes (Gold Standard)
        (r'\w+ectom(y|ies)\b', "Excision (-ectomy)"),       
        (r'\w+otom(y|ies)\b', "Incision (-otomy)"),         
        (r'\w+ostom(y|ies)\b', "Stoma (-ostomy)"),          
        (r'\w+plast(y|ies)\b', "Repair (-plasty)"),         
        (r'\w+pex(y|ies)\b', "Fixation (-pexy)"),           
        (r'\w+rraph(y|ies)\b', "Suture (-rraphy)"),         
        (r'\w+desis\b', "Fusion"),                          

        # 4. Explicit Actions
        (r'\bresection\b', "Resection"),
        (r'\bexcision\b', "Excision"),
        (r'\bablation\b', "Ablation"),          
        (r'\bdebridement\b', "Debridement"),
        (r'\bamputat\w*', "Amputation"),
        (r'\brevascularization\b', "Revascularization"),
        (r'\banastomos(is|es)\b', "Anastomosis"),
        (r'\bcautery\b', "Cautery"),
        (r'\bligat(ion|ure)\b', "Ligation"),
        (r'\bincis(ion|ional)\b', "Incision"),
        (r'\benucleation\b', "Enucleation"),
        (r'\bdecortication\b', "Decortication"),
        (r'\bexenteration\b', "Exenteration"),
        (r'\bfulguration\b', "Fulguration"),
        (r'\bmarsupialization\b', "Marsupialization"),
        
        # 5. Specific Repair Contexts
        (r'\b(hernia|valve|aneurysm|fracture|tendon|cleft|mitral|aortic)\s+repair\b', "Specific Repair"),

        # 6. Approaches
        (r'\blaparoscop\w*', "Laparoscopic"),
        (r'\brobotic\b', "Robotic"), 
        (r'\bendovascular\b', "Endovascular"),
        (r'\bpercutaneous\b', "Percutaneous"),
        (r'\bthoracoscop\w*', "Thoracoscopic"),
        (r'\btranscatheter\b', "Transcatheter"),
        (r'\bmicrosurg\w*', "Microsurgery"),
        (r'\btransanal\b', "Transanal"),
        (r'\bsternotomy\b', "Sternotomy"),
        (r'\bcraniotomy\b', "Craniotomy"),
        (r'\bthoracotomy\b', "Thoracotomy"),
        (r'\blaparotomy\b', "Laparotomy"),
        (r'\barthroscop\w*', "Arthroscopy"),

        # 7. Implants / Grafts
        (r'\ballograft\b', "Allograft"),
        (r'\bxenograft\b', "Xenograft"),
        (r'\bautograft\b', "Autograft"),
        (r'\bprosthes(is|es)\b', "Prosthesis"), 
        (r'\bflap\b', "Flap"),
        (r'\bdonor\b', "Donor"),
        (r'\brecipient\b', "Recipient"),

        # 8. Named Procedures
        (r'\bwhipple\b', "Whipple"),
        (r'\broux-en-y\b', "Roux-en-Y"),
        (r'\bhartmann\'?s?\b', "Hartmann's"),
        (r'\bnissen\b', "Nissen"),
        (r'\bfundoplication\b', "Fundoplication"),
        (r'\btevar\b', "TEVAR"),
        (r'\bevar\b', "EVAR"),
        (r'\bcabg\b', "CABG"),
        (r'\bpoucho\b', "Pouch"), 
        (r'\bmetastasectomy\b', "Metastasectomy"),
        (r'\blymphadenectomy\b', "Lymphadenectomy"),
    ]

    # --- C. EVALUATION ---
    matches = []
    for pattern, tag in surgical_patterns:
        if re.search(pattern, title_lower):
            matches.append(tag)

    if not matches:
        return "Non-Surgical", 0, "No keywords"

    # --- D. CONFLICT RESOLUTION ---
    # Case: "Stem cell transplantation" -> Match: "Transplant (Generic)" + Context: "Stem cell"
    # Result: Non-Surgical.
    
    # Case: "Bowel resection after stem cell transplantation" -> Match: "Resection", "Transplant" + Context: "Stem cell"
    # Result: Surgical (because "Resection" is a strong independent signal).

    # We categorize matches into "Weak" (vulnerable to medical context) and "Strong"
    weak_tags = ["Transplant (Generic)", "Donor", "Recipient"]
    
    # Filter out weak matches if medical context exists
    if has_medical_context:
        strong_matches = [m for m in matches if m not in weak_tags]
        if not strong_matches:
            # If we only had weak matches (like "transplant") and a medical context, it's non-surgical
            return "Non-Surgical", 0, f"Excluded: Medical Context ({matches[0]})"
        else:
            # We have a strong match (e.g. "Resection") alongside the medical context
            return "Surgical", 1, f"{strong_matches[0]} (despite medical context)"

    # If no medical context, or valid strong match exists
    return "Surgical", 1, matches[0]


# ==========================================
# 2. OPENALEX API HANDLER (JOURNAL MODE)
# ==========================================

def search_journals(journal_names):
    """
    Resolves journal string names to OpenAlex Source IDs.
    """
    found_journals = []
    base_url = "https://api.openalex.org/sources"
    
    for name in journal_names:
        params = {"search": name.strip()}
        try:
            r = requests.get(base_url, params=params)
            if r.status_code == 200:
                results = r.json().get('results', [])
                # Simple heuristic: take the first result that is a 'journal'
                for res in results:
                    if res.get('type') == 'journal':
                        found_journals.append({
                            'name': res['display_name'],
                            'id': res['id'],
                            'input_name': name
                        })
                        break
        except:
            pass
    return found_journals

def fetch_papers_from_sources(source_ids, start_year, end_year, max_limit=1000):
    """
    Fetches papers from specific source IDs using cursor pagination.
    """
    base_url = "https://api.openalex.org/works"
    
    # Filter construction
    # source.id:S123|S456 (OR logic)
    source_filter = "|".join(source_ids)
    
    filters = [
        f"primary_location.source.id:{source_filter}",
        f"publication_year:{start_year}-{end_year}",
        "type:article|review" # Limit to articles/reviews
    ]
    
    params = {
        "filter": ",".join(filters),
        "per-page": 200,
        "cursor": "*", # Start cursor
        "select": "id,display_name,publication_year,primary_location,primary_topic,doi"
    }

    all_papers = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        while len(all_papers) < max_limit:
            r = requests.get(base_url, params=params)
            if r.status_code != 200:
                break
            
            data = r.json()
            results = data.get('results', [])
            
            if not results:
                break
                
            all_papers.extend(results)
            
            # Update Progress
            current_count = len(all_papers)
            status_text.text(f"Fetched {current_count} papers...")
            progress = min(current_count / max_limit, 1.0)
            progress_bar.progress(progress)

            # Pagination
            cursor = data.get('meta', {}).get('next_cursor')
            if not cursor:
                break
            params['cursor'] = cursor
            
            # Respect rate limits slightly
            time.sleep(0.1)
            
    except Exception as e:
        st.error(f"API Error: {e}")

    progress_bar.empty()
    status_text.empty()
    
    # Trim to limit
    return all_papers[:max_limit]

# ==========================================
# 3. STREAMLIT UI
# ==========================================

st.set_page_config(page_title="Surgical Journal Analyzer", layout="wide")

st.title("🏥 Surgical Journal Analyzer")
st.markdown("""
**Goal:** Retrieve papers from specific journals and strictly isolate **surgical/interventional** content.
**Filters:** Eliminates "Medical Transplants" (FMT, Stem Cell, Bone Marrow) and diagnostic-only procedures.
""")

# --- SIDEBAR: CONFIGURATION ---
with st.sidebar:
    st.header("1. Define Journals")
    default_journals = "Annals of Surgery, JAMA Surgery, British Journal of Surgery"
    journal_input = st.text_area("Journal Names (comma separated)", default_journals, height=100)
    
    st.header("2. Parameters")
    current_year = datetime.now().year
    years = st.slider("Year Range", 2000, current_year, (current_year-2, current_year))
    max_papers = st.number_input("Max Papers to Fetch", min_value=100, max_value=5000, value=500, step=100)
    
    run_btn = st.button("Analyze Journals", type="primary")

# --- MAIN EXECUTION ---
if run_btn:
    # 1. Resolve Journals
    input_list = [x.strip() for x in journal_input.split(',') if x.strip()]
    
    with st.spinner("Resolving Journal IDs..."):
        resolved_sources = search_journals(input_list)
    
    if not resolved_sources:
        st.error("Could not find any of the specified journals in OpenAlex.")
    else:
        # Display resolved journals
        found_names = [j['name'] for j in resolved_sources]
        source_ids = [j['id'] for j in resolved_sources]
        st.success(f"Found {len(found_names)} journals: {', '.join(found_names)}")
        
        # 2. Fetch Papers
        with st.spinner(f"Fetching up to {max_papers} papers (200/batch)..."):
            raw_papers = fetch_papers_from_sources(source_ids, years[0], years[1], max_papers)
            
        if not raw_papers:
            st.warning("No papers found matching criteria.")
        else:
            # 3. Classify
            processed_data = []
            for p in raw_papers:
                title = p.get('display_name', 'No Title')
                cls, score, reason = classify_paper(title)
                
                # Get Source Name safely (Handle NoneType at any level)
                primary_loc = p.get('primary_location') or {}
                source = primary_loc.get('source') or {}
                source_name = source.get('display_name', 'Unknown')
                
                # Get Topic safely (Handle NoneType if primary_topic is null)
                primary_topic = p.get('primary_topic') or {}
                topic = primary_topic.get('display_name', 'Uncategorized')
                
                processed_data.append({
                    "Title": title,
                    "Classification": cls,
                    "Reason": reason,
                    "Journal": source_name,
                    "Year": p.get('publication_year'),
                    "Topic": topic,
                    "DOI": p.get('doi'),
                    "OpenAlex ID": p.get('id')
                })
            
            df = pd.DataFrame(processed_data)
            
            # --- DASHBOARD ---
            
            # Metrics Row
            st.divider()
            col1, col2, col3 = st.columns(3)
            n_total = len(df)
            n_surg = len(df[df['Classification'] == 'Surgical'])
            pct_surg = (n_surg / n_total) * 100 if n_total > 0 else 0
            
            col1.metric("Total Papers Fetched", n_total)
            col2.metric("Classified Surgical", n_surg)
            col3.metric("Surgical Yield", f"{pct_surg:.1f}%")
            
            # Visualizations
            st.subheader("📊 Analysis")
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("##### Surgical vs Non-Surgical by Journal")
                if not df.empty:
                    chart_data = df.groupby(['Journal', 'Classification']).size().reset_index(name='Count')
                    bar_chart = alt.Chart(chart_data).mark_bar().encode(
                        x=alt.X('Journal', axis=alt.Axis(labelAngle=-45)),
                        y='Count',
                        color=alt.Color('Classification', scale=alt.Scale(domain=['Surgical', 'Non-Surgical'], range=['#ef4444', '#94a3b8'])),
                        tooltip=['Journal', 'Classification', 'Count']
                    ).properties(height=300)
                    st.altair_chart(bar_chart, use_container_width=True)
                
            with c2:
                st.markdown("##### Top Topics in Surgical Papers")
                surg_df = df[df['Classification'] == 'Surgical']
                if not surg_df.empty:
                    topic_counts = surg_df['Topic'].value_counts().head(10).reset_index()
                    topic_counts.columns = ['Topic', 'Count']
                    
                    topic_chart = alt.Chart(topic_counts).mark_bar().encode(
                        x=alt.X('Count'),
                        y=alt.Y('Topic', sort='-x'),
                        color=alt.value('#ef4444'),
                        tooltip=['Topic', 'Count']
                    ).properties(height=300)
                    st.altair_chart(topic_chart, use_container_width=True)
                else:
                    st.info("No surgical papers to analyze topics.")

            # Data Table
            st.divider()
            st.subheader("📑 Detailed Results")
            
            tab_all, tab_surg, tab_non = st.tabs(["All Papers", "✅ Surgical Only", "❌ Non-Surgical"])
            
            with tab_all:
                st.dataframe(df, use_container_width=True)
            with tab_surg:
                st.dataframe(df[df['Classification'] == 'Surgical'], use_container_width=True)
            with tab_non:
                st.dataframe(df[df['Classification'] == 'Non-Surgical'], use_container_width=True)

            # Download
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "Download Dataset (CSV)",
                csv,
                "surgical_analysis.csv",
                "text/csv",
                key='download-main'
            )
