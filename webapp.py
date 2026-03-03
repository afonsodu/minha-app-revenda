import streamlit as st
import PIL.Image
import json
import time
import pandas as pd
import io
from supabase import create_client, Client
from datetime import datetime
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
# 🎨 CSS CIRÚRGICO — Apenas o que não quebra Streamlit
# Regra de ouro: NUNCA tocar em data-testid="stDataFrame" nem em tabelas
# ==========================================
st.markdown("""
<style>
/* === FONTE === */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* === FUNDO GERAL === */
.stApp {
    background: linear-gradient(135deg, #0d0d1a 0%, #141428 100%) !important;
    font-family: 'Inter', sans-serif !important;
}

/* === SIDEBAR === */
[data-testid="stSidebar"] {
    background: #111122 !important;
    border-right: 1px solid rgba(120, 60, 220, 0.25) !important;
}

/* === HEADER STREAMLIT (esconder barra laranja) === */
[data-testid="stHeader"] {
    background: transparent !important;
    height: 0px !important;
}

/* === TÍTULOS === */
.stApp h1 {
    color: #c084fc !important;
    font-weight: 700 !important;
}
.stApp h2, .stApp h3 {
    color: #e2e8f0 !important;
}

/* === TABS === */
.stTabs [data-baseweb="tab-list"] {
    background: #1a1a35 !important;
    border-radius: 10px !important;
    padding: 3px !important;
    border: 1px solid rgba(120,60,220,0.3) !important;
}
.stTabs [data-baseweb="tab"] {
    color: #94a3b8 !important;
    border-radius: 8px !important;
    padding: 8px 18px !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #7c3aed, #6d28d9) !important;
    color: #fff !important;
}

/* === BOTÃO PRIMÁRIO === */
.stButton button[kind="primary"] {
    background: linear-gradient(135deg, #7c3aed, #5b21b6) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    box-shadow: 0 4px 15px rgba(124,58,237,0.4) !important;
    transition: transform 0.15s ease !important;
}
.stButton button[kind="primary"]:hover {
    transform: translateY(-2px) !important;
}

/* === BOTÃO SECUNDÁRIO === */
.stButton button[kind="secondary"] {
    background: #1e1e3a !important;
    color: #c084fc !important;
    border: 1px solid rgba(120,60,220,0.4) !important;
    border-radius: 10px !important;
}

/* === ALERTS === */
[data-testid="stAlert"] {
    border-radius: 8px !important;
}

/* === MÉTRICAS === */
[data-testid="stMetric"] {
    background: #1a1a35 !important;
    border: 1px solid rgba(120,60,220,0.25) !important;
    border-radius: 10px !important;
    padding: 12px !important;
}
[data-testid="stMetricValue"] {
    color: #a78bfa !important;
    font-weight: 700 !important;
}
[data-testid="stMetricLabel"] {
    color: #94a3b8 !important;
}

/* === PROGRESS BAR === */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #7c3aed, #a78bfa) !important;
}

/* === CHAT MESSAGES === */
[data-testid="stChatMessage"] {
    background: #1a1a35 !important;
    border: 1px solid rgba(120,60,220,0.2) !important;
    border-radius: 10px !important;
    margin-bottom: 6px !important;
}

/* === FILE UPLOADER === */
[data-testid="stFileUploader"] > div {
    background: #1a1a35 !important;
    border: 2px dashed rgba(120,60,220,0.4) !important;
    border-radius: 10px !important;
}

/* === SCROLLBAR === */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #0d0d1a; }
::-webkit-scrollbar-thumb { background: #7c3aed; border-radius: 3px; }

/* === SIDEBAR TEXT === */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown {
    color: #e2e8f0 !important;
}

/* === CAPTION E TEXTO PEQUENO === */
.stApp .stCaption, .stApp small {
    color: #64748b !important;
}
</style>
""", unsafe_allow_html=True)


# --- CONFIGURAÇÃO REGIÃO ---
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
        st.sidebar.caption("If 'No', eBay charges 20% VAT on fees.")
    else:
        st.sidebar.success("Private sellers: 0% final value fees! 🎉")
elif region == "🇺🇸 USA ($)":
    currency = "$"


# ==========================================
# 🔑 GEMINI CLIENT
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
        st.error(f"Vertex AI error: {e}")

client = st.session_state.get("client")

# ==========================================
# 🗄️ SUPABASE
# ==========================================
url_sb = st.secrets["SUPABASE_URL"]
key_sb = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url_sb, key_sb)

# ==========================================
# VARIÁVEIS GLOBAIS
# ==========================================
modo_simulacao = False
ADMINS = ["afonsocgomesduarte@gmail.com"]

# ==========================================
# 🔒 LOGIN GLOBAL (SENHA)
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
    """Token com cache de 90 minutos."""
    agora = time.time()
    token_ok = (
        'ebay_token' in st.session_state
        and st.session_state.get('ebay_token')
        and (agora - st.session_state.get('ebay_token_ts', 0)) < 5400
    )
    if not token_ok:
        try:
            app_id = st.secrets["EBAY_APP_ID"]
            cert_id = st.secrets["EBAY_CERT_ID"]
            novo = get_ebay_token(app_id, cert_id)
            if novo:
                st.session_state.ebay_token = novo
                st.session_state.ebay_token_ts = agora
            else:
                st.error("Couldn't get eBay token.")
                return None
        except Exception as e:
            st.error(f"eBay keys not found: {e}")
            return None
    return st.session_state.ebay_token

def set_app_icon(icon_path):
    if os.path.exists(icon_path):
        with open(icon_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        st.markdown(f"""<script>
            var l=document.querySelector("link[rel*='icon']")||document.createElement('link');
            l.type='image/png';l.rel='shortcut icon';
            l.href__='data:image/png;base64,{b64}?v=2';
            document.head.appendChild(l);
        </script>""", unsafe_allow_html=True)

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
        supabase.table("historico_scans").insert({
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
        }).execute()
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
    if not email_user: return False, 0
    if email_user in ADMINS: return True, 9999
    try:
        res = supabase.table("users_credits").select("*").eq("email", email_user).execute()
        hoje = datetime.now().date().isoformat()
        if not res.data:
            supabase.table("users_credits").insert({"email": email_user, "creditos": 1, "ultimo_reset": hoje}).execute()
            return True, 1
        d = res.data[0]
        saldo = d.get("creditos", 0)
        if d.get("ultimo_reset") != hoje:
            supabase.table("users_credits").update({"creditos": 1, "ultimo_reset": hoje}).eq("email", email_user).execute()
            return True, 1
        return (True, saldo) if saldo > 0 else (False, 0)
    except Exception as e:
        st.error(f"DB Error: {e}")
        return False, 0

def gastar_credito(email):
    if email in ADMINS: return
    try:
        res = supabase.table("users_credits").select("creditos").eq("email", email).execute()
        if res.data:
            novo = max(0, res.data[0]['creditos'] - 1)
            supabase.table("users_credits").update({"creditos": novo}).eq("email", email).execute()
    except Exception as e:
        print(f"Credit error: {e}")

def converter_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_exp = df.copy()
        if 'Verdict' in df_exp.columns:
            df_exp['Verdict'] = df_exp['Verdict'].astype(str)\
                .str.replace('🟢', 'YES').str.replace('🟡', 'MAYBE').str.replace('🔴', 'NO')
        for col in [f'Cost ({currency})', f'Avg Price ({currency})', f'Target Price ({currency})', f'Est. Fees ({currency})', f'Net Profit ({currency})']:
            if col in df_exp.columns:
                df_exp[col] = pd.to_numeric(df_exp[col].astype(str).str.replace(currency, '').str.replace(',', '.').str.strip(), errors='coerce')
        df_exp.to_excel(writer, index=False, sheet_name='Results')
        wb = writer.book
        ws = writer.sheets['Results']
        fmt_g = wb.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        fmt_y = wb.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C5700'})
        fmt_r = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        try:
            ci = df_exp.columns.get_loc("Verdict")
            ul = len(df_exp) + 1
            ws.conditional_format(1, ci, ul, ci, {'type': 'cell', 'criteria': 'equal to', 'value': '"YES"', 'format': fmt_g})
            ws.conditional_format(1, ci, ul, ci, {'type': 'cell', 'criteria': 'equal to', 'value': '"MAYBE"', 'format': fmt_y})
            ws.conditional_format(1, ci, ul, ci, {'type': 'cell', 'criteria': 'equal to', 'value': '"NO"', 'format': fmt_r})
            ws.set_column(ci, ci, 15)
        except: pass
    return output.getvalue()

def mostrar_rodape_legal():
    st.markdown("---")
    with st.expander("ℹ️ Legal Notice and Disclaimer"):
        st.markdown("""
        **1. Informational Nature:** Valurise is a decision-support tool. Estimates are AI-generated and not financial advice.
        **2. Possibility of Error:** AI can produce inaccurate or outdated information occasionally.
        **3. User Responsibility:** Always verify before any transaction. Valurise is not liable for financial losses.
        *By using this tool, you accept these terms.*
        """)
        st.caption("Powered by Google Gemini AI • Valurise © 2026")


# ==========================================
# 🧮 TAXAS EBAY
# ==========================================

def calculate_ebay_fees(region, seller_type, vat_registered, category, sale_price):
    fees = 0.0
    fixed_fee = 0.0
    if region == "🇺🇸 USA ($)":
        fixed_fee = 0.30
        cat = (category or "").lower()
        if "sneaker" in cat or "calçado" in cat:
            fees = (sale_price * 0.08) if sale_price >= 150 else (sale_price * 0.1325) + fixed_fee
        elif "tech" in cat or "electr" in cat:
            fees = (sale_price * 0.0635) + fixed_fee
        else:
            fees = (sale_price * 0.1325) + fixed_fee

    elif region == "🇬🇧 UK (£)":
        if seller_type == "Private": return 0.0
        fixed_fee = 0.30
        cat = (category or "").lower()
        if "sneaker" in cat or "calçado" in cat:
            fees = (sale_price * 0.07) + fixed_fee if sale_price >= 100 else (sale_price * 0.119) + fixed_fee
        elif "tech" in cat or "electr" in cat:
            fees = (sale_price * 0.069) + fixed_fee if sale_price <= 400 else (400 * 0.069) + ((sale_price - 400) * 0.02) + fixed_fee
        else:
            fees = (sale_price * 0.119) + fixed_fee
        if seller_type == "Business" and vat_registered == "No":
            fees *= 1.20

    elif region == "🇵🇹 Portugal (€)":
        fixed_fee = 0.35
        cat = (category or "").lower()
        if "sneaker" in cat or "calçado" in cat:
            return sale_price * 0.08 if sale_price >= 150 else (sale_price * 0.136) + fixed_fee
        elif "relógio" in cat or "watch" in cat:
            return (sale_price * 0.065) if sale_price >= 2000 else (sale_price * 0.15) + fixed_fee
        elif "guitar" in cat:
            return (sale_price * 0.067) + fixed_fee
        elif "book" in cat or "media" in cat or "livro" in cat:
            return (sale_price * 0.153) + fixed_fee
        elif "collect" in cat or "colecion" in cat:
            return (sale_price * 0.1325) + fixed_fee
        elif "tech" in cat or "electr" in cat:
            return (sale_price * 0.09) + fixed_fee
        elif "health" in cat or "beauty" in cat or "saúde" in cat:
            return (sale_price * 0.136) + fixed_fee
        else:
            return (sale_price * 0.136) + fixed_fee
    return fees


# ==========================================
# 🛡️ FILTROS DE QUALIDADE DE ANÚNCIOS
# ==========================================

HARD_REJECT = [
    "for parts", "not working", "broken", "faulty", "defective",
    "spares or repair", "parts only", "repair only", "non functional",
    "does not work", "damaged", "cracked", "para peças", "avariado",
    "estragado", "partido", "não funciona"
]
LIKELY_INCOMPLETE = [
    "no battery", "no charger", "no box", "no cable", "no controller",
    "no remote", "no power supply", "no accessories", "without charger",
    "without battery", "without box", "unit only", "console only",
    "tablet only", "device only", "sem bateria", "sem carregador", "sem caixa"
]
# Palavras que inflacionam (bundles, lotes, graded)
INFLATION_WORDS = [
    "bundle", "lot ", "lote", "joblot", "set of ", "graded", "wata games",
    "vga graded", "ukg graded", "pcgs", "x2 ", "x3 ", "x4 ", "x5 ",
    "2x ", "3x ", "4x ", "5x ", "pack of", "collection of"
]

def contains_word(text, word):
    return re.search(r'\b' + re.escape(word.strip()) + r'\b', text) is not None

def item_passa_filtro(titulo, condicao, nome_pesquisado=""):
    t = titulo.lower()

    # Rejeitar sempre itens com inflation words (a menos que o produto em si seja um bundle)
    nome_lower = nome_pesquisado.lower()
    for iw in INFLATION_WORDS:
        if iw.strip() in t and iw.strip() not in nome_lower:
            return False

    if condicao == "Parts":
        POSITIVE = ["complete", "fully working", "full set", "includes charger", "includes box", "sealed", "brand new"]
        if any(contains_word(t, w) for w in POSITIVE):
            return False
        return True

    elif condicao == "Brand New":
        NOT_NEW = ["used", "pre-owned", "preowned", "open box", "loose", "played",
                   "no box", "without box", "usado", "montado", "sem caixa", "refurbished"]
        if any(contains_word(t, w) for w in HARD_REJECT + LIKELY_INCOMPLETE + NOT_NEW):
            return False
        return True

    else:  # Used
        if any(contains_word(t, w) for w in HARD_REJECT + LIKELY_INCOMPLETE):
            return False
        return True


# ==========================================
# 🤖 PIPELINE PRINCIPAL: GEMINI + EBAY
# ==========================================

def analisar_imagem_json(image, custo, objetivo, sabe_custo, condicao):
    try:
        # --- PASSO 1: IDENTIFICAÇÃO PRECISA ---
        prompt_id = f"""
        You are an expert resale item identifier. Analyze this image with maximum precision.
        
        Extract:
        1. **PRODUCT NAME**: Full commercial name. Include brand + model + key variant.
           - For electronics: include storage/RAM if visible (e.g. "iPhone 13 128GB Black")
           - For sneakers: include colorway (e.g. "Nike Air Max 90 White Black")
           - For perfumes/cosmetics: include size in ml or oz (e.g. "Chanel No 5 EDP 100ml")
           - For games/toys: include platform or set number (e.g. "LEGO Star Wars 75257")
           - DO NOT include condition, barcode numbers, or "no barcode"
        
        2. **EBAY SEARCH QUERY**: Best 5-7 word search to find SOLD listings of this exact item.
           Think: what would a buyer type on eBay to find this exact product?
           Example: "Nike Air Max 90 White Black UK9" or "iPhone 13 128GB Black Unlocked"
        
        3. **CATEGORY**: One of: Sneakers, Watches, Electronics, Guitars & Basses, Books/Media, Collectibles, Health & Beauty, Others
        
        4. **CONFIDENCE**: 0-100, how confident are you in the identification?
        
        Respond ONLY in valid JSON:
        {{"produto": "...", "ebay_query": "...", "categoria": "...", "confianca": 85}}
        
        Region: {region}. Write all values in English.
        """

        res_visao = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt_id, image]
        )

        texto = res_visao.text.replace("```json", "").replace("```", "").strip()
        json_match = re.search(r'\{.*?\}', texto, re.DOTALL)
        if json_match:
            texto = json_match.group()

        try:
            dados_ia = json.loads(texto)
            nome_item = dados_ia.get("produto", "Unknown Item")
            ebay_query = dados_ia.get("ebay_query", nome_item)
            categoria_item = dados_ia.get("categoria", "Others")
            confianca = dados_ia.get("confianca", 50)
        except json.JSONDecodeError:
            nome_item = texto[:80].strip()
            ebay_query = nome_item
            categoria_item = "Others"
            confianca = 30

        # --- PASSO 2: PESQUISA EBAY (SOLD LISTINGS) ---
        token = garantir_token_ebay()
        
        # Traduzir a condição do utilizador para IDs do eBay antes de chamar a API
        if condicao == "Brand New":
            ebay_cond = "1000|1500|1750|2000"
        elif condicao == "Parts":
            ebay_cond = "7000"
        else:
            ebay_cond = "3000|4000|5000|6000"

        # Passamos o ebay_cond no filter_condition
        dados_ebay = buscar_precos_ebay(token, ebay_query, marketplace_id=marketplace_atual, filter_condition=ebay_cond)
        item_summaries = dados_ebay.get('itemSummaries', [])
        fonte_dados = dados_ebay.get('_source', 'unknown')

        # Se poucos resultados, tenta com nome completo
        if len(item_summaries) < 5:
            dados_ebay2 = buscar_precos_ebay(token, nome_item, marketplace_id=marketplace_atual, filter_condition=ebay_cond)
            items2 = dados_ebay2.get('itemSummaries', [])
            if len(items2) > len(item_summaries):
                item_summaries = items2
                fonte_dados = dados_ebay2.get('_source', 'unknown')

        dados_validados = []

        for item in item_summaries:
            try:
                titulo_anuncio = item.get('title', '')
                condition_id = str(item.get('conditionId', ''))

                # ====================================================
                # FILTRO 1: Condição por ID oficial eBay
                # 1000=New, 1500=New other, 2000=Manufacturer refurb
                # 2500=Seller refurb, 3000=Used, 7000=For parts
                # ====================================================
                if condicao == "Brand New":
                    if condition_id not in ["1000", "1500", "1750", "2000"]:
                        continue
                elif condicao == "Parts":
                    if condition_id != "7000":
                        continue
                else:  # Used
                    # Excluir novo (inflaciona) e partes (deflaciona)
                    if condition_id in ["1000", "1500", "1750", "7000"]:
                        continue
                    # Aceitar: 2000 (refurb), 2500 (seller refurb), 3000 (used), 4000 (very good), 5000 (good), 6000 (acceptable)

                # FILTRO 2: Qualidade do título
                if not item_passa_filtro(titulo_anuncio, condicao, ebay_query):
                    continue

                # FILTRO 3: Preço mínimo realista (evita anúncios de $0.99)
                valor = float(item.get('price', {}).get('value', 0))
                if valor < 5.0:
                    continue

                # FILTRO 4: Envio excessivo (pode ser erro de dados)
                try:
                    opcoes = item.get('shippingOptions', [])
                    custo_envio = float(opcoes[0].get('shippingCost', {}).get('value', 0)) if opcoes else 0.0
                except:
                    custo_envio = 4.50

                if custo_envio > 35.0:
                    continue

                dados_validados.append({
                    "preco": valor,
                    "envio": custo_envio,
                    "titulo": titulo_anuncio
                })

            except:
                continue

        # --- PASSO 3: PUREZA ESTATÍSTICA ROBUSTA ---
        num_amostra_raw = len(dados_validados)

        if dados_validados:
            lista_precos = [d["preco"] for d in dados_validados]

            # A) Mediana como âncora central (resistente a outliers)
            mediana = np.median(lista_precos)

            # B) Filtro IQR (Interquartile Range) — método estatístico padrão
            # Elimina outliers de forma científica sem cortar arbitrariamente
            q1 = np.percentile(lista_precos, 25)
            q3 = np.percentile(lista_precos, 75)
            iqr = q3 - q1

            # Limites: Q1 - 1.5*IQR e Q3 + 1.5*IQR (regra de Tukey)
            lower_bound = max(q1 - 1.5 * iqr, mediana * 0.30)
            upper_bound = q3 + 1.5 * iqr

            dados_filtrados = [d for d in dados_validados if lower_bound <= d["preco"] <= upper_bound]

            if not dados_filtrados:
                dados_filtrados = dados_validados  # fallback

            if len(dados_filtrados) >= 2:
                precos_f = [d["preco"] for d in dados_filtrados]
                # Usar mediana dos filtrados (mais robusta que média para preços)
                p_medio = float(np.median(precos_f))
                portes_medios = float(np.mean([d["envio"] for d in dados_filtrados]))

                # Preço de venda competitivo:
                # - Com muitas amostras (mercado líquido): 5% abaixo da mediana
                # - Com poucas amostras (mercado escasso): na mediana ou ligeiramente acima
                n = len(dados_filtrados)
                if n >= 15:
                    p_venda = p_medio * 0.95  # mercado competitivo, ser ligeiramente mais barato
                elif n >= 7:
                    p_venda = p_medio * 0.97  # mercado normal
                else:
                    p_venda = p_medio * 0.99  # poucas referências, conservador
            else:
                p_medio = p_venda = portes_medios = 0.0
        else:
            p_medio = p_venda = portes_medios = 0.0

        num_amostra = len(dados_validados) if 'dados_filtrados' not in dir() else len(dados_filtrados)

        # --- PASSO 4: TAXAS + ESTRATÉGIA ---
        if p_medio > 0:
            comissao = calculate_ebay_fees(region, seller_type, vat_registered, categoria_item, p_venda)
            taxas_estimadas = portes_medios + comissao
            custo_real = 0 if not sabe_custo else custo
            lucro = p_venda - custo_real - taxas_estimadas
            margem_pct = (lucro / p_venda * 100) if p_venda > 0 else 0

            # Link eBay (sold listings)
            dominios = {"🇺🇸 USA ($)": "ebay.com", "🇬🇧 UK (£)": "ebay.co.uk", "🇵🇹 Portugal (€)": "ebay.es"}
            dominio = dominios.get(region, "ebay.com")
            cond_url = {"Brand New": "&LH_ItemCondition=3", "Parts": "&LH_ItemCondition=7000", "Used": "&LH_ItemCondition=4"}
            filtro_url = cond_url.get(condicao, "&LH_ItemCondition=4")
            q_url = ebay_query.replace(' ', '+')
            link_mercado = f"https://www.{dominio}/sch/i.html?_nkw={q_url}&LH_Sold=1&LH_Complete=1{filtro_url}"

            # Veredito
            if lucro < 0:
                cor = "🔴"
            elif margem_pct >= 20 and num_amostra >= 5:
                cor = "🟢"
            elif margem_pct >= 8:
                cor = "🟡"
            else:
                cor = "🔴"

            # Aviso de fonte de dados
            fonte_label = "✅ Sold listings" if fonte_dados == "sold" else "⚠️ Active listings (no sold data)"

            if not sabe_custo:
                estrategia = (
                    f"{fonte_label} | {num_amostra} refs | "
                    f"Median: {currency}{round(p_medio,2)} → Target: {currency}{round(p_venda,2)} | "
                    f"Fees: {currency}{round(taxas_estimadas,2)} | "
                    f"Buy below {currency}{round(p_venda - taxas_estimadas,2)} to profit."
                )
            else:
                if lucro < 0:
                    estrategia = f"❌ Loss {currency}{abs(round(lucro,2))} | {fonte_label} | {num_amostra} refs | Try sourcing below {currency}{round(p_venda - taxas_estimadas,2)}"
                elif margem_pct < 8:
                    estrategia = f"⚠️ Tight {round(margem_pct,1)}% margin | {fonte_label} | {num_amostra} refs"
                elif margem_pct >= 20:
                    estrategia = f"🔥 Excellent {round(margem_pct,1)}% margin | {fonte_label} | {num_amostra} refs | Strong demand"
                else:
                    estrategia = f"👍 Solid {round(margem_pct,1)}% margin | {fonte_label} | {num_amostra} refs"

            if p_venda > 200:
                estrategia += " | ⚠️ HIGH VALUE: verify edition on eBay before buying."

        else:
            # Plano B: estimativa visual Gemini
            prompt_est = f"""
            No eBay data found for "{nome_item}". 
            As an expert appraiser, estimate a realistic eBay selling price in {currency}.
            Consider: brand, type, materials, rarity, market demand.
            Respond ONLY in JSON: {{"preco": X, "justificativa": "reason"}}
            """
            try:
                res_est = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt_est, image])
                texto_j = res_est.text.replace("```json","").replace("```","").strip()
                jm = re.search(r'\{.*?\}', texto_j, re.DOTALL)
                if jm: texto_j = jm.group()
                d_est = json.loads(texto_j)
                p_venda = float(d_est.get("preco", 0))
                justif = d_est.get("justificativa", "Visual estimate.")
                p_medio = p_venda
                portes_medios = 4.50
                comissao = p_venda * 0.13
                taxas_estimadas = portes_medios + comissao
                custo_real = 0 if not sabe_custo else custo
                lucro = p_venda - custo_real - taxas_estimadas
                dominios = {"🇺🇸 USA ($)": "ebay.com", "🇬🇧 UK (£)": "ebay.co.uk", "🇵🇹 Portugal (€)": "ebay.es"}
                dominio = dominios.get(region, "ebay.com")
                link_mercado = f"https://www.{dominio}/sch/i.html?_nkw={nome_item.replace(' ','+')}"
                cor = "🔮"
                if lucro < 0: cor = "🔴"
                elif lucro > 15: cor = "🟢"
                estrategia = f"⚠️ No eBay data — AI visual estimate: {justif}"
            except Exception as e:
                p_medio = p_venda = lucro = taxas_estimadas = 0
                dominios = {"🇺🇸 USA ($)": "ebay.com", "🇬🇧 UK (£)": "ebay.co.uk", "🇵🇹 Portugal (€)": "ebay.es"}
                dominio = dominios.get(region, "ebay.com")
                link_mercado = f"https://www.{dominio}/sch/i.html?_nkw={nome_item.replace(' ','+')}"
                cor = "⚪"
                estrategia = "No eBay data found and AI couldn't estimate. Try a clearer photo."
                num_amostra = 0

        return {
            "produto": nome_item,
            "ebay_query": ebay_query,
            "categoria": categoria_item,
            "confianca_ia": confianca,
            "fonte_dados": fonte_dados if 'fonte_dados' in dir() else "unknown",
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
            "produto": "Read Error", "estrategia_base": f"Error: {str(e)}",
            "veredito_cor": "🔴", "preco_medio": 0, "sugestao_venda": 0,
            "taxas_estimadas": 0, "lucro_estimado": 0
        }


# ==========================================
# 💬 CHAT SESSION
# ==========================================

def criar_chat_session(dados_completos):
    if modo_simulacao: return "simulacao"
    nome = dados_completos.get('produto', 'Item')
    p_medio = dados_completos.get('preco_medio', 0)
    sugestao = dados_completos.get('sugestao_venda', 0)
    lucro = dados_completos.get('lucro_estimado', 0)
    estrategia = dados_completos.get('estrategia_base', '')
    veredito = dados_completos.get('veredito_cor', '⚪')
    categoria = dados_completos.get('categoria', 'Others')
    confianca = dados_completos.get('confianca_ia', 50)
    num_refs = dados_completos.get('num_amostra', 0)
    fonte = dados_completos.get('fonte_dados', 'unknown')

    ctx = f"""
    You are an elite Resale & Arbitrage Consultant. Be concise and data-driven.
    
    Item analysed:
    - PRODUCT: {nome} | CATEGORY: {categoria} | AI CONFIDENCE: {confianca}%
    - DATA SOURCE: {fonte} ({num_refs} references)
    - MEDIAN MARKET PRICE: {currency}{p_medio}
    - SUGGESTED SELLING PRICE: {currency}{sugestao}
    - ESTIMATED FEES: {currency}{dados_completos.get('taxas_estimadas',0)}
    - NET PROFIT: {currency}{lucro}
    - VERDICT: {veredito}
    - STRATEGY: {estrategia}
    - REGION: {region}
    
    Your role:
    1. Explain the price strategy clearly
    2. If confidence < 60%, warn to verify identification on eBay manually
    3. Suggest best platforms to sell (eBay, Vinted, Depop, Facebook Marketplace)
    4. Give title/description tips for eBay listings
    5. If verdict is 🔴, suggest how to source cheaper or alternative selling venues
    Keep responses concise. Use bullet points for tips.
    """
    st.session_state.chat = client.chats.create(
        model='gemini-2.0-flash',
        history=[
            types.Content(role="user", parts=[types.Part.from_text(text=ctx)]),
            types.Content(role="model", parts=[types.Part.from_text(
                text=f"Ready to help maximize your profit on **{nome}**. What would you like to know?"
            )])
        ]
    )
    return st.session_state.chat


# ==========================================
# 🔐 SESSION STATE
# ==========================================
defaults = {
    "email_logado": None, "single_result": None,
    "chat_history_single": [], "chat_session_single": None,
    "bulk_results": [], "bulk_images": {},
    "chat_history_bulk": [], "chat_session_bulk": None,
    "current_bulk_item": None, "historico_conversas": [],
    "id_conversa_ativa": None
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ==========================================
# ⚙️ SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("---")
    if st.session_state.email_logado:
        st.success(f"👤 {st.session_state.email_logado}")
        if st.session_state.email_logado in ADMINS:
            st.metric("Plan", "👑 ADMIN / Unlimited")
        else:
            st.metric("Credits Today", f"{obter_saldo_visual(st.session_state.email_logado)} / 1")
        if st.button("🚪 Exit / Change Account"):
            st.session_state.email_logado = None
            st.rerun()
    else:
        st.warning("No user logged in.")
    st.divider()
    st.markdown("**Legend:**")
    st.markdown("🟢 Profitable | 🟡 Break-even | 🔴 Loss | 🔮 AI Estimate")


# ==========================================
# 📱 INTERFACE
# ==========================================
st.title("💎 Valurise")
st.caption("AI-Powered Resale Intelligence — eBay Sold Listings Engine")

# EMAIL LOGIN
if not st.session_state.email_logado:
    st.info("👋 You are invited to test the Valurise prototype.")
    col1, col2 = st.columns([3, 1])
    with col1:
        email_input = st.text_input("Email:")
        termos = st.checkbox("I accept the Beta test terms and understand AI may make mistakes.")
    with col2:
        st.write(""); st.write("")
        if st.button("Access Beta", type="primary"):
            if not termos: st.warning("Accept the terms first.")
            elif "@" not in email_input: st.warning("Invalid email.")
            else:
                st.session_state.email_logado = email_input
                st.rerun()
    with st.expander("ℹ️ About"):
        st.markdown("Prototype by an independent developer. Email used only for your account. Values are AI estimates — always verify.")
    st.stop()

st.sidebar.write(f"👤 **{st.session_state.email_logado}**")


# ==========================================
# TABS
# ==========================================
aba1, aba2, aba3, aba_historico = st.tabs([
    "🔍 Single Analysis", "📦 Bulk Scan", "📰 Market News", "📜 History"
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
        custo_single = st.number_input(f"Purchase Cost ({currency})", min_value=0.0, step=1.0, key="single_cost_final", disabled=not sabe_custo_single)
        condicao_single = st.selectbox("Item Condition", ["Used (Complete/Working)", "Brand New (Sealed)", "Incomplete / For Parts"], key="cond_single")
        if condicao_single == "Brand New (Sealed)": cond_codigo_single = "Brand New"
        elif condicao_single == "Incomplete / For Parts": cond_codigo_single = "Parts"
        else: cond_codigo_single = "Used"

        if st.button("🚀 Analyse Item", type="primary", use_container_width=True):
            if not foto_single:
                st.warning("Upload a photo first.")
            else:
                if trava_seguranca_global():
                    st.error("🛑 Daily limit reached. Try again tomorrow.")
                    st.stop()
                foto_single.seek(0)
                img = comprimir_imagem(PIL.Image.open(foto_single))
                pode_avancar, saldo = gerir_creditos(st.session_state.email_logado)
                if pode_avancar or modo_simulacao:
                    with st.spinner(f"🔍 Identifying item + searching eBay sold listings..."):
                        supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()
                        dados = analisar_imagem_json(img, custo_single, objetivo_single, sabe_custo_single, cond_codigo_single)
                        if dados and "Read Error" not in dados.get("produto", ""):
                            guardar_no_historico(dados, objetivo_single, st.session_state.email_logado)
                            gastar_credito(st.session_state.email_logado)
                        dados['id_unico'] = time.time()
                        st.session_state.single_result = dados
                else:
                    st.error("❌ No credits remaining.")
                    st.link_button("💎 Upgrade to PRO — 9.99/month", "https://tuolinkdostripe.com", use_container_width=True)

    if st.session_state.single_result:
        dados = st.session_state.single_result

        if "ultimo_id_salvo" not in st.session_state or st.session_state.ultimo_id_salvo != dados.get('id_unico'):
            st.session_state.chat_history_single = []
            st.session_state.chat_session_single = criar_chat_session(dados)
            primeira_resp = (
                f"Analysed **{dados.get('produto','this item')}** | "
                f"Verdict: **{dados.get('veredito_cor')}** | "
                f"Target: **{currency}{dados.get('sugestao_venda',0)}** | "
                f"Net profit: **{currency}{dados.get('lucro_estimado',0)}**. How can I help?"
            )
            st.session_state.chat_history_single.append({"role": "assistant", "content": primeira_resp})
            if foto_single:
                foto_single.seek(0)
                img_sess = PIL.Image.open(foto_single)
            else:
                img_sess = None
            st.session_state.historico_conversas.insert(0, {
                "id": dados.get('id_unico'), "titulo": dados['produto'],
                "imagem": img_sess, "dados_analise": dados,
                "historico_chat": st.session_state.chat_history_single
            })
            st.session_state.ultimo_id_salvo = dados.get('id_unico')

        with col_res:
            if foto_single:
                foto_single.seek(0)
                st.image(foto_single, width=200)

            # Métricas
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Avg Price", f"{currency}{dados.get('preco_medio',0)}")
            m2.metric("Target Price", f"{currency}{dados.get('sugestao_venda',0)}")
            m3.metric("Est. Fees", f"{currency}{dados.get('taxas_estimadas',0)}")
            m4.metric("Net Profit", f"{currency}{dados.get('lucro_estimado',0)}")

            # Veredito
            cor = dados.get('veredito_cor', '⚪')
            msg_strat = dados.get('estrategia_base', '')
            if cor == "🟢": st.success(f"**{cor} PROFITABLE** — {msg_strat}")
            elif cor == "🟡": st.warning(f"**{cor} MARGINAL** — {msg_strat}")
            elif cor == "🔴": st.error(f"**{cor} LOSS** — {msg_strat}")
            else: st.info(f"**{cor} AI ESTIMATE** — {msg_strat}")

            if dados.get('link_pesquisa'):
                st.link_button("🔗 Verify on eBay (Sold Listings)", dados['link_pesquisa'])

            confianca = dados.get('confianca_ia', 0)
            if confianca:
                cor_c = "green" if confianca >= 75 else "orange" if confianca >= 50 else "red"
                st.markdown(f"🧠 AI Confidence: **:{cor_c}[{confianca}%]** | 📊 References: **{dados.get('num_amostra',0)}** sold")

            st.write("---")

            # CHAT
            container_chat = st.container(height=380)
            with container_chat:
                for msg in st.session_state.chat_history_single:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])

            if prompt := st.chat_input("Ask about pricing, strategy, listing tips...", key="chat_input_unico"):
                st.session_state.chat_history_single.append({"role": "user", "content": prompt})
                with container_chat:
                    with st.chat_message("user"): st.markdown(prompt)
                    with st.chat_message("assistant"):
                        try:
                            resp = st.session_state.chat_session_single.send_message(prompt).text
                        except:
                            try:
                                st.session_state.chat_session_single = criar_chat_session(dados)
                                resp = st.session_state.chat_session_single.send_message(prompt).text
                            except:
                                resp = "Connection error. Please try again."
                        st.markdown(resp)
                        st.session_state.chat_history_single.append({"role": "assistant", "content": resp})


# ==========================================
# ABA 2: BULK
# ==========================================
with aba2:
    st.markdown("### ⚙️ Configure Batch")
    modo_geral = st.radio("Batch goal?", ["🛒 All for Buying", "🏠 All for Selling", "🔀 Mixed"], horizontal=True)
    fotos_bulk = st.file_uploader("Upload Photos", type=["jpg","jpeg","png","webp"], accept_multiple_files=True, key="bulk_up")

    if fotos_bulk:
        if "tabela_base" not in st.session_state or len(st.session_state.tabela_base) != len(fotos_bulk):
            st.session_state.tabela_base = pd.DataFrame([{
                "Preview": obter_base64_imagem(f), "File": f.name,
                f"Cost ({currency})": 0.0, "Unknown Cost": False,
                "Condition": "Used", "Action": "Sell"
            } for f in fotos_bulk])

        col_cfg = {
            "Preview": st.column_config.ImageColumn("Image", width="small"),
            "Condition": st.column_config.SelectboxColumn("Condition", options=["Used", "Brand New", "Parts"]),
            f"Cost ({currency})": st.column_config.NumberColumn(f"Cost ({currency})", min_value=0.0),
            "Unknown Cost": st.column_config.CheckboxColumn("Unknown Cost")
        }
        if "Mixed" in modo_geral:
            col_cfg["Action"] = st.column_config.SelectboxColumn("Action", options=["Sell", "Buy"], required=True)

        tabela_editada = st.data_editor(st.session_state.tabela_base, num_rows="dynamic",
                                        use_container_width=True, key="editor_bulk", column_config=col_cfg)

        cb1, cb2 = st.columns([2, 1])
        with cb1:
            btn_bulk = st.button("🚀 Process All Items", type="primary", use_container_width=True)
        with cb2:
            st.info(f"📷 {len(fotos_bulk)} items")

        if btn_bulk:
            if not st.session_state.get('email_logado'):
                st.warning("Must be logged in.")
            else:
                st.session_state.bulk_results = []
                st.session_state.bulk_images = {}
                barra = st.progress(0, text="Processing...")
                total = len(tabela_editada)

                for i, row in tabela_editada.iterrows():
                    if trava_seguranca_global():
                        st.error(f"🛑 Global limit reached at item {i+1}.")
                        break
                    pode, saldo = gerir_creditos(st.session_state.email_logado)
                    if not modo_simulacao and not pode:
                        st.warning(f"⚠️ Credits exhausted at item {i+1}.")
                        break

                    nome_fich = row["File"]
                    custo = float(row.get(f"Cost ({currency})", row.get("Cost", 0.0)))
                    sabe = not row.get("Unknown Cost", False)
                    cond_t = row.get("Condition", "Used")
                    cond_c = "Brand New" if cond_t == "Brand New" else "Parts" if cond_t == "Parts" else "Used"
                    obj_f = "Buy" if "Buying" in modo_geral else "Sell" if "Selling" in modo_geral else row.get("Action","Sell")

                    foto_r = next((f for f in fotos_bulk if f.name == nome_fich), None)
                    if foto_r:
                        if i > 0: time.sleep(2)
                        foto_r.seek(0)
                        img = comprimir_imagem(PIL.Image.open(foto_r))
                        st.session_state.bulk_images[nome_fich] = img
                        barra.progress((i + 0.5) / total, text=f"🔍 {nome_fich}...")

                        tentativas = 0
                        sucesso = False
                        dados = {}
                        while tentativas < 3 and not sucesso:
                            if not modo_simulacao:
                                supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()
                            dados = analisar_imagem_json(img, custo, obj_f, sabe, cond_c)
                            if "429" in str(dados.get("estrategia_base","")) or "Resource exhausted" in str(dados.get("estrategia_base","")):
                                tentativas += 1
                                time.sleep(10 * tentativas)
                            elif "Read Error" in dados.get("produto",""):
                                st.error(f"❌ Error: {nome_fich}")
                                break
                            else:
                                sucesso = True
                                if not modo_simulacao: gastar_credito(st.session_state.email_logado)

                        if sucesso:
                            st.session_state.bulk_results.append({
                                "File": nome_fich,
                                f"Cost ({currency})": f"{currency}{custo}",
                                "Item": dados.get('produto','Unknown'),
                                "Verdict": dados.get('veredito_cor','🟡'),
                                f"Avg Price ({currency})": f"{currency}{dados.get('preco_medio',0)}",
                                f"Target Price ({currency})": f"{currency}{dados.get('sugestao_venda',0)}",
                                f"Est. Fees ({currency})": f"{currency}{dados.get('taxas_estimadas',0)}",
                                f"Net Profit ({currency})": f"{currency}{dados.get('lucro_estimado',0)}",
                                "AI Conf.": f"{dados.get('confianca_ia',0)}%",
                                "Data Source": dados.get('fonte_dados','?'),
                                "Strategy": dados.get('estrategia_base'),
                                "Market Link": dados.get('link_pesquisa',''),
                                "Raw": dados
                            })
                            guardar_no_historico(dados, obj_f, st.session_state.email_logado)

                        barra.progress((i+1)/total, text=f"✅ {nome_fich}")

                if st.session_state.bulk_results:
                    st.success(f"✅ Done! {len(st.session_state.bulk_results)}/{total} analysed.")

    if st.session_state.bulk_results:
        st.divider()
        st.markdown("### 📊 Batch Report")
        df_res = pd.DataFrame(st.session_state.bulk_results)
        cols = [c for c in df_res.columns if c != "Raw"]
        st.dataframe(df_res[cols], use_container_width=True)

        # Resumo
        verdes = sum(1 for r in st.session_state.bulk_results if r.get("Verdict") == "🟢")
        profits = []
        for r in st.session_state.bulk_results:
            try:
                v = r.get(f"Net Profit ({currency})", f"{currency}0")
                profits.append(float(str(v).replace(currency, "").replace(",", ".").strip()))
            except: pass
        total_p = sum(profits)

        cs1, cs2, cs3 = st.columns(3)
        cs1.metric("Total Items", len(st.session_state.bulk_results))
        cs2.metric("Profitable 🟢", verdes)
        cs3.metric(f"Total Est. Profit ({currency})", f"{currency}{round(total_p,2)}")

        try:
            excel = converter_para_excel(df_res)
            st.download_button("📥 Download Excel", excel, "valurise_report.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        except Exception as e:
            st.error(f"Excel error: {e}")

        st.write("---")
        opcoes = [r["File"] for r in st.session_state.bulk_results]
        if opcoes:
            escolha = st.selectbox("💬 Chat about:", opcoes, key="seletor_bulk")
            if escolha != st.session_state.current_bulk_item:
                st.session_state.current_bulk_item = escolha
                st.session_state.chat_history_bulk = []
                item_d = next(r for r in st.session_state.bulk_results if r["File"] == escolha)
                if st.session_state.bulk_images.get(escolha):
                    st.session_state.chat_session_bulk = criar_chat_session(item_d['Raw'])
                    bv = (f"👋 Ready for **{item_d['Item']}** {item_d['Verdict']} | "
                          f"Target: {item_d.get(f'Target Price ({currency})','?')} | "
                          f"Profit: {item_d.get(f'Net Profit ({currency})','?')}. What do you want to know?")
                    st.session_state.chat_history_bulk.append({"role": "assistant", "content": bv})

            cc_bulk = st.container(height=380)
            with cc_bulk:
                for msg in st.session_state.chat_history_bulk:
                    with st.chat_message(msg["role"]): st.markdown(msg["content"])

            if pb := st.chat_input("Ask about this item...", key="chat_in_bulk"):
                st.session_state.chat_history_bulk.append({"role": "user", "content": pb})
                with cc_bulk:
                    with st.chat_message("user"): st.markdown(pb)
                    with st.chat_message("assistant"):
                        try:
                            resp = st.session_state.chat_session_bulk.send_message(pb).text
                        except:
                            try:
                                item_d = next(r for r in st.session_state.bulk_results if r["File"] == escolha)
                                st.session_state.chat_session_bulk = criar_chat_session(item_d['Raw'])
                                resp = st.session_state.chat_session_bulk.send_message(pb).text
                            except:
                                resp = "Connection error. Try again."
                        st.markdown(resp)
                        st.session_state.chat_history_bulk.append({"role": "assistant", "content": resp})
                        st.rerun()


# ==========================================
# ABA 3: NEWS
# ==========================================
with aba3:
    st.markdown("### 📈 Market Radar — Trends & Opportunities")
    st.divider()
    try:
        resp_news = supabase.table("noticias").select("*").order("created_at", desc=True).limit(20).execute()
        noticias = resp_news.data
        if noticias:
            for n in noticias:
                with st.container(border=True):
                    c1n, c2n = st.columns([3, 1])
                    with c1n:
                        st.subheader(n['titulo'])
                        st.caption(f"📅 {n['created_at'][:10]} | 🏷️ {n.get('categoria','General')}")
                        st.markdown(n['conteudo'])
                    with c2n:
                        if n.get('imagem_url'): st.image(n['imagem_url'], use_container_width=True)
                        else: st.markdown("# 🗞️")
        else:
            st.info("No news yet. Come back soon!")
    except:
        st.error("Error loading news.")


# ==========================================
# ABA HISTÓRICO
# ==========================================
with aba_historico:
    st.markdown("### 📜 Your Analysis History")
    try:
        res_h = supabase.table("historico_scans").select("*")\
            .eq("email", st.session_state.email_logado)\
            .order("created_at", desc=True).execute()
        if res_h.data:
            df_h = pd.DataFrame(res_h.data)
            lucros_h = pd.to_numeric(df_h.get("lucro_estimado", pd.Series(dtype=float)), errors='coerce').dropna()
            avg_p = lucros_h.mean() if len(lucros_h) > 0 else 0
            h1, h2, h3 = st.columns(3)
            h1.metric("Total Scans", len(df_h))
            h2.metric(f"Avg Net Profit ({currency})", f"{currency}{round(avg_p,2)}")
            h3.metric("Profitable 🟢", len(df_h[df_h.get("cor","") == "🟢"]) if "cor" in df_h.columns else "—")

            cols_disp = [c for c in ["cor","produto","preco_medio","sugestao_venda","taxas_estimadas","lucro_estimado","objetivo","estrategia","link_mercado"] if c in df_h.columns]
            st.dataframe(df_h[cols_disp], column_config={
                "cor": "Verdict", "produto": "Item Name",
                "preco_medio": st.column_config.NumberColumn("Avg Price", format="%.2f"),
                "sugestao_venda": st.column_config.NumberColumn("Target Price", format="%.2f"),
                "taxas_estimadas": st.column_config.NumberColumn("Est. Fees", format="%.2f"),
                "lucro_estimado": st.column_config.NumberColumn("Net Profit", format="%.2f"),
                "link_mercado": st.column_config.LinkColumn("eBay Link"),
                "estrategia": "Strategy", "objetivo": "Goal"
            }, use_container_width=True, hide_index=True)

            if st.button("🗑️ Clear All History"):
                supabase.table("historico_scans").delete().eq("email", st.session_state.email_logado).execute()
                st.success("🧹 Cleared!")
                time.sleep(1)
                st.rerun()
        else:
            st.info("No analyses yet. Start scanning!")
    except Exception as e:
        st.error(f"Error loading history: {e}")


mostrar_rodape_legal()