import streamlit as st
import PIL.Image
import json
import time
import random
import pandas as pd
import io
from supabase import create_client, Client
from datetime import datetime, timedelta
import base64
from google import genai
from google.genai import types
from ebay_engine import get_ebay_token, buscar_precos_ebay
import os
from google.oauth2 import service_account
import numpy as np
import re

st.set_page_config(page_title="Valurise", page_icon="💎", layout="wide")

# ==========================================
# 🎨 CSS INJETADO — Estilo Premium sem quebrar Streamlit
# ==========================================
st.markdown("""
<style>
/* ===== FONTES & VARIÁVEIS ===== */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --primary: #7C3AED;
    --primary-light: #A78BFA;
    --accent: #10B981;
    --danger: #EF4444;
    --warning: #F59E0B;
    --bg-dark: #0F0F1A;
    --bg-card: #1A1A2E;
    --bg-surface: #16213E;
    --text-primary: #F1F5F9;
    --text-muted: #94A3B8;
    --border: rgba(124, 58, 237, 0.3);
}

/* ===== BASE ===== */
html, body, .stApp {
    background: linear-gradient(135deg, #0F0F1A 0%, #16213E 50%, #0F0F1A 100%) !important;
    font-family: 'Inter', sans-serif !important;
    color: var(--text-primary) !important;
}

/* ===== ESCONDER HEADER PADRÃO DO STREAMLIT ===== */
header[data-testid="stHeader"] {
    background: transparent !important;
}

/* ===== SIDEBAR ===== */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1A1A2E 0%, #0F0F1A 100%) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * {
    color: var(--text-primary) !important;
}

/* ===== TÍTULO PRINCIPAL ===== */
h1 {
    background: linear-gradient(90deg, #A78BFA, #60A5FA, #34D399) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    font-weight: 700 !important;
    font-size: 2.2rem !important;
}

h2, h3 {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
}

/* ===== TABS ===== */
.stTabs [data-baseweb="tab-list"] {
    background: var(--bg-card) !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 4px !important;
    border: 1px solid var(--border) !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 8px !important;
    color: var(--text-muted) !important;
    font-weight: 500 !important;
    padding: 8px 16px !important;
    transition: all 0.2s ease !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, var(--primary), #6D28D9) !important;
    color: white !important;
    box-shadow: 0 4px 15px rgba(124, 58, 237, 0.4) !important;
}

/* ===== BOTÃO PRIMÁRIO ===== */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7C3AED, #6D28D9) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 0.6rem 1.5rem !important;
    box-shadow: 0 4px 15px rgba(124, 58, 237, 0.35) !important;
    transition: all 0.2s ease !important;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 25px rgba(124, 58, 237, 0.5) !important;
}

/* ===== INPUTS & SELECTBOX ===== */
.stTextInput input, .stNumberInput input, .stSelectbox select,
[data-testid="stTextInput"] input,
[data-baseweb="input"] input,
[data-baseweb="select"] div {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
}
.stTextInput input:focus, .stNumberInput input:focus {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 2px rgba(124, 58, 237, 0.2) !important;
}

/* ===== MÉTRICAS / CARDS ===== */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 1rem !important;
}
[data-testid="stMetricValue"] {
    color: var(--primary-light) !important;
    font-weight: 700 !important;
}

/* ===== CONTAINERS COM BORDA ===== */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"][style*="border"] {
    background: var(--bg-card) !important;
    border-color: var(--border) !important;
    border-radius: 12px !important;
}

/* ===== FILE UPLOADER ===== */
[data-testid="stFileUploader"] {
    background: var(--bg-card) !important;
    border: 2px dashed var(--border) !important;
    border-radius: 12px !important;
}

/* ===== ALERTS / INFO / SUCCESS / WARNING / ERROR ===== */
.stSuccess, [data-testid="stAlert"][data-type="success"] {
    background: rgba(16, 185, 129, 0.1) !important;
    border-left: 4px solid var(--accent) !important;
    border-radius: 8px !important;
}
.stWarning, [data-testid="stAlert"][data-type="warning"] {
    background: rgba(245, 158, 11, 0.1) !important;
    border-left: 4px solid var(--warning) !important;
    border-radius: 8px !important;
}
.stError, [data-testid="stAlert"][data-type="error"] {
    background: rgba(239, 68, 68, 0.1) !important;
    border-left: 4px solid var(--danger) !important;
    border-radius: 8px !important;
}
.stInfo, [data-testid="stAlert"][data-type="info"] {
    background: rgba(124, 58, 237, 0.1) !important;
    border-left: 4px solid var(--primary) !important;
    border-radius: 8px !important;
}

/* ===== DATAFRAME / TABELAS ===== */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}
.dvn-scroller {
    background: var(--bg-card) !important;
}

/* ===== CHAT ===== */
[data-testid="stChatMessage"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    margin-bottom: 8px !important;
}

/* ===== PROGRESS BAR ===== */
.stProgress > div > div {
    background: linear-gradient(90deg, var(--primary), var(--primary-light)) !important;
    border-radius: 10px !important;
}

/* ===== SPINNER ===== */
.stSpinner > div {
    border-top-color: var(--primary) !important;
}

/* ===== DIVIDER ===== */
hr {
    border-color: var(--border) !important;
    opacity: 0.5 !important;
}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-dark); }
::-webkit-scrollbar-thumb { background: var(--primary); border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# --- 1. ZONA DE CONFIGURAÇÃO ---
st.sidebar.header("⚙️ Market Settings")

region = st.sidebar.selectbox(
    "Select your Region", 
    ["🇺🇸 USA ($)", "🇬🇧 UK (£)", "🇵🇹 Portugal (€)"]
)

mapa_marketplaces = {
    "🇺🇸 USA ($)": "EBAY_US",
    "🇬🇧 UK (£)": "EBAY_GB",
    "🇵🇹 Portugal (€)": "EBAY_ES" 
}
marketplace_atual = mapa_marketplaces.get(region, "EBAY_US")

seller_type = "Business" 
vat_registered = "Yes"
currency = "€"

if region == "🇬🇧 UK (£)":
    currency = "£"
    seller_type = st.sidebar.radio("Account Type", ["Private", "Business"])
    if seller_type == "Business":
        vat_registered = st.sidebar.radio("Are you VAT Registered?", ["Yes", "No"])
        st.sidebar.caption("If 'No', eBay charges 20% VAT on your seller fees.")
    else:
        st.sidebar.success("Private sellers pay 0% final value fees in the UK! 🎉")

elif region == "🇺🇸 USA ($)":
    currency = "$"


# ==========================================
# 🔑 INICIALIZAÇÃO DO CLIENTE GEMINI
# ==========================================
if "client" not in st.session_state:
    try:
        info_servico = st.secrets["gcp_service_account"]
        credenciais_gcp = service_account.Credentials.from_service_account_info(
            info_servico,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        st.session_state.client = genai.Client(
            vertexai=True, 
            project="gen-lang-client-0850234234", 
            location="us-central1",
            credentials=credenciais_gcp
        )
    except Exception as e:
        st.error(f"Erro ao carregar chave do Vertex AI: {e}")
        
client = st.session_state.get("client")

# ==========================================
# 🗄️ SUPABASE
# ==========================================
url_sb = st.secrets["SUPABASE_URL"]
key_sb = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url_sb, key_sb)

# ==========================================
# 🏁 VARIÁVEIS GLOBAIS
# ==========================================
modo_simulacao = False
ADMINS = ["afonsocgomesduarte@gmail.com"]


# ==========================================
# 🔒 LOGIN (SENHA GLOBAL)
# ==========================================
SENHA_SECRETA = "1234"

if "logado" not in st.session_state:
    st.session_state["logado"] = False

if not st.session_state["logado"]:
    st.title("🔒 Restricted Area")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        entrada = st.text_input("Password:", type="password")
        if st.button("Login", type="primary", use_container_width=True):
            if entrada == SENHA_SECRETA:
                st.session_state["logado"] = True
                st.rerun()
            else:
                st.error("Wrong password!")
    st.stop()


# ==========================================
# 🔧 FUNÇÕES UTILITÁRIAS
# ==========================================

def comprimir_imagem(pil_image):
    img_copy = pil_image.copy()
    img_copy.thumbnail((1024, 1024))
    return img_copy


def obter_base64_imagem(upload_file):
    upload_file.seek(0)
    bytes_data = upload_file.getvalue()
    b64_str = base64.b64encode(bytes_data).decode()
    return f"data:image/png;base64,{b64_str}"


def garantir_token_ebay():
    """Token com cache + renovação automática a cada 90 minutos."""
    agora = time.time()
    token_valido = (
        'ebay_token' in st.session_state and
        st.session_state.ebay_token and
        'ebay_token_ts' in st.session_state and
        (agora - st.session_state.ebay_token_ts) < 5400  # 90 minutos
    )
    if not token_valido:
        try:
            app_id = st.secrets["EBAY_APP_ID"]
            cert_id = st.secrets["EBAY_CERT_ID"]
            novo_token = get_ebay_token(app_id, cert_id)
            if novo_token:
                st.session_state.ebay_token = novo_token
                st.session_state.ebay_token_ts = agora
            else:
                st.error("Não foi possível obter token eBay.")
                return None
        except Exception as e:
            st.error(f"eBay keys not found: {e}")
            return None
    return st.session_state.ebay_token


def set_app_icon(icon_path):
    if os.path.exists(icon_path):
        with open(icon_path, "rb") as f:
            data = f.read()
            b64_encoded = base64.b64encode(data).decode()
        st.markdown(f"""
            <script>
                var link = document.querySelector("link[rel*='icon']") || document.createElement('link');
                link.type = 'image/png'; link.rel = 'shortcut icon';
                link.href = 'data:image/png;base64,{b64_encoded}?v=2';
                document.getElementsByTagName('head')[0].appendChild(link);
            </script>
        """, unsafe_allow_html=True)

set_app_icon("app_icon_512.png")


# ==========================================
# 💾 SUPABASE HELPERS
# ==========================================

def obter_saldo_visual(email_user):
    try:
        res = supabase.table("users_credits").select("creditos").eq("email", email_user).execute()
        return res.data[0]['creditos'] if res.data else 0
    except:
        return 0


def guardar_no_historico(dados, objetivo, email_usuario):
    try:
        entry = {
            "email": email_usuario,
            "produto": dados.get("produto"),
            "preco_medio": dados.get("preco_medio"),
            "sugestao_venda": dados.get("sugestao_venda"),
            "taxas_estimadas": dados.get("taxas_estimadas"),
            "lucro_estimado": dados.get("lucro_estimado"),
            "estrategia": dados.get("estrategia_base"),
            "link_mercado": dados.get("link_pesquisa"),
            "cor": dados.get("veredito_cor"),
            "objetivo": objetivo
        }
        supabase.table("historico_scans").insert(entry).execute()
    except Exception as e:
        print(f"Supabase save error: {e}")


def trava_seguranca_global():
    hoje = datetime.now().date().isoformat()
    try:
        res = supabase.table("historico_geral").select("id", count="exact").eq("data", hoje).execute()
        return res.count >= 1400
    except:
        return False


def gerir_creditos(email_user):
    if not email_user:
        return False, 0
    if email_user in ADMINS:
        return True, 9999
    try:
        res = supabase.table("users_credits").select("*").eq("email", email_user).execute()
        user_data = res.data
        hoje = datetime.now().date().isoformat()

        if not user_data:
            supabase.table("users_credits").insert({
                "email": email_user, "creditos": 1, "ultimo_reset": hoje
            }).execute()
            return True, 1

        dados_user = user_data[0]
        saldo_atual = dados_user.get("creditos", 0)
        data_ultimo_reset = dados_user.get("ultimo_reset")

        if data_ultimo_reset != hoje:
            supabase.table("users_credits").update({
                "creditos": 1, "ultimo_reset": hoje
            }).eq("email", email_user).execute()
            return True, 1

        return (True, saldo_atual) if saldo_atual > 0 else (False, 0)

    except Exception as e:
        st.error(f"Database Error: {e}")
        return False, 0


def gastar_credito(email_utilizador):
    if email_utilizador in ADMINS:
        return
    try:
        res = supabase.table("users_credits").select("creditos").eq("email", email_utilizador).execute()
        if res.data:
            novo_saldo = max(0, res.data[0]['creditos'] - 1)
            supabase.table("users_credits").update({"creditos": novo_saldo}).eq("email", email_utilizador).execute()
    except Exception as e:
        print(f"Credit error: {e}")


def converter_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export = df.copy()
        if 'Verdict' in df_export.columns:
            df_export['Verdict'] = df_export['Verdict'].astype(str)\
                .str.replace('🟢', 'YES').str.replace('🟡', 'MAYBE').str.replace('🔴', 'NO')

        colunas_dinheiro = [f'Cost ({currency})', f'Avg Price ({currency})', f'Target Price ({currency})', f'Est. Fees ({currency})', f'Net Profit ({currency})']
        for col in colunas_dinheiro:
            if col in df_export.columns:
                df_export[col] = df_export[col].astype(str).str.replace(f'{currency}', '').str.replace(',', '.').str.strip()
                df_export[col] = pd.to_numeric(df_export[col], errors='coerce')

        sheet_name = 'Results'
        df_export.to_excel(writer, index=False, sheet_name=sheet_name)
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        
        fmt_verde = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        fmt_amarelo = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C5700'})
        fmt_vermelho = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        
        try:
            col_idx = df_export.columns.get_loc("Verdict")
            ultima_linha = len(df_export) + 1
            worksheet.conditional_format(1, col_idx, ultima_linha, col_idx,
                {'type': 'cell', 'criteria': 'equal to', 'value': '"YES"', 'format': fmt_verde})
            worksheet.conditional_format(1, col_idx, ultima_linha, col_idx,
                {'type': 'cell', 'criteria': 'equal to', 'value': '"MAYBE"', 'format': fmt_amarelo})
            worksheet.conditional_format(1, col_idx, ultima_linha, col_idx,
                {'type': 'cell', 'criteria': 'equal to', 'value': '"NO"', 'format': fmt_vermelho})
            worksheet.set_column(col_idx, col_idx, 15)
        except:
            pass
    return output.getvalue()


def mostrar_rodape_legal():
    st.markdown("---")
    with st.expander("ℹ️ Legal Notice and Disclaimer"):
        st.markdown("""
        **1. Informational Nature:** Valurise is a decision-support tool. Estimates are AI-generated and not financial advice.
        **2. Possibility of Error:** AI can occasionally produce inaccurate or outdated information.
        **3. User Responsibility:** You are solely responsible for verifying information before any transaction.
        *By using this tool, you accept these terms.*
        """)
        st.caption("Powered by Google Gemini AI • Valurise © 2026")


# ==========================================
# 🧮 MOTOR DE CÁLCULO DE TAXAS EBAY
# ==========================================

def calculate_ebay_fees(region, seller_type, vat_registered, category, sale_price):
    fees = 0.0
    fixed_fee = 0.0

    if region == "🇺🇸 USA ($)":
        fixed_fee = 0.30
        if category in ["Sneakers", "Calçado Esportivo"]:
            fees = (sale_price * 0.08) + 0.00 if sale_price >= 150 else (sale_price * 0.1325) + fixed_fee
        elif category in ["Tech", "Eletrónica", "Electronics"]:
            fees = (sale_price * 0.0635) + fixed_fee
        else:
            fees = (sale_price * 0.1325) + fixed_fee

    elif region == "🇬🇧 UK (£)":
        if seller_type == "Private":
            return 0.0
        fixed_fee = 0.30
        if category in ["Sneakers", "Calçado Esportivo"]:
            fees = (sale_price * 0.07) + fixed_fee if sale_price >= 100 else (sale_price * 0.119) + fixed_fee
        elif category in ["Tech", "Eletrónica", "Electronics"]:
            if sale_price <= 400:
                fees = (sale_price * 0.069) + fixed_fee
            else:
                fees = (400 * 0.069) + ((sale_price - 400) * 0.02) + fixed_fee
        else:
            fees = (sale_price * 0.119) + fixed_fee
        if seller_type == "Business" and vat_registered == "No":
            fees *= 1.20

    elif region == "🇵🇹 Portugal (€)":
        fixed_fee = 0.35
        if category in ["Calçado Esportivo", "Sneakers"]:
            return sale_price * 0.08 if sale_price >= 150 else (sale_price * 0.136) + fixed_fee
        elif category in ["Relógios", "Watches"]:
            return (sale_price * 0.065) if sale_price >= 2000 else (sale_price * 0.15) + fixed_fee
        elif category in ["Guitarras e Baixos", "Guitars & Basses"]:
            return (sale_price * 0.067) + fixed_fee
        elif category in ["Livros/Mídia", "Books/Media"]:
            return (sale_price * 0.153) + fixed_fee
        elif category in ["Colecionáveis", "Collectibles"]:
            return (sale_price * 0.1325) + fixed_fee
        elif category in ["Eletrónica", "Electronics", "Tech"]:
            return (sale_price * 0.09) + fixed_fee
        elif category in ["Health & Beauty", "Saúde & Beleza"]:
            return (sale_price * 0.136) + fixed_fee
        else:
            return (sale_price * 0.136) + fixed_fee
    return fees


# ==========================================
# 🛡️ FILTRO DE CONDIÇÃO (GUILHOTINA)
# ==========================================

HARD_REJECT = [
    "for parts", "for part", "not working", "broken", "faulty", "defective",
    "spares or repair", "spares and repair", "parts only", "repair only",
    "non functional", "does not work", "don't work", "damaged", "cracked",
    "para peças", "avariado", "estragado", "partido", "defeito", "não funciona"
]
LIKELY_INCOMPLETE = [
    "missing", "no battery", "no charger", "no box", "no cable", "no cables",
    "no controller", "no remote", "no power supply", "no psu", "no accessories",
    "without charger", "without battery", "without box", "without accessories",
    "unit only", "console only", "tablet only", "device only",
    "em falta", "falta", "sem bateria", "sem carregador", "sem caixa"
]
AVOID_INFLATION = [
    "console", "consola", "bundle", "lot ", "lote", "joblot",
    "set of", "graded", "wata", "vga", "ukg", "pcgs"
]

def contains_word(text, word):
    return re.search(r'\b' + re.escape(word) + r'\b', text) is not None

def item_passa_filtro(titulo_ebay, condicao_item, nome_pesquisado=""):
    titulo = titulo_ebay.lower()
    
    # Rejeitar itens que inflacionam (bundles, lotes, graded)
    if any(contains_word(titulo, word) for word in AVOID_INFLATION):
        # Permitir se o próprio produto pesquisado contiver essa palavra (ex: "Console X")
        if nome_pesquisado:
            n = nome_pesquisado.lower()
            if not any(contains_word(n, word) for word in AVOID_INFLATION):
                return False
    
    if condicao_item == "Parts":
        POSITIVE = ["complete", "fully working", "full set", "all accessories", "includes charger", "includes box"]
        NEW_KEYWORDS = ["sealed", "bnib", "nib", "unopened", "brand new", "factory sealed"]
        if any(contains_word(titulo, word) for word in POSITIVE + NEW_KEYWORDS):
            return False
        return True
    
    elif condicao_item == "Brand New":
        NOT_NEW = ["used", "pre-owned", "preowned", "open box", "loose", "built", "played",
                   "no box", "without box", "usado", "montado", "sem caixa"]
        if any(contains_word(titulo, word) for word in HARD_REJECT + LIKELY_INCOMPLETE + NOT_NEW):
            return False
        return True
    
    else:  # Used
        if any(contains_word(titulo, word) for word in HARD_REJECT + LIKELY_INCOMPLETE):
            return False
        return True


# ==========================================
# 🤖 MOTOR PRINCIPAL: GEMINI + EBAY
# ==========================================

def analisar_imagem_json(image, custo, objetivo, sabe_custo, condicao):
    """
    Pipeline completo: Visão → Identificação → eBay multi-query → Pureza estatística → Cálculo
    """
    try:
        # --- PASSO 1: IDENTIFICAÇÃO ULTRA-PRECISA COM GEMINI ---
        prompt_id = f"""
        You are an expert resale item identifier and eBay listing specialist.
        
        Analyze this image with extreme precision and extract:
        
        1. **PRODUCT NAME**: Exact commercial name. Include:
           - Brand (mandatory)
           - Model name/number
           - Color/colorway (if relevant for pricing, e.g., sneakers)
           - Capacity/Size for liquids, cosmetics, perfumes (e.g., 50ml, 100ml, 1.7 oz)
           - Edition (Special Edition, Limited, etc.) if clearly visible
           - Generation/Year if clearly visible (e.g., iPhone 14, PS5)
           - DO NOT include: "no barcode", barcode numbers, condition descriptions
        
        2. **EBAY SEARCH QUERY**: The optimal search string to find this exact item on eBay.
           - Use the most common way buyers search for it
           - Include brand + model + key variant
           - Max 8 words
           - Example: "Nike Air Max 90 White Black" or "Apple iPhone 13 128GB"
        
        3. **CATEGORY**: Classify strictly as one of:
           "Sneakers", "Watches", "Electronics", "Guitars & Basses", "Books/Media", 
           "Collectibles", "Health & Beauty", "Others"
        
        4. **CONFIDENCE**: Your confidence in the identification (0-100)
        
        5. **NOTES**: Any important detail that affects resale value (e.g., "Limited Edition", "Rare colorway", "Discontinued model")
        
        Respond ONLY in valid JSON:
        {{
          "produto": "Exact Product Name",
          "ebay_query": "optimal ebay search string",
          "categoria": "Category",
          "confianca": 85,
          "notas": "Any relevant notes or empty string"
        }}
        
        Region context: {region} — ensure the product name is in English for better eBay search results.
        """
        
        res_visao = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=[prompt_id, image]
        )
        
        texto_limpo = res_visao.text.replace("```json", "").replace("```", "").strip()
        
        # Extração robusta do JSON (mesmo se a IA adicionar texto extra)
        json_match = re.search(r'\{.*\}', texto_limpo, re.DOTALL)
        if json_match:
            texto_limpo = json_match.group()
        
        try:
            dados_ia = json.loads(texto_limpo)
            nome_item = dados_ia.get("produto", "Unknown Item")
            ebay_query = dados_ia.get("ebay_query", nome_item)  # ← NOVO: query otimizada
            categoria_item = dados_ia.get("categoria", "Others")
            confianca = dados_ia.get("confianca", 50)
            notas_ia = dados_ia.get("notas", "")
        except json.JSONDecodeError:
            # Fallback: usa o texto todo como nome
            nome_item = texto_limpo[:100].strip()
            ebay_query = nome_item
            categoria_item = "Others"
            confianca = 30
            notas_ia = ""

        # --- PASSO 2: PESQUISA EBAY INTELIGENTE (com query otimizada) ---
        token = garantir_token_ebay()
        
        # Usa a ebay_query otimizada pela IA (não o nome completo)
        dados_ebay = buscar_precos_ebay(token, ebay_query, marketplace_id=marketplace_atual)
        item_summaries = dados_ebay.get('itemSummaries', [])
        
        # Se poucos resultados, tenta novamente com o nome completo
        if len(item_summaries) < 5 and ebay_query != nome_item:
            dados_ebay2 = buscar_precos_ebay(token, nome_item, marketplace_id=marketplace_atual)
            items2 = dados_ebay2.get('itemSummaries', [])
            if len(items2) > len(item_summaries):
                item_summaries = items2

        dados_validados = []
        
        for item in item_summaries:
            try:
                titulo_anuncio = item.get('title', '')
                condition_id = str(item.get('conditionId', ''))
                
                # Filtro por condição usando IDs oficiais eBay
                if condicao == "Brand New":
                    if condition_id not in ["1000", "1500", "1750", "2000"]:
                        continue
                elif condicao == "Parts":
                    if condition_id != "7000":
                        continue
                else:  # Used
                    if condition_id in ["7000", "1000", "1500", "1750"]:
                        continue
                
                if not item_passa_filtro(titulo_anuncio, condicao, ebay_query):
                    continue
                
                valor = float(item.get('price', {}).get('value', 0))
                if valor < 3.0:
                    continue
                
                try:
                    opcoes_envio = item.get('shippingOptions', [])
                    custo_envio = float(opcoes_envio[0].get('shippingCost', {}).get('value', 0)) if opcoes_envio else 0.0
                except:
                    custo_envio = 4.50
                
                if custo_envio > 30.0:
                    continue
                
                dados_validados.append({
                    "preco": valor,
                    "envio": custo_envio,
                    "titulo": titulo_anuncio,
                    "condicao_id": condition_id
                })
                
            except:
                continue

        # --- PASSO 3: MOTOR DE PUREZA ESTATÍSTICA V2 ---
        num_amostra = len(dados_validados)
        
        if dados_validados:
            lista_precos = [d["preco"] for d in dados_validados]
            mediana_real = np.median(lista_precos)
            
            # Filtro de chão (suavizado)
            if condicao == "Brand New":
                dados_validados = [d for d in dados_validados if d["preco"] >= (mediana_real * 0.35)]
            else:
                dados_validados = [d for d in dados_validados if d["preco"] >= (mediana_real * 0.20)]
            
            # Filtro de teto (1.8x mediana)
            dados_validados = [d for d in dados_validados if d["preco"] <= (mediana_real * 1.8)]
            
            # Guilhotina de desvio padrão (1.5σ)
            if len(dados_validados) >= 3:
                lista_atualizada = [d["preco"] for d in dados_validados]
                media_bruta = np.mean(lista_atualizada)
                desvio = np.std(lista_atualizada)
                dados_seguros = [d for d in dados_validados if abs(d["preco"] - media_bruta) <= (desvio * 1.5)]
                if dados_seguros:
                    dados_validados = dados_seguros

            if len(dados_validados) >= 2:
                p_medio = np.mean([d["preco"] for d in dados_validados])
                portes_medios = np.mean([d["envio"] for d in dados_validados])
                
                # Estratégia de preço inteligente:
                # Se amostras > 10, podemos ser mais agressivos (90% da média)
                # Se amostras < 5, ser conservador (85% para vender mais rápido)
                fator_preco = 0.92 if len(dados_validados) > 10 else 0.87
                p_venda = p_medio * fator_preco
            else:
                p_medio = p_venda = portes_medios = 0.0
        else:
            p_medio = p_venda = portes_medios = 0.0

        # --- PASSO 4: CÁLCULO DE TAXAS E ESTRATÉGIA ---
        if p_medio > 0:
            comissao_plataforma = calculate_ebay_fees(region, seller_type, vat_registered, categoria_item, p_venda)
            taxas_estimadas = portes_medios + comissao_plataforma
            
            custo_real = 0 if not sabe_custo else custo
            lucro = p_venda - custo_real - taxas_estimadas
            margem_pct = (lucro / p_venda * 100) if p_venda > 0 else 0
            
            # Link eBay com filtro correto
            if region == "🇺🇸 USA ($)":
                dominio = "ebay.com"
            elif region == "🇬🇧 UK (£)":
                dominio = "ebay.co.uk"
            else:
                dominio = "ebay.es"

            mapa_condicao_url = {
                "Brand New": "&LH_ItemCondition=3",
                "Parts": "&LH_ItemCondition=7000",
                "Used": "&LH_ItemCondition=4"
            }
            filtro_condicao = mapa_condicao_url.get(condicao, "&LH_ItemCondition=4")
            query_url = ebay_query.replace(' ', '+')
            link_mercado = f"https://www.{dominio}/sch/i.html?_nkw={query_url}&LH_Sold=1&LH_Complete=1{filtro_condicao}"
            
            # Veredito baseado em margem %
            if lucro < 0:
                cor = "🔴"
            elif margem_pct >= 25 and len(dados_validados) >= 5:
                cor = "🟢"
            elif margem_pct >= 10:
                cor = "🟡"
            else:
                cor = "🔴"

            # Estratégia detalhada
            if not sabe_custo:
                estrategia = (
                    f"Active market ({len(dados_validados)} listings analysed). "
                    f"Suggested price: {currency}{round(p_venda, 2)} | Fees: {currency}{round(taxas_estimadas, 2)}. "
                    f"Any purchase below {currency}{round(p_venda - taxas_estimadas, 2)} will be profitable."
                )
            else:
                if lucro < 0:
                    estrategia = f"❌ Loss of {currency}{abs(round(lucro,2))} ahead! Fees and cost exceed sale value. Need a cheaper source."
                elif margem_pct < 8:
                    estrategia = f"⚠️ Tight margin ({round(margem_pct,1)}%). Only worth it for very fast sales."
                elif margem_pct >= 25 and len(dados_validados) >= 5:
                    estrategia = f"🔥 Excellent deal! {round(margem_pct,1)}% margin on {len(dados_validados)} active listings. Strong market demand."
                else:
                    estrategia = f"👍 Solid deal. {round(margem_pct,1)}% margin, stable market ({len(dados_validados)} listings)."
            
            if notas_ia:
                estrategia += f" | AI Note: {notas_ia}"
            
            if p_venda > 200:
                estrategia += " ⚠️ HIGH VALUE: Always verify special editions on eBay before investing."
                
        else:
            # Plano B: Gemini estima o preço visualmente
            prompt_estimativa = f"""
            I couldn't find enough eBay sales data for "{nome_item}".
            Act as an expert resale appraiser. Look at the image carefully.
            Evaluate: brand prestige, product type, materials, apparent condition, market rarity.
            
            Region: {region} | Currency: {currency}
            
            Give a realistic eBay selling price estimate and confidence level.
            
            Respond ONLY in JSON:
            {{"preco": X, "justificativa": "reason for this estimate", "confianca_estimativa": 70}}
            """
            
            try:    
                res_estimativa = client.models.generate_content(
                    model='gemini-2.0-flash', 
                    contents=[prompt_estimativa, image]
                )
                texto_json = res_estimativa.text.replace("```json", "").replace("```", "").strip()
                json_match = re.search(r'\{.*\}', texto_json, re.DOTALL)
                if json_match:
                    texto_json = json_match.group()
                dados_est = json.loads(texto_json)
                
                p_venda = float(dados_est.get("preco", 0))
                justificativa = dados_est.get("justificativa", "Estimated from visual inspection.")
                
                p_medio = p_venda
                portes_medios = 4.50
                comissao_plataforma = p_venda * 0.13
                taxas_estimadas = portes_medios + comissao_plataforma
                
                custo_real = 0 if not sabe_custo else custo
                lucro = p_venda - custo_real - taxas_estimadas
                
                dominio = "ebay.co.uk" if region == "🇬🇧 UK (£)" else "ebay.es" if region == "🇵🇹 Portugal (€)" else "ebay.com"
                query_url = nome_item.replace(' ', '+')
                link_mercado = f"https://www.{dominio}/sch/i.html?_nkw={query_url}"
                
                cor = "🔮"  # Roxo = estimativa AI
                if lucro < 0:
                    cor = "🔴"
                elif lucro > 15:
                    cor = "🟢"
                
                estrategia = (
                    f"⚠️ No eBay sales data found. AI visual estimate: {justificativa} "
                    f"| Please verify on eBay before purchasing."
                )
                
            except Exception as e:
                p_medio = p_venda = lucro = taxas_estimadas = 0
                dominio = "ebay.co.uk" if region == "🇬🇧 UK (£)" else "ebay.es" if region == "🇵🇹 Portugal (€)" else "ebay.com"
                link_mercado = f"https://www.{dominio}/sch/i.html?_nkw={nome_item.replace(' ', '+')}"
                cor = "⚪"
                estrategia = "Could not find eBay data or estimate price. Try with a clearer photo."

        return {
            "produto": nome_item,
            "ebay_query": ebay_query,
            "categoria": categoria_item,
            "confianca_ia": confianca,
            "preco_medio": round(p_medio, 2),
            "sugestao_venda": round(p_venda, 2),
            "taxas_estimadas": round(taxas_estimadas, 2),
            "lucro_estimado": round(lucro, 2),
            "link_pesquisa": link_mercado,
            "estrategia_base": estrategia,
            "veredito_cor": cor,
            "num_amostra": num_amostra if 'num_amostra' in dir() else 0
        }

    except Exception as e:
        return {
            "produto": "Read Error",
            "estrategia_base": f"Technical Error: {str(e)}",
            "veredito_cor": "🔴",
            "preco_medio": 0, "sugestao_venda": 0, "taxas_estimadas": 0, "lucro_estimado": 0
        }


# ==========================================
# 💬 CHAT SESSION COM CONTEXTO RICO
# ==========================================

def criar_chat_session(dados_completos):
    if modo_simulacao:
        return "simulacao"
    
    nome = dados_completos.get('produto', 'Item')
    preco_medio = dados_completos.get('preco_medio', 0)
    sugestao = dados_completos.get('sugestao_venda', 0)
    lucro = dados_completos.get('lucro_estimado', 0)
    estrategia = dados_completos.get('estrategia_base', '')
    veredito = dados_completos.get('veredito_cor', '⚪')
    categoria = dados_completos.get('categoria', 'Others')
    confianca = dados_completos.get('confianca_ia', 50)
    num_amostra = dados_completos.get('num_amostra', 0)

    contexto_especialista = f"""
    You are an elite Resale & Arbitrage Consultant with 15+ years of experience in eBay, 
    Vinted, Depop, and general resale markets. You are concise, data-driven, and always 
    give actionable advice.
    
    You have just analyzed this item:
    - PRODUCT: {nome}
    - CATEGORY: {categoria}
    - AI IDENTIFICATION CONFIDENCE: {confianca}%
    - MARKET DATA: Based on {num_amostra} eBay listings
    - AVERAGE MARKET PRICE: {currency}{preco_medio}
    - SUGGESTED SELLING PRICE: {currency}{sugestao}
    - ESTIMATED FEES: {currency}{dados_completos.get('taxas_estimadas', 0)}
    - NET PROFIT ESTIMATE: {currency}{lucro}
    - VERDICT: {veredito}
    - STRATEGY NOTES: {estrategia}
    - REGION: {region}
    
    YOUR ROLE IN THIS CONVERSATION:
    1. Explain the pricing strategy clearly (why this price? fast sale vs max profit?)
    2. If confidence < 60%, warn to verify the identification manually on eBay
    3. Suggest the best platforms to sell (eBay, Vinted, Depop, Facebook Marketplace, etc.)
    4. Give tips on how to write a great listing title and description
    5. Advise on photography tips for this type of item
    6. If verdict is 🔴 (loss), suggest alternatives (where to source cheaper, etc.)
    7. Always back your advice with numbers from the analysis above
    
    Be concise. Use bullet points when listing multiple tips. Max 3-4 sentences per response unless asked for more detail.
    """
    
    st.session_state.chat = client.chats.create(
        model='gemini-2.0-flash',
        history=[
            types.Content(role="user", parts=[types.Part.from_text(text=contexto_especialista)]),
            types.Content(role="model", parts=[types.Part.from_text(
                text=f"Understood. I'm ready to help maximize your profit on **{nome}**. What would you like to know?"
            )])
        ]
    )
    return st.session_state.chat


# ==========================================
# 🔐 INICIALIZAÇÃO DE SESSION STATE
# ==========================================

if "email_logado" not in st.session_state:
    st.session_state.email_logado = None
if "single_result" not in st.session_state: 
    st.session_state.single_result = None
if "chat_history_single" not in st.session_state: 
    st.session_state.chat_history_single = []
if "chat_session_single" not in st.session_state: 
    st.session_state.chat_session_single = None
if "bulk_results" not in st.session_state: 
    st.session_state.bulk_results = []
if "bulk_images" not in st.session_state: 
    st.session_state.bulk_images = {}
if "chat_history_bulk" not in st.session_state: 
    st.session_state.chat_history_bulk = []
if "chat_session_bulk" not in st.session_state: 
    st.session_state.chat_session_bulk = None
if "current_bulk_item" not in st.session_state: 
    st.session_state.current_bulk_item = None
if "historico_conversas" not in st.session_state: 
    st.session_state.historico_conversas = []
if "id_conversa_ativa" not in st.session_state: 
    st.session_state.id_conversa_ativa = None


# ==========================================
# ⚙️ SIDEBAR — PAINEL DO UTILIZADOR
# ==========================================

with st.sidebar:
    st.markdown("---")
    if st.session_state.email_logado:
        st.success(f"👤 {st.session_state.email_logado}")
        if st.session_state.email_logado in ADMINS:
            st.metric(label="Plan", value="👑 ADMIN / Unlimited")
        else:
            saldo_atual = obter_saldo_visual(st.session_state.email_logado)
            st.metric(label="Credits Today", value=f"{saldo_atual} / 1")
        if st.button("🚪 Exit / Change Account"):
            st.session_state.email_logado = None
            st.rerun()
    else:
        st.warning("No user logged in.")
    st.divider()
    
    # Mini-glossário do veredito
    st.markdown("**Legend:**")
    st.markdown("🟢 Profitable | 🟡 Break-even | 🔴 Loss | 🔮 AI Estimate")


# ==========================================
# 📱 INTERFACE PRINCIPAL
# ==========================================

st.title("💎 Valurise")
st.caption("AI-Powered Resale Intelligence Platform")

# LOGIN DO UTILIZADOR (email)
if not st.session_state.email_logado:
    st.info("👋 You are invited to test the Valurise prototype.")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        email_input = st.text_input("Email (to create your account):")
        termos = st.checkbox("I accept to participate in the Beta test and understand that AI may make mistakes.")
    with col2:
        st.write("")
        st.write("")
        if st.button("Access Beta", type="primary"):
            if not termos:
                st.warning("You must accept the terms to test.")
            elif "@" not in email_input:
                st.warning("Invalid email.")
            else:
                st.session_state.email_logado = email_input
                st.rerun()

    with st.expander("ℹ️ About This Prototype"):
        st.markdown("""
        **What is this?** A prototype for testing AI-powered resale intelligence.
        
        **Your data:** Email used only for your account. Never sold or shared.
        
        **Disclaimer:** Values are AI estimates. Always verify before selling.
        """)
    st.stop()

st.sidebar.write(f"👤 **{st.session_state.email_logado}**")


# ==========================================
# 📑 TABS
# ==========================================

aba1, aba2, aba3, aba_historico = st.tabs([
    "🔍 Single Analysis", 
    "📦 Bulk Scan", 
    "📰 Market News", 
    "📜 History"
])


# ==========================================
# ABA 1: ANÁLISE INDIVIDUAL
# ==========================================

with aba1:
    col_input, col_res = st.columns([1, 2])
    
    with col_input:
        st.markdown("### 📸 Item Details")
        objetivo_single = st.radio("Goal?", ["Sell", "Buy"], horizontal=True, key="obj_single_final")
        foto_single = st.file_uploader("Upload Photo", type=["jpg", "jpeg", "png", "webp"], key="single_up_final")
        
        sabe_custo_single = not st.checkbox("I don't know the item cost", key="check_custo_single")
        custo_single = st.number_input(
            f"Purchase Cost ({currency})", 
            min_value=0.0, step=1.0, 
            key="single_cost_final", 
            disabled=not sabe_custo_single
        )
        
        condicao_single = st.selectbox(
            "Item Condition", 
            ["Used (Complete/Working)", "Brand New (Sealed)", "Incomplete / For Parts"], 
            key="cond_single"
        )
        
        if condicao_single == "Brand New (Sealed)": 
            cond_codigo_single = "Brand New"
        elif condicao_single == "Incomplete / For Parts": 
            cond_codigo_single = "Parts"
        else: 
            cond_codigo_single = "Used"

        btn_analyze = st.button("🚀 Analyse Item", type="primary", use_container_width=True)
        
        if btn_analyze:
            if not foto_single:
                st.warning("Please upload a photo first.")
            else:
                if trava_seguranca_global():
                    st.error("🛑 Daily system limit reached (1400/1500). Try again tomorrow!")
                    st.stop()

                foto_single.seek(0)
                img_bruta = PIL.Image.open(foto_single)
                img = comprimir_imagem(img_bruta)
                
                pode_avancar, saldo = gerir_creditos(st.session_state.email_logado)
                
                if modo_simulacao:
                    with st.spinner("Simulating AI analysis..."):
                        supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()
                        dados = analisar_imagem_json(img, custo_single, objetivo_single, sabe_custo_single, cond_codigo_single)
                        dados['id_unico'] = time.time()
                        st.session_state.single_result = dados
                else:
                    if pode_avancar:
                        with st.spinner(f"🔍 Identifying item... then searching eBay... (Credits: {saldo})"):
                            supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()
                            dados = analisar_imagem_json(img, custo_single, objetivo_single, sabe_custo_single, cond_codigo_single)
                            
                            if dados and "Read Error" not in dados.get("produto", ""):
                                guardar_no_historico(dados, objetivo_single, st.session_state.email_logado)
                                gastar_credito(st.session_state.email_logado)
                            
                            dados['id_unico'] = time.time()
                            st.session_state.single_result = dados
                    else:
                        st.error("❌ No credits remaining. Upgrade to PRO for unlimited analyses.")
                        st.link_button("💎 Upgrade to PRO — 9.99/month", "https://tuolinkdostripe.com", use_container_width=True)

    # --- RESULTADOS ---
    if st.session_state.single_result:
        dados = st.session_state.single_result
        
        texto_resumo = f"""**{dados['veredito_cor']} {dados['produto']}**
💰 **Avg Price:** {currency}{dados.get('preco_medio', 0)}
🚀 **Target Price:** {currency}{dados.get('sugestao_venda', 0)}
💸 **Est. Fees:** {currency}{dados.get('taxas_estimadas', 0)}
💶 **Net Profit:** {currency}{dados.get('lucro_estimado', 0)}
📊 **Strategy:** {dados.get('estrategia_base', '')}
"""
        
        if "ultimo_id_salvo" not in st.session_state or st.session_state.ultimo_id_salvo != dados.get('id_unico'):
            if foto_single:
                foto_single.seek(0)
                imagem_aberta = PIL.Image.open(foto_single)
            else:
                imagem_aberta = None

            st.session_state.chat_history_single = []
            st.session_state.chat_session_single = criar_chat_session(dados)
            primeira_resposta = (
                f"Hello! I've analyzed **{dados.get('produto', 'this item')}** "
                f"across eBay {marketplace_atual}. "
                f"Verdict: **{dados.get('veredito_cor')}** | "
                f"Target price: **{currency}{dados.get('sugestao_venda', 0)}** | "
                f"Net profit: **{currency}{dados.get('lucro_estimado', 0)}**. "
                f"What would you like to know?"
            )
            st.session_state.chat_history_single.append({"role": "assistant", "content": primeira_resposta})
            
            nova_sessao = {
                "id": dados.get('id_unico'), 
                "titulo": dados['produto'], 
                "imagem": imagem_aberta, 
                "dados_analise": dados, 
                "resumo": texto_resumo, 
                "historico_chat": st.session_state.chat_history_single
            }
            st.session_state.historico_conversas.insert(0, nova_sessao)
            st.session_state.ultimo_id_salvo = dados.get('id_unico')
            st.session_state.id_conversa_ativa = dados.get('id_unico')

        with col_res:
            if foto_single:
                foto_single.seek(0)
                st.image(foto_single, width=220)
            
            # Cards de métricas
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Avg Price", f"{currency}{dados.get('preco_medio', 0)}")
            m2.metric("Target Price", f"{currency}{dados.get('sugestao_venda', 0)}")
            m3.metric("Est. Fees", f"{currency}{dados.get('taxas_estimadas', 0)}")
            m4.metric("Net Profit", f"{currency}{dados.get('lucro_estimado', 0)}")
            
            # Veredito e estratégia
            cor = dados.get('veredito_cor', '⚪')
            if cor == "🟢":
                st.success(f"**{cor} PROFITABLE** — {dados.get('estrategia_base', '')}")
            elif cor == "🟡":
                st.warning(f"**{cor} MARGINAL** — {dados.get('estrategia_base', '')}")
            elif cor == "🔴":
                st.error(f"**{cor} LOSS** — {dados.get('estrategia_base', '')}")
            else:
                st.info(f"**{cor} AI ESTIMATE** — {dados.get('estrategia_base', '')}")
            
            # Link eBay
            if dados.get('link_pesquisa'):
                st.link_button("🔗 Verify on eBay (Sold Listings)", dados['link_pesquisa'])
            
            # Confiança da IA
            confianca = dados.get('confianca_ia', 0)
            if confianca > 0:
                cor_conf = "green" if confianca >= 75 else "orange" if confianca >= 50 else "red"
                st.markdown(f"🧠 **AI Identification Confidence:** :{cor_conf}[{confianca}%]")
            
            st.write("---")
            
            # Chat
            container_chat = st.container(height=380)
            with container_chat:
                for msg in st.session_state.chat_history_single:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])

            if prompt := st.chat_input("Ask about this item, pricing, or selling strategy...", key="chat_input_unico"):
                st.session_state.chat_history_single.append({"role": "user", "content": prompt})
                with container_chat:
                    with st.chat_message("user"):
                        st.markdown(prompt)
                    with st.chat_message("assistant"):
                        if modo_simulacao:
                            resp = f"[Simulation] Response for: {prompt}"
                        else:
                            try:
                                resp = st.session_state.chat_session_single.send_message(prompt).text
                            except Exception as e:
                                try:
                                    st.session_state.chat_session_single = criar_chat_session(dados)
                                    resp = st.session_state.chat_session_single.send_message(prompt).text
                                except:
                                    resp = "Sorry, connection error. Please try again."
                        st.markdown(resp)
                        st.session_state.chat_history_single.append({"role": "assistant", "content": resp})


# ==========================================
# ABA 2: BULK SCAN
# ==========================================

with aba2:
    st.markdown("### ⚙️ Configure Batch")
    modo_geral = st.radio(
        "What is this batch?", 
        ["🛒 All for Buying", "🏠 All for Selling", "🔀 Mixed (Decide 1 by 1)"], 
        horizontal=True
    )
    fotos_bulk = st.file_uploader(
        "Upload Photos (multiple)", 
        type=["jpg", "jpeg", "png", "webp"], 
        accept_multiple_files=True, 
        key="bulk_up"
    )
    
    if fotos_bulk:
        if "tabela_base" not in st.session_state or len(st.session_state.tabela_base) != len(fotos_bulk):
            dados_iniciais = []
            for f in fotos_bulk:
                img_preview = obter_base64_imagem(f)
                dados_iniciais.append({
                    "Preview": img_preview,
                    "File": f.name,
                    f"Cost ({currency})": 0.0,
                    "Unknown Cost": False,
                    "Condition": "Used",
                    "Action": "Sell"
                })
            st.session_state.tabela_base = pd.DataFrame(dados_iniciais)
            
        col_config = {
            "Preview": st.column_config.ImageColumn("Image", width="small"),
            "Condition": st.column_config.SelectboxColumn(
                "Condition", width="medium", 
                options=["Used", "Brand New", "Parts"]
            ),
            f"Cost ({currency})": st.column_config.NumberColumn(
                f"Cost ({currency})", min_value=0.0, format=f"%.2f"
            ),
            "Unknown Cost": st.column_config.CheckboxColumn("Unknown Cost")
        }
        
        if "Mixed" in modo_geral:
            col_config["Action"] = st.column_config.SelectboxColumn(
                "Action", width="medium", options=["Sell", "Buy"], required=True
            )
        
        tabela_editada = st.data_editor(
            st.session_state.tabela_base,
            num_rows="dynamic",
            use_container_width=True,
            key="editor_bulk_limpo",
            column_config=col_config
        )

        col_btn1, col_btn2 = st.columns([2, 1])
        with col_btn1:
            btn_bulk = st.button("🚀 Process All Items", type="primary", use_container_width=True)
        with col_btn2:
            st.info(f"📷 {len(fotos_bulk)} items to process")
        
        if btn_bulk:
            if not st.session_state.get('email_logado'):
                st.warning("⚠️ You must be logged in.")
            else:
                st.session_state.bulk_results = []
                st.session_state.bulk_images = {}
                barra = st.progress(0, text="Processing...")
                total_items = len(tabela_editada)
                
                for i, row in tabela_editada.iterrows():
                    if trava_seguranca_global():
                        st.error(f"🛑 Global limit reached. Stopped at item {i+1}.")
                        break

                    pode_avancar, saldo = gerir_creditos(st.session_state.email_logado)
                    if not modo_simulacao and not pode_avancar:
                        st.warning(f"⚠️ Credits exhausted at item {i+1}. Upgrade to PRO.")
                        break

                    nome_fich = row["File"]
                    custo_col = f"Cost ({currency})"
                    custo = float(row.get(custo_col, row.get("Cost", 0.0)))
                    sabe_custo_bulk = not row.get("Unknown Cost", False)
                    
                    escolha_tabela = row.get("Condition", "Used")
                    if escolha_tabela == "Brand New": 
                        cond_codigo_bulk = "Brand New"
                    elif escolha_tabela == "Parts": 
                        cond_codigo_bulk = "Parts"
                    else: 
                        cond_codigo_bulk = "Used"
                    
                    if "Buying" in modo_geral: 
                        objetivo_final = "Buy"
                    elif "Selling" in modo_geral: 
                        objetivo_final = "Sell"
                    else: 
                        objetivo_final = row.get("Action", "Sell")

                    foto_real = next((f for f in fotos_bulk if f.name == nome_fich), None)
                    
                    if foto_real:
                        if i > 0:
                            time.sleep(2)  # Delay para evitar rate limiting
                        
                        foto_real.seek(0)
                        img_bruta = PIL.Image.open(foto_real)
                        img = comprimir_imagem(img_bruta)
                        st.session_state.bulk_images[nome_fich] = img
                        
                        barra.progress((i + 0.5) / total_items, text=f"🔍 Analysing {nome_fich}...")
                        
                        # Retry logic
                        tentativas = 0
                        sucesso = False
                        dados = {}

                        while tentativas < 3 and not sucesso:
                            if not modo_simulacao:
                                supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()
                            
                            dados = analisar_imagem_json(img, custo, objetivo_final, sabe_custo_bulk, cond_codigo_bulk)
                            
                            if "429" in str(dados) or "Resource exhausted" in str(dados.get("estrategia_base", "")):
                                tentativas += 1
                                wait = 10 * tentativas
                                st.warning(f"⏳ Rate limit. Retry {tentativas}/3 for '{nome_fich}'. Waiting {wait}s...")
                                time.sleep(wait)
                            elif "Read Error" in dados.get("produto", ""):
                                st.error(f"❌ Error in {nome_fich}: {dados.get('estrategia_base')}")
                                break
                            else:
                                sucesso = True
                                if not modo_simulacao:
                                    gastar_credito(st.session_state.email_logado)

                        if sucesso:
                            st.session_state.bulk_results.append({
                                "File": nome_fich,
                                f"Cost ({currency})": f"{currency}{custo}",
                                "Item": dados.get('produto', 'Unknown'),
                                "Verdict": dados.get('veredito_cor', '🟡'),
                                f"Avg Price ({currency})": f"{currency}{dados.get('preco_medio', 0)}",
                                f"Target Price ({currency})": f"{currency}{dados.get('sugestao_venda', 0)}",
                                f"Est. Fees ({currency})": f"{currency}{dados.get('taxas_estimadas', 0)}",
                                f"Net Profit ({currency})": f"{currency}{dados.get('lucro_estimado', 0)}",
                                "AI Confidence": f"{dados.get('confianca_ia', 0)}%",
                                "Strategy": dados.get('estrategia_base'),
                                "Market Link": dados.get('link_pesquisa', ''),
                                "Raw": dados
                            })
                            guardar_no_historico(dados, objetivo_final, st.session_state.email_logado)
                        
                        barra.progress((i + 1) / total_items, text=f"✅ Done: {nome_fich}")
                
                if st.session_state.bulk_results:
                    st.success(f"✅ Processing completed! {len(st.session_state.bulk_results)}/{total_items} items analysed.")

    # Resultados do Bulk
    if st.session_state.bulk_results:
        st.divider()
        st.markdown("### 📊 Batch Report")
        
        df_res = pd.DataFrame(st.session_state.bulk_results)
        cols_para_tabela = [c for c in df_res.columns if c != "Raw"]
        st.dataframe(df_res[cols_para_tabela], use_container_width=True)
        
        # Resumo rápido
        total_profit = sum(
            float(r.get(f"Net Profit ({currency})", f"{currency}0").replace(currency, "").replace(",", ".") or 0)
            for r in st.session_state.bulk_results
        )
        verdes = sum(1 for r in st.session_state.bulk_results if r.get("Verdict") == "🟢")
        
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("Total Items", len(st.session_state.bulk_results))
        col_s2.metric("Profitable Items 🟢", verdes)
        col_s3.metric(f"Total Est. Profit ({currency})", f"{currency}{round(total_profit, 2)}")
        
        try:
            excel_data = converter_para_excel(df_res)
            st.download_button(
                "📥 Download Excel Report", 
                excel_data, 
                "valurise_bulk_report.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"⚠️ Excel error: {e}")
        
        st.write("---")
        
        # Chat sobre item específico do bulk
        opcoes = [row["File"] for row in st.session_state.bulk_results]
        if opcoes:
            escolha = st.selectbox("💬 Chat about which item?", opcoes, key="seletor_bulk")
            
            if escolha != st.session_state.current_bulk_item:
                st.session_state.current_bulk_item = escolha
                st.session_state.chat_history_bulk = []
                item_dados = next(r for r in st.session_state.bulk_results if r["File"] == escolha)
                img_sel = st.session_state.bulk_images.get(escolha)
                if img_sel:
                    st.session_state.chat_session_bulk = criar_chat_session(item_dados['Raw'])
                    nome_prod = item_dados['Item']
                    veredito = item_dados['Verdict']
                    boas_vindas = (
                        f"👋 Ready to discuss **{nome_prod}** {veredito}. "
                        f"Target: **{item_dados.get(f'Target Price ({currency})', 'N/A')}** | "
                        f"Profit: **{item_dados.get(f'Net Profit ({currency})', 'N/A')}**. "
                        f"What do you want to know?"
                    )
                    st.session_state.chat_history_bulk.append({"role": "assistant", "content": boas_vindas})

            container_chat_bulk = st.container(height=380)
            with container_chat_bulk:
                for msg in st.session_state.chat_history_bulk:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])
            
            if prompt_bulk := st.chat_input("Ask about this item...", key="chat_in_bulk"):
                st.session_state.chat_history_bulk.append({"role": "user", "content": prompt_bulk})
                with container_chat_bulk:
                    with st.chat_message("user"):
                        st.markdown(prompt_bulk)
                    with st.chat_message("assistant"):
                        try:
                            resp = st.session_state.chat_session_bulk.send_message(prompt_bulk).text
                        except Exception as e:
                            try:
                                item_dados = next(r for r in st.session_state.bulk_results if r["File"] == escolha)
                                st.session_state.chat_session_bulk = criar_chat_session(item_dados['Raw'])
                                resp = st.session_state.chat_session_bulk.send_message(prompt_bulk).text
                            except:
                                resp = "Connection error. Please try again."
                        st.markdown(resp)
                        st.session_state.chat_history_bulk.append({"role": "assistant", "content": resp})
                        st.rerun()


# ==========================================
# ABA 3: NOTÍCIAS / MARKET RADAR
# ==========================================

with aba3:
    st.markdown("### 📈 Market Radar — Trends & Opportunities")
    st.write("Stay ahead of price changes and weekly tips to maximize profit.")
    st.divider()

    try:
        response = supabase.table("noticias").select("*").order("created_at", desc=True).limit(20).execute()
        lista_noticias = response.data

        if lista_noticias:
            for news in lista_noticias:
                with st.container(border=True):
                    col_texto, col_img = st.columns([3, 1])
                    with col_texto:
                        st.subheader(news['titulo'])
                        st.caption(f"📅 {news['created_at'][:10]} | 🏷️ {news.get('categoria', 'General')}")
                        st.markdown(news['conteudo'])
                    with col_img:
                        if news.get('imagem_url'):
                            st.image(news['imagem_url'], use_container_width=True)
                        else:
                            st.markdown("# 🗞️")
        else:
            st.info("No news published this week yet. Come back soon!")

    except Exception as e:
        st.error("Error loading news.")


# ==========================================
# ABA HISTÓRICO
# ==========================================

with aba_historico:
    st.markdown("### 📜 Your Analysis History")
    
    try:
        res = supabase.table("historico_scans").select("*")\
            .eq("email", st.session_state.email_logado)\
            .order("created_at", desc=True)\
            .execute()
        
        if res.data:
            df_hist = pd.DataFrame(res.data)
            
            df_display = df_hist[[
                "cor", "produto", "preco_medio", "sugestao_venda",
                "taxas_estimadas", "lucro_estimado", "objetivo", "estrategia", "link_mercado"
            ]]
            
            # Mini stats
            total_scans = len(df_hist)
            lucros = pd.to_numeric(df_hist.get("lucro_estimado", pd.Series([])), errors='coerce').dropna()
            avg_profit = lucros.mean() if len(lucros) > 0 else 0
            
            hs1, hs2, hs3 = st.columns(3)
            hs1.metric("Total Scans", total_scans)
            hs2.metric(f"Avg Estimated Profit ({currency})", f"{currency}{round(avg_profit, 2)}")
            hs3.metric("Items Profitable 🟢", len(df_hist[df_hist.get("cor", "") == "🟢"]) if "cor" in df_hist else "—")
            
            st.dataframe(
                df_display,
                column_config={
                    "cor": "Verdict",
                    "produto": "Item Name",
                    "preco_medio": st.column_config.NumberColumn(f"Avg Price", format=f"%.2f"),
                    "sugestao_venda": st.column_config.NumberColumn(f"Target Price", format=f"%.2f"),
                    "taxas_estimadas": st.column_config.NumberColumn(f"Est. Fees", format=f"%.2f"),
                    "lucro_estimado": st.column_config.NumberColumn(f"Net Profit", format=f"%.2f"),
                    "link_mercado": st.column_config.LinkColumn("eBay Link"),
                    "estrategia": "Strategy",
                    "objetivo": "Goal"
                },
                use_container_width=True,
                hide_index=True
            )
            
            if st.button("🗑️ Clear All History", type="secondary"):
                supabase.table("historico_scans").delete().eq("email", st.session_state.email_logado).execute()
                st.success("🧹 History cleared!")
                time.sleep(1)
                st.rerun()
        else:
            st.info("No analyses yet. Start scanning to populate this table!")
            
    except Exception as e:
        st.error(f"Error loading history: {e}")


mostrar_rodape_legal()