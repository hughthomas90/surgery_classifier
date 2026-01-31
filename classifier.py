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
    medical_context_pattern = r'\b(stem cell|bone marrow|hematopoietic|fecal|fmt|microbiota|mitochondria|corneal|renal replacement)\b'
    has_medical_context = re.search(medical_context_pattern, title_lower)

    # --- B. POSITIVE PATTERNS (Strict) ---
    surgical_patterns = [
        (r'\bsurg(eries|ery|ical|eons?)\b', "Surgery (General)"),
        (r'\boperat(ions?|ive)\b', "Operative"), 
        (r'\bxeno[\w-]*transplant\w*', "Xenotransplant"), 
        (r'\ballo[\w-]*transplant\w*', "Allotransplant"),
        (r'\borthotopic\b', "Orthotopic Tx"),
        (r'\w*transplant\w*', "Transplant (Generic)"),
        (r'\w+ectom(y|ies)\b', "Excision (-ectomy)"),       
        (r'\w+otom(y|ies)\b', "Incision (-otomy)"),         
        (r'\w+ostom(y|ies)\b', "Stoma (-ostomy)"),          
        (r'\w+plast(y|ies)\b', "Repair (-plasty)"),         
        (r'\w+pex(y|ies)\b', "Fixation (-pexy)"),           
        (r'\w+rraph(y|ies)\b', "Suture (-rraphy)"),         
        (r'\w+desis\b', "Fusion"),                          
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
        (r'\b(hernia|valve|aneurysm|fracture|tendon|cleft|mitral|aortic)\s+repair\b', "Specific Repair"),
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
        (r'\ballograft\b', "Allograft"),
        (r'\bxenograft\b', "Xenograft"),
        (r'\bautograft\b', "Autograft"),
        (r'\bprosthes(is|es)\b', "Prosthesis"), 
        (r'\bflap\b', "Flap"),
        (r'\bdonor\b', "Donor"),
        (r'\brecipient\b', "Recipient"),
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
    weak_tags = ["Transplant (Generic)", "Donor", "Recipient"]
    
    if has_medical_context:
        strong_matches = [m for m in matches if m not in weak_tags]
        if not strong_matches:
            return "Non-Surgical", 0, f"Excluded: Medical Context ({matches[0]})"
        else:
            return "Surgical", 1, f"{strong_matches[0]} (despite medical context)"

    return "Surgical", 1, matches[0]


# ==========================================
# 2. OPENALEX API HANDLER
# ==========================================

def search_journals(journal_names):
    """Resolves journal string names to OpenAlex Source IDs."""
    found_journals = []
    base_url = "https://api.openalex.org/sources"
    
    for name in journal_names:
        params = {"search": name.strip()}
        try:
            r = requests.get(base_url, params=params)
            if r.status_code == 200:
                results = r.json().get('results', [])
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

def get_total_count(source_ids, start_year, end_year):
    """Checks total available papers without fetching them all."""
    base_url = "https://api.openalex.org/works"
    source_filter = "|".join(source_ids)
    filters = [
        f"primary_location.source.id:{source_filter}",
        f"publication_year:{start_year}-{end_year}",
        "type:article|review"
    ]
    params = {
        "filter": ",".join(filters),
        "per-page": 1,
        "select": "id"
    }
    try:
        r = requests.get(base_url, params=params)
        if r.status_code == 200:
            return r.json().get('meta', {}).get('count', 0)
    except:
        return 0
    return 0

def fetch_papers_from_sources(source_ids, start_year, end_year, max_limit=1000):
    """Fetches papers using cursor pagination."""
    base_url = "https://api.openalex.org/works"
    source_filter = "|".join(source_ids)
    filters = [
        f"primary_location.source.id:{source_filter}",
        f"publication_year:{start_year}-{end_year}",
        "type:article|review"
    ]
    params = {
        "filter": ",".join(filters),
        "per-page": 200,
        "cursor": "*",
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
            
            # Update UI
            current_count = len(all_papers)
            status_text.text(f"Fetched {current_count} papers...")
            # Progress calculation: capped at 1.0 (100%)
            progress = min(current_count / max_limit, 1.0)
            progress_bar.progress(progress)

            cursor = data.get('meta', {}).get('next_cursor')
            if not cursor:
                break
            params['cursor'] = cursor
            time.sleep(0.1)
            
    except Exception as e:
        st.error(f"API Error: {e}")

    progress_bar.empty()
    status_text.empty()
    return all_papers[:max_limit]

# ==========================================
# 3. STREAMLIT UI
# ==========================================

st.set_page_config(page_title="Surgical Journal Analyzer", layout="wide")

st.title("🏥 Surgical Journal Analyzer")
st.markdown("""
**Goal:** Retrieve papers from specific journals and strictly isolate **surgical/interventional** content.
""")

# --- STATE MANAGEMENT ---
if 'source_ids' not in st.session_state:
    st.session_state.source_ids = []
if 'total_count' not in st.session_state:
    st.session_state.total_count = 0
if 'journal_names' not in st.session_state:
    st.session_state.journal_names = []

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Define Journals")
    default_journals = "Annals of Surgery, JAMA Surgery"
    journal_input = st.text_area("Journal Names", default_journals, height=100)
    
    st.header("2. Parameters")
    current_year = datetime.now().year
    years = st.slider("Year Range", 2000, current_year, (current_year-1, current_year))
    
    st.divider()
    
    # PRE-FLIGHT CHECK
    if st.button("Check Availability", type="secondary"):
        input_list = [x.strip() for x in journal_input.split(',') if x.strip()]
        with st.spinner("Checking OpenAlex..."):
            resolved = search_journals(input_list)
            if resolved:
                st.session_state.journal_names = [j['name'] for j in resolved]
                st.session_state.source_ids = [j['id'] for j in resolved]
                st.session_state.total_count = get_total_count(st.session_state.source_ids, years[0], years[1])
            else:
                st.session_state.journal_names = []
                st.session_state.total_count = 0
                st.error("No journals found.")

    # Show results of check
    if st.session_state.journal_names:
        st.info(f"Matched: {len(st.session_state.journal_names)} journals")
        st.success(f"Available Papers: {st.session_state.total_count:,}")
    
    st.divider()
    
    # FETCH SETTINGS
    # Default limit to total count if reasonable, otherwise clamp it
    default_limit = min(st.session_state.total_count, 1000) if st.session_state.total_count > 0 else 500
    
    max_papers = st.number_input(
        "Fetch Limit", 
        min_value=10, 
        max_value=20000, 
        value=int(default_limit) if default_limit > 0 else 500,
        help="Max 20,000 for browser stability."
    )
    
    run_btn = st.button("Fetch & Analyze", type="primary", disabled=not st.session_state.source_ids)


# --- MAIN EXECUTION ---
if run_btn:
    if not st.session_state.source_ids:
        st.warning("Please check availability first to identify journals.")
    else:
        st.write(f"### Fetching from: {', '.join(st.session_state.journal_names)}")
        
        # FETCH
        raw_papers = fetch_papers_from_sources(
            st.session_state.source_ids, 
            years[0], 
            years[1], 
            max_papers
        )
            
        if not raw_papers:
            st.warning("No papers fetched.")
        else:
            # CLASSIFY
            processed_data = []
            for p in raw_papers:
                title = p.get('display_name', 'No Title')
                cls, score, reason = classify_paper(title)
                
                primary_loc = p.get('primary_location') or {}
                source = primary_loc.get('source') or {}
                source_name = source.get('display_name', 'Unknown')
                
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
            
            # METRICS
            st.divider()
            col1, col2, col3 = st.columns(3)
            n_total = len(df)
            n_surg = len(df[df['Classification'] == 'Surgical'])
            pct_surg = (n_surg / n_total) * 100 if n_total > 0 else 0
            
            col1.metric("Total Papers Fetched", n_total)
            col2.metric("Classified Surgical", n_surg)
            col3.metric("Surgical Yield", f"{pct_surg:.1f}%")
            
            # CHARTS
            st.subheader("📊 Analysis")
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("##### Surgical vs Non-Surgical")
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
                st.markdown("##### Top Surgical Topics")
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

            # TABLE
            st.divider()
            tab_all, tab_surg, tab_non = st.tabs(["All Papers", "✅ Surgical", "❌ Non-Surgical"])
            with tab_all: st.dataframe(df, use_container_width=True)
            with tab_surg: st.dataframe(df[df['Classification'] == 'Surgical'], use_container_width=True)
            with tab_non: st.dataframe(df[df['Classification'] == 'Non-Surgical'], use_container_width=True)

            # DOWNLOAD
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "Download CSV",
                csv,
                "surgical_analysis.csv",
                "text/csv",
                key='download-main'
            )
