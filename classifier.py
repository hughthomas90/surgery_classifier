import streamlit as st
import pandas as pd
import requests
import re
import time
import altair as alt
from datetime import datetime

# ==========================================
# 1. CLASSIFIER LOGIC
# ==========================================

def classify_paper(title):
    if not isinstance(title, str):
        return "Non-Surgical", 0, "No Title"

    title_lower = title.lower()

    # --- A. NEGATIVE CONTEXT ---
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

    matches = []
    for pattern, tag in surgical_patterns:
        if re.search(pattern, title_lower):
            matches.append(tag)

    if not matches:
        return "Non-Surgical", 0, "No keywords"

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
    base_url = "https://api.openalex.org/works"
    source_filter = "|".join(source_ids)
    filters = [
        f"primary_location.source.id:{source_filter}",
        f"publication_year:{start_year}-{end_year}",
        "type:article|review"
    ]
    # Added authorships to select
    params = {
        "filter": ",".join(filters),
        "per-page": 200,
        "cursor": "*",
        "select": "id,display_name,publication_year,primary_location,primary_topic,doi,fwci,cited_by_count,authorships"
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
            
            current_count = len(all_papers)
            status_text.text(f"Fetched {current_count} papers...")
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

def extract_corresponding_info(authorships):
    """Parses authorships to find corresponding author institution and country."""
    if not authorships:
        return "Unknown", "Unknown"
    
    # 1. Try explicit corresponding flag
    for auth in authorships:
        if auth.get('is_corresponding'):
            insts = auth.get('institutions', [])
            if insts:
                return insts[0].get('display_name', ''), insts[0].get('country_code', '')
    
    # 2. Fallback to first author
    if authorships:
        first = authorships[0]
        insts = first.get('institutions', [])
        if insts:
            return insts[0].get('display_name', ''), insts[0].get('country_code', '')
            
    return "Unknown", "Unknown"

# ==========================================
# 3. STREAMLIT UI
# ==========================================

st.set_page_config(page_title="Surgical Impact Analyzer", layout="wide")

st.title("🏥 Surgical Impact Analyzer")
st.markdown("""
**Goal:** Retrieve papers, isolate surgical content, and analyze **citation impact (FWCI)** and **output proportions**.
**Features:** Corresponding Author extraction, Country analysis, and OpenAlex drill-down.
""")

if 'source_ids' not in st.session_state:
    st.session_state.source_ids = []
if 'total_count' not in st.session_state:
    st.session_state.total_count = 0
if 'journal_names' not in st.session_state:
    st.session_state.journal_names = []

with st.sidebar:
    st.header("1. Define Journals")
    default_journals = "Annals of Surgery, JAMA Surgery, British Journal of Surgery"
    journal_input = st.text_area("Journal Names", default_journals, height=100)
    
    st.header("2. Parameters")
    current_year = datetime.now().year
    years = st.slider("Year Range", 2000, current_year, (current_year-3, current_year))
    
    st.divider()
    
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

    if st.session_state.journal_names:
        st.info(f"Matched: {len(st.session_state.journal_names)} journals")
        st.success(f"Available Papers: {st.session_state.total_count:,}")
    
    st.divider()
    
    default_limit = min(st.session_state.total_count, 1000) if st.session_state.total_count > 0 else 500
    
    max_papers = st.number_input(
        "Fetch Limit", 
        min_value=10, 
        max_value=20000, 
        value=int(default_limit) if default_limit > 0 else 500
    )
    
    run_btn = st.button("Fetch & Analyze", type="primary", disabled=not st.session_state.source_ids)

if run_btn:
    if not st.session_state.source_ids:
        st.warning("Please check availability first to identify journals.")
    else:
        st.write(f"### Fetching from: {', '.join(st.session_state.journal_names)}")
        
        raw_papers = fetch_papers_from_sources(
            st.session_state.source_ids, 
            years[0], 
            years[1], 
            max_papers
        )
            
        if not raw_papers:
            st.warning("No papers fetched.")
        else:
            processed_data = []
            for p in raw_papers:
                title = p.get('display_name', 'No Title')
                cls, score, reason = classify_paper(title)
                
                primary_loc = p.get('primary_location') or {}
                source = primary_loc.get('source') or {}
                source_name = source.get('display_name', 'Unknown')
                
                primary_topic = p.get('primary_topic') or {}
                topic = primary_topic.get('display_name', 'Uncategorized')
                
                # Extract Institution/Country
                inst, country = extract_corresponding_info(p.get('authorships', []))

                processed_data.append({
                    "Title": title,
                    "Classification": cls,
                    "Reason": reason,
                    "Journal": source_name,
                    "Year": p.get('publication_year'),
                    "Topic": topic,
                    "Institution": inst,
                    "Country": country,
                    "DOI": p.get('doi'),
                    "OpenAlex ID": p.get('id'),
                    "FWCI": p.get('fwci', 0), 
                    "Citations": p.get('cited_by_count', 0)
                })
            
            df = pd.DataFrame(processed_data)
            
            # --- AGGREGATION LOGIC ---
            journal_counts = df.groupby('Journal').size().reset_index(name='Journal_Total_Papers')
            
            class_stats = df.groupby(['Journal', 'Classification']).size().reset_index(name='Count')
            class_stats = class_stats.merge(journal_counts, on='Journal')
            class_stats['Proportion'] = (class_stats['Count'] / class_stats['Journal_Total_Papers']) * 100

            # --- TABS ---
            st.divider()
            tab_overview, tab_geo, tab_data = st.tabs([
                "📊 Overview", 
                "🌍 Geography & Institutions", 
                "📑 Raw Data & Links"
            ])
            
            # --- TAB 1: OVERVIEW ---
            with tab_overview:
                st.subheader("Surgical vs Non-Surgical Output")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Volume (Count)**")
                    vol_chart = alt.Chart(class_stats).mark_bar().encode(
                        x=alt.X('Journal', axis=alt.Axis(labelAngle=-45)),
                        y='Count',
                        color=alt.Color('Classification', scale=alt.Scale(domain=['Surgical', 'Non-Surgical'], range=['#ef4444', '#94a3b8'])),
                        tooltip=['Journal', 'Classification', 'Count']
                    ).properties(height=350)
                    st.altair_chart(vol_chart, use_container_width=True)
                with col2:
                    st.markdown("**Proportion (%)**")
                    prop_chart = alt.Chart(class_stats).mark_bar().encode(
                        x=alt.X('Journal', axis=alt.Axis(labelAngle=-45)),
                        y=alt.Y('Proportion', title='Percentage of Output'),
                        color=alt.Color('Classification', scale=alt.Scale(domain=['Surgical', 'Non-Surgical'], range=['#ef4444', '#94a3b8'])),
                        tooltip=['Journal', 'Classification', alt.Tooltip('Proportion', format='.1f')]
                    ).properties(height=350)
                    st.altair_chart(prop_chart, use_container_width=True)

            # --- TAB 2: GEOGRAPHY ---
            with tab_geo:
                surg_df = df[df['Classification'] == 'Surgical']
                if surg_df.empty:
                    st.info("No surgical papers to analyze.")
                else:
                    st.subheader("Surgical Output by Country")
                    geo_counts = surg_df['Country'].value_counts().reset_index()
                    geo_counts.columns = ['Country', 'Papers']
                    geo_counts = geo_counts[geo_counts['Country'] != 'Unknown'] # Filter unknowns
                    
                    geo_chart = alt.Chart(geo_counts.head(20)).mark_bar().encode(
                        x=alt.X('Papers'),
                        y=alt.Y('Country', sort='-x'),
                        color=alt.value('#ef4444'),
                        tooltip=['Country', 'Papers']
                    ).properties(height=500)
                    st.altair_chart(geo_chart, use_container_width=True)
                    
                    st.subheader("Top Institutions (Surgical)")
                    inst_counts = surg_df['Institution'].value_counts().reset_index()
                    inst_counts.columns = ['Institution', 'Papers']
                    inst_counts = inst_counts[inst_counts['Institution'] != '']
                    st.dataframe(inst_counts.head(20), use_container_width=True)

            # --- TAB 3: DATA & LINKS ---
            with tab_data:
                st.subheader("Interactive Data Table")
                st.info("Select rows below to generate an OpenAlex analysis link.")
                
                # Make dataframe selectable
                selection = st.dataframe(
                    df,
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="multi-row"
                )
                
                # Link Generator Logic
                selected_indices = selection.selection.rows
                if selected_indices:
                    selected_ids = df.iloc[selected_indices]['OpenAlex ID'].tolist()
                    clean_ids = [i.replace("https://openalex.org/", "") for i in selected_ids]
                    
                    st.markdown("#### 🔗 Analysis Actions")
                    
                    if len(clean_ids) > 150:
                        st.warning(f"You selected {len(clean_ids)} papers. The link may be too long for some browsers.")
                    
                    # Create OpenAlex ID filter string
                    id_filter = "|".join(clean_ids)
                    oa_link = f"https://openalex.org/works?filter=ids.openalex:{id_filter}"
                    
                    st.markdown(f"""
                    <a href="{oa_link}" target="_blank" style="
                        display: inline-block;
                        padding: 10px 20px;
                        background-color: #ef4444;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: bold;">
                        Analyze {len(clean_ids)} Selected Papers in OpenAlex ➜
                    </a>
                    """, unsafe_allow_html=True)
                else:
                    st.caption("No papers selected. Click checkboxes in the table to generate an analysis link.")

                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("Download Raw Data (CSV)", csv, "raw_data.csv", "text/csv")
