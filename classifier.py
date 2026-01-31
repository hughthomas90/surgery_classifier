import streamlit as st
import pandas as pd
import requests
import re
from datetime import datetime

# --- CLASSIFIER LOGIC (Strict Version) ---
def classify_paper(title):
    """
    Classifies a paper title as 'Surgical' or 'Non-Surgical' based purely on the presence
    of unambiguous surgical keywords.
    Returns a tuple: (Classification, Score, Reason)
    """
    if not isinstance(title, str):
        return "Non-Surgical", 0, "No Title"

    title_lower = title.lower()

    # --- SURGICAL / INTERVENTIONAL KEYWORDS ---
    # STRICT INCLUSION LIST.
    # Terms must imply a physical surgical act on a patient with high certainty.
    surgical_patterns = [
        # --- 1. The "Must Be Surgery" Roots ---
        (r'\bsurg(ery|ical|eon)\b', "Surgery/Surgical"),
        (r'\boperat(ive)\b', "Operative"), 

        # --- 2. Suffixes (High Specificity) ---
        (r'\w+ectom(y|ies)\b', "Excision (-ectomy)"),       
        (r'\w+otom(y|ies)\b', "Incision (-otomy)"),         
        (r'\w+ostom(y|ies)\b', "Stoma (-ostomy)"),          
        (r'\w+plast(y|ies)\b', "Repair (-plasty)"),         
        (r'\w+pex(y|ies)\b', "Fixation (-pexy)"),           
        (r'\w+rraph(y|ies)\b', "Suture (-rraphy)"),         
        # REMOVED generic 'scop(y|ies)' to exclude diagnostic endoscopy/colonoscopy
        (r'\w+centesis\b', "Puncture"),                     
        (r'\w+desis\b', "Fusion"),                          

        # --- 3. Unambiguous Surgical Actions ---
        (r'\bresection\b', "Resection"),
        (r'\bexcision\b', "Excision"),
        (r'\bablation\b', "Ablation"),          
        (r'\bdebridement\b', "Debridement"),
        (r'\bamputat\w*', "Amputation"),
        (r'\btransplant\w*', "Transplant"),
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
        
        # --- 4. Specific "Repair" Contexts ---
        (r'\bhernia repair\b', "Hernia Repair"),
        (r'\bvalve repair\b', "Valve Repair"),
        (r'\baneurysm repair\b', "Aneurysm Repair"),
        (r'\bfracture repair\b', "Fracture Repair"),
        (r'\btendon repair\b', "Tendon Repair"),
        (r'\bcleft repair\b', "Cleft Repair"),

        # --- 5. Approaches / Techniques ---
        (r'\blaparoscop\w*', "Laparoscopic"),
        (r'\brobotic\b', "Robotic"), 
        (r'\bendovascular\b', "Endovascular"),
        (r'\bpercutaneous\b', "Percutaneous"),
        (r'\bthoracoscop\w*', "Thoracoscopic"),
        (r'\btranscatheter\b', "Transcatheter"),
        # REMOVED 'endoscop' to exclude diagnostic EGD/Colonoscopy.
        # Interventional endoscopy will be caught by action words (e.g. Resection).
        (r'\bmicrosurg\w*', "Microsurgery"),
        (r'\btransanal\b', "Transanal"),
        (r'\btransoral\b', "Transoral"),
        (r'\bsternotomy\b', "Sternotomy"),
        (r'\bcraniotomy\b', "Craniotomy"),
        (r'\bthoracotomy\b', "Thoracotomy"),
        (r'\blaparotomy\b', "Laparotomy"),
        (r'\barthroscop\w*', "Arthroscopy"), # Added as distinct from generic endoscopy

        # --- 6. Implants / Grafts (Specifics only) ---
        (r'\ballograft\b', "Allograft"),
        (r'\bxenograft\b', "Xenograft"),
        (r'\bautograft\b', "Autograft"),
        (r'\bhomograft\b', "Homograft"),
        (r'\bprosthes(is|es)\b', "Prosthesis"), 
        (r'\bflap\b', "Flap"),
        (r'\bdonor\b', "Donor"),
        (r'\brecipient\b', "Recipient"),

        # --- 7. Named Procedures ---
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
        
        # --- 8. Strong Perioperative Terms ---
        (r'\bintraoperative\b', "Intraoperative"),
        (r'\bperioperative\b', "Perioperative"),
        (r'\bpostoperative\b', "Postoperative"),
    ]

    for pattern, tag in surgical_patterns:
        if re.search(pattern, title_lower):
            return "Surgical", 1, tag

    return "Non-Surgical", 0, "No keywords found"

# --- OPENALEX API HANDLER ---
def fetch_openalex_papers(query, limit=50, start_year=None, end_year=None, types=None, journal_search=None):
    base_url = "https://api.openalex.org/works"
    
    # Construct Filter String
    filters = []
    
    # 1. Date Range
    current_year = datetime.now().year
    start = start_year if start_year else 1900
    end = end_year if end_year else current_year
    filters.append(f"publication_year:{start}-{end}")
    
    # 2. Article Types (e.g., type:article|review)
    if types:
        # OpenAlex uses pipe | for OR logic within a filter
        type_str = "|".join(types)
        filters.append(f"type:{type_str}")
        
    # 3. Journal Search (Source)
    if journal_search:
        # Search for the string in the source display name
        filters.append(f"primary_location.source.display_name.search:{journal_search}")

    # Combine all filters with commas (AND logic)
    filter_param = ",".join(filters)

    params = {
        "search": query,
        "per-page": limit,
        "filter": filter_param,
        "select": "id,display_name,publication_year,primary_location,authorships,doi,type"
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get('results', [])
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data from OpenAlex: {e}")
        return []

def extract_journal_name(paper):
    loc = paper.get('primary_location') or {}
    source = loc.get('source') or {}
    return source.get('display_name', 'Unknown Journal')

# --- STREAMLIT APP UI ---
st.set_page_config(page_title="Surgical Paper Classifier", layout="wide")

st.title("🔪 Surgical Paper Classifier")
st.markdown("""
This tool uses the **OpenAlex API** to find papers and applies a strict keyword classifier 
to identify purely surgical/interventional research.
""")

# --- SIDEBAR CONTROLS ---
st.sidebar.header("Search Parameters")
search_query = st.sidebar.text_input("Topic / Keyword", "pancreaticoduodenectomy")

st.sidebar.divider()
st.sidebar.subheader("Filters")

# Year Slider
current_year = datetime.now().year
year_range = st.sidebar.slider(
    "Publication Years",
    min_value=1980,
    max_value=current_year,
    value=(current_year - 5, current_year)
)

# Article Types
# Common OpenAlex types
available_types = ["article", "review", "editorial", "letter", "preprint", "book-chapter"]
selected_types = st.sidebar.multiselect(
    "Article Type",
    available_types,
    default=["article", "review"]
)

# Journal Source
journal_filter = st.sidebar.text_input("Journal Name (Optional)", placeholder="e.g. Annals of Surgery")

# Limit
result_limit = st.sidebar.number_input("Max Results", min_value=10, max_value=200, value=50, step=10)

run_search = st.sidebar.button("Fetch & Classify", type="primary")

# --- MAIN LOGIC ---
if run_search:
    st.info(f"Querying OpenAlex: '{search_query}' | Years: {year_range[0]}-{year_range[1]} | Types: {selected_types}")
    
    with st.spinner("Fetching data..."):
        results = fetch_openalex_papers(
            query=search_query,
            limit=result_limit,
            start_year=year_range[0],
            end_year=year_range[1],
            types=selected_types,
            journal_search=journal_filter
        )
        
    if results:
        st.success(f"Found {len(results)} papers. Running classification...")
        
        # Process results
        paper_data = []
        for p in results:
            title = p.get('display_name', 'No Title')
            cls, score, reason = classify_paper(title)
            
            paper_data.append({
                "Title": title,
                "Year": p.get('publication_year'),
                "Journal": extract_journal_name(p),
                "Type": p.get('type'),
                "Classification": cls,
                "Reason": reason,
                "DOI": p.get('doi'),
                "OpenAlex ID": p.get('id')
            })
            
        df = pd.DataFrame(paper_data)
        
        # Metrics
        col1, col2 = st.columns(2)
        n_surgical = len(df[df['Classification'] == 'Surgical'])
        n_non = len(df[df['Classification'] == 'Non-Surgical'])
        
        col1.metric("Surgical Papers", n_surgical)
        col2.metric("Non-Surgical Papers", n_non)
        
        # Filter tabs
        tab1, tab2, tab3 = st.tabs(["All Results", "Surgical Only", "Non-Surgical Only"])
        
        with tab1:
            st.dataframe(df, use_container_width=True)
            
        with tab2:
            st.dataframe(df[df['Classification'] == 'Surgical'], use_container_width=True)
            
        with tab3:
            st.dataframe(df[df['Classification'] == 'Non-Surgical'], use_container_width=True)
            
        # Download
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "Download Results as CSV",
            csv,
            "classified_papers.csv",
            "text/csv",
            key='download-csv'
        )
    else:
        st.warning("No results found. Try broadening your search or filters.")
