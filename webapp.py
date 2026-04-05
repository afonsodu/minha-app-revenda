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
import math
from news_manager import mostrar_painel_noticias

st.set_page_config(page_title="Valurise", page_icon="💎", layout="wide")

# ==========================================
# 🎨 CSS CIRÚRGICO
# ==========================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

.stApp { background: linear-gradient(135deg, #0d0d1a 0%, #141428 100%) !important; font-family: 'Inter', sans-serif !important; }
[data-testid="stSidebar"] { background: #111122 !important; border-right: 1px solid rgba(120, 60, 220, 0.25) !important; }
[data-testid="stHeader"] { background: transparent !important; height: 0px !important; }
.stApp h1 { color: #c084fc !important; font-weight: 700 !important; }
.stApp h2, .stApp h3 { color: #e2e8f0 !important; }
.stTabs [data-baseweb="tab-list"] { background: #1a1a35 !important; border-radius: 10px !important; padding: 3px !important; border: 1px solid rgba(120,60,220,0.3) !important; }
.stTabs [data-baseweb="tab"] { color: #94a3b8 !important; border-radius: 8px !important; padding: 8px 18px !important; }
.stTabs [aria-selected="true"] { background: linear-gradient(135deg, #7c3aed, #6d28d9) !important; color: #fff !important; }
.stButton button[kind="primary"] { background: linear-gradient(135deg, #7c3aed, #5b21b6) !important; color: white !important; border: none !important; border-radius: 10px !important; font-weight: 600 !important; box-shadow: 0 4px 15px rgba(124,58,237,0.4) !important; transition: transform 0.15s ease !important; }
.stButton button[kind="primary"]:hover { transform: translateY(-2px) !important; }
.stButton button[kind="secondary"] { background: #1e1e3a !important; color: #c084fc !important; border: 1px solid rgba(120,60,220,0.4) !important; border-radius: 10px !important; }
[data-testid="stAlert"] { border-radius: 8px !important; }
[data-testid="stMetric"] { background: #1a1a35 !important; border: 1px solid rgba(120,60,220,0.25) !important; border-radius: 10px !important; padding: 12px !important; }
[data-testid="stMetricValue"] { color: #a78bfa !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #94a3b8 !important; }
.stProgress > div > div > div { background: linear-gradient(90deg, #7c3aed, #a78bfa) !important; }
[data-testid="stChatMessage"] { background: #1a1a35 !important; border: 1px solid rgba(120,60,220,0.2) !important; border-radius: 10px !important; margin-bottom: 6px !important; }
[data-testid="stFileUploader"] > div { background: #1a1a35 !important; border: 2px dashed rgba(120,60,220,0.4) !important; border-radius: 10px !important; }
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #0d0d1a; }
::-webkit-scrollbar-thumb { background: #7c3aed; border-radius: 3px; }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] .stMarkdown { color: #e2e8f0 !important; }
.stApp .stCaption, .stApp small { color: #64748b !important; }
</style>
""", unsafe_allow_html=True)


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


# ==========================================
# 💾 SUPABASE E CRÉDITOS
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
            "objetivo": objetivo,
            "sell_through_rate": dados.get("sell_through_rate"),
            "custo_compra": dados.get("custo_compra", 0),
            "num_amostra": dados.get("num_amostra", 0)
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
        for col in [f'Cost ({currency})', f'Median ({currency})', f'Target ({currency})', f'Fees ({currency})', f'Profit ({currency})']:
            if col in df_exp.columns:
                df_exp[col] = pd.to_numeric(df_exp[col].astype(str).str.replace(currency, '').str.replace(',', '.').str.strip(), errors='coerce')
        df_exp.to_excel(writer, index=False, sheet_name='Results')
    return output.getvalue()


# ==========================================
# 👤 REGIME DO UTILIZADOR (SETTINGS)
# ==========================================

def carregar_regime_utilizador(email):
    """Carrega as preferências de regime guardadas no Supabase para este email."""
    try:
        res = supabase.table("users_credits").select(
            "regime_region, regime_seller_type, regime_store_plan, regime_vat, regime_intl_shipping"
        ).eq("email", email).execute()
        if res.data and res.data[0].get("regime_region"):
            d = res.data[0]
            return {
                "region":          d.get("regime_region", "🇺🇸 USA ($)"),
                "seller_type":     d.get("regime_seller_type", "Business"),
                "store_plan":      d.get("regime_store_plan", "No Store"),
                "vat_registered":  d.get("regime_vat", "Yes"),
                "intl_shipping":   d.get("regime_intl_shipping", "Own carrier"),
            }
    except:
        pass
    return None

def guardar_regime_utilizador(email, region, seller_type, store_plan, vat_registered, intl_shipping):
    """Persiste as preferências de regime no Supabase."""
    try:
        supabase.table("users_credits").update({
            "regime_region":          region,
            "regime_seller_type":     seller_type,
            "regime_store_plan":      store_plan,
            "regime_vat":             vat_registered,
            "regime_intl_shipping":   intl_shipping,
        }).eq("email", email).execute()
        return True
    except Exception as e:
        st.error(f"Error saving settings: {e}")
        return False


# ==========================================
# 🧮 TAXAS EBAY — MOTOR COMPLETO 2025/2026
# ==========================================

_USA_FVF_NO_STORE = {
    "sneakers_high":    (0.08,    None,   None,   False),
    "sneakers_low":     (0.136,   7500,   0.0235, True),
    "books_media":      (0.153,   7500,   0.0235, True),
    "coins":            (0.1325,  7500,   0.0235, True),
    "bullion":          (0.136,   7500,   0.07,   True),
    "handbags":         (0.15,    2000,   0.09,   True),
    "trading_cards":    (0.1325,  7500,   0.0235, True),
    "jewelry":          (0.15,    5000,   0.09,   True),
    "watches":          (0.15,    1000,   0.065,  True),
    "nfts":             (0.05,    None,   None,   True),
    "heavy_equipment":  (0.03,    15000,  0.005,  True),
    "guitars":          (0.067,   7500,   0.0235, True),
    "default":          (0.136,   7500,   0.0235, True),
}

_USA_FVF_STORE = {
    "sneakers_high":    (0.0765,  None,   None,   False),
    "sneakers_low":     (0.1325,  7500,   0.0235, True),
    "books_media":      (0.1495,  7500,   0.0235, True),
    "coins":            (0.129,   7500,   0.0235, True),
    "bullion":          (0.136,   7500,   0.07,   True),
    "handbags":         (0.146,   2000,   0.086,  True),
    "trading_cards":    (0.129,   7500,   0.0235, True),
    "jewelry":          (0.146,   5000,   0.086,  True),
    "watches":          (0.146,   1000,   0.061,  True),
    "nfts":             (0.05,    None,   None,   True),
    "heavy_equipment":  (0.03,    15000,  0.005,  True),
    "guitars":          (0.0635,  7500,   0.0235, True),
    "default":          (0.1325,  7500,   0.0235, True),
}

_TOP_RATED_DISCOUNT = 0.10

_UK_FVF_BUSINESS = {
    "sneakers_high":    (0.07,    None,   None),
    "sneakers_low":     (0.119,   None,   None),
    "handbags":         (0.129,   800,    0.07),
    "jewelry":          (0.129,   800,    0.07),
    "watches":          (0.069,   2000,   0.03),
    "cameras_pro":      (0.069,   1000,   0.03),
    "computers_pro":    (0.069,   1000,   0.03),
    "electronics_pro":  (0.069,   1000,   0.03),
    "phones":           (0.069,   1000,   0.03),
    "guitars":          (0.07,    2000,   0.035),
    "coins":            (0.109,   450,    0.03),
    "books_media":      (0.099,   None,   None),
    "music":            (0.099,   None,   None),
    "video_games":      (0.099,   None,   None),
    "cameras_basic":    (0.099,   None,   None),
    "antiques":         (0.109,   None,   None),
    "art":              (0.109,   None,   None),
    "baby":             (0.109,   None,   None),
    "collectables":     (0.109,   None,   None),
    "dolls":            (0.109,   None,   None),
    "pottery":          (0.109,   None,   None),
    "sports_mem":       (0.109,   None,   None),
    "stamps":           (0.099,   None,   None),
    "travel":           (0.099,   None,   None),
    "vehicle_parts":    (0.109,   None,   None),
    "business_ind":     (0.119,   None,   None),
    "clothes":          (0.119,   None,   None),
    "crafts":           (0.119,   None,   None),
    "garden":           (0.119,   None,   None),
    "health_beauty":    (0.119,   None,   None),
    "home_furniture":   (0.119,   None,   None),
    "pet_supplies":     (0.119,   None,   None),
    "sporting_goods":   (0.119,   None,   None),
    "toys_games":       (0.119,   None,   None),
    "default":          (0.119,   None,   None),
}

_REGULATORY_FEE = 0.0042
_INTL_FEE_US_OWN  = 0.0165
_INTL_FEE_UK_EU   = 0.0135
_INTL_FEE_UK_US   = 0.0165
_INTL_FEE_UK_ROW  = 0.02

_PER_ORDER_US  = 0.40
_PER_ORDER_US_SMALL = 0.30
_PER_ORDER_UK  = 0.30
_PER_ORDER_EU  = 0.35

def _mapear_cat_usa(c):
    c = (c or "").lower()
    if any(x in c for x in ["sneaker", "trainer", "shoe", "calçado", "sapatilha"]): return "sneakers"
    if any(x in c for x in ["book", "movie", "music", "dvd", "media", "livro", "blu"]): return "books_media"
    if "coin" in c: return "coins"
    if "bullion" in c or "gold bar" in c: return "bullion"
    if any(x in c for x in ["handbag", "bag", "bolsa", "mala"]): return "handbags"
    if any(x in c for x in ["trading card", "sports card", "comic", "ccg"]): return "trading_cards"
    if any(x in c for x in ["watch", "relógio"]): return "watches"
    if "jewelry" in c or "jewellery" in c or "joia" in c: return "jewelry"
    if "nft" in c: return "nfts"
    if any(x in c for x in ["heavy equipment", "printing press", "food truck"]): return "heavy_equipment"
    if any(x in c for x in ["guitar", "bass", "guitarra"]): return "guitars"
    return "default"

def _mapear_cat_uk(c, price):
    c = (c or "").lower()
    if any(x in c for x in ["sneaker", "trainer", "shoe", "calçado", "sapatilha"]):
        return "sneakers_high" if price >= 100 else "sneakers_low"
    if any(x in c for x in ["handbag", "bag", "bolsa", "mala"]): return "handbags"
    if any(x in c for x in ["watch", "relógio"]): return "watches"
    if "jewelry" in c or "jewellery" in c or "joia" in c: return "jewelry"
    if any(x in c for x in ["laptop", "notebook", "desktop", "tablet", "printer", "server", "storage"]): return "computers_pro"
    if any(x in c for x in ["smartphone", "phone", "mobile", "telemóvel"]): return "phones"
    if any(x in c for x in ["camera", "lens", "camcorder", "dslr", "mirrorless"]): return "cameras_pro"
    if any(x in c for x in ["tv", "television", "console", "playstation", "xbox", "nintendo", "audio", "speaker", "headphone"]): return "electronics_pro"
    if any(x in c for x in ["guitar", "bass", "guitarra"]): return "guitars"
    if "coin" in c or "stamp" in c: return "coins"
    if any(x in c for x in ["book", "dvd", "blu-ray", "cd", "vinyl", "livro"]): return "books_media"
    if any(x in c for x in ["game", "video game", "jogo"]): return "video_games"
    if any(x in c for x in ["cloth", "fashion", "apparel", "roupa", "vestuário"]): return "clothes"
    if any(x in c for x in ["health", "beauty", "saúde", "beleza", "cosmetic", "perfume"]): return "health_beauty"
    if any(x in c for x in ["antique", "collectab", "collectable", "vintage"]): return "collectables"
    if any(x in c for x in ["sport", "fitness", "gym"]): return "sporting_goods"
    return "default"

def _fvf_escalonado(p, pct_b, thresh, pct_a):
    if thresh is None or pct_a is None: return p * pct_b
    return p * pct_b if p <= thresh else thresh * pct_b + (p - thresh) * pct_a

def calculate_ebay_fees(region, seller_type, vat_registered, categoria, sale_price,
                         store_plan="No Store", top_rated=False,
                         intl_shipping_method="Own carrier", buyer_location="Domestic"):
    if sale_price <= 0: return 0.0
    fees = 0.0
    
    if region == "🇺🇸 USA ($)":
        ck = _mapear_cat_usa(categoria)
        has_store = store_plan not in ("No Store","Starter")
        tab = _USA_FVF_STORE if has_store else _USA_FVF_NO_STORE
        entry = tab["sneakers_high" if sale_price >= 150 else "sneakers_low"] if ck == "sneakers" else tab.get(ck, tab["default"])
        pct_b, thresh, pct_a, tem_po = entry
        
        if ck == "watches":
            if not has_store:
                fvf = sale_price*0.15 if sale_price<=1000 else 1000*0.15+(sale_price-1000)*0.065 if sale_price<=7500 else 1000*0.15+6500*0.065+(sale_price-7500)*0.03
            else:
                fvf = sale_price*0.146 if sale_price<=1000 else 1000*0.146+(sale_price-1000)*0.061 if sale_price<=7500 else 1000*0.146+6500*0.061+(sale_price-7500)*0.026
        else:
            fvf = _fvf_escalonado(sale_price, pct_b, thresh, pct_a)
            
        if top_rated: fvf *= (1 - _TOP_RATED_DISCOUNT)
        po = (_PER_ORDER_US if sale_price > 10 else _PER_ORDER_US_SMALL) if tem_po else 0.0
        fees = fvf + po
        
        if buyer_location != "Domestic" and intl_shipping_method != "eBay International Shipping (eIS)":
            fees += sale_price * _INTL_FEE_US_OWN

    elif region == "🇬🇧 UK (£)":
        if seller_type == "Private":
            if buyer_location == "Domestic": return 0.0
            return round(sale_price * (_INTL_FEE_UK_EU if buyer_location=="EU" else _INTL_FEE_UK_US if buyer_location=="USA" else _INTL_FEE_UK_ROW), 2)
            
        ck = _mapear_cat_uk(categoria, sale_price)
        pct_b, thresh, pct_a = _UK_FVF_BUSINESS.get(ck, _UK_FVF_BUSINESS["default"])
        fvf = _fvf_escalonado(sale_price, pct_b, thresh, pct_a)
        
        if top_rated: fvf *= (1 - _TOP_RATED_DISCOUNT)
        if vat_registered == "No": fvf *= 1.20
        fees = fvf + _PER_ORDER_UK + sale_price * _REGULATORY_FEE
        
        if buyer_location != "Domestic":
            fees += sale_price * (_INTL_FEE_UK_EU if buyer_location=="EU" else _INTL_FEE_UK_US if buyer_location=="USA" else _INTL_FEE_UK_ROW)

    elif region == "🇵🇹 Portugal (€)":
        cat = (categoria or "").lower()
        if any(x in cat for x in ["sneaker","trainer","sapatilha","calçado"]):
            fvf = sale_price*0.08 if sale_price>=150 else sale_price*0.136
        elif any(x in cat for x in ["watch","relógio"]):
            fvf = sale_price*0.065 if sale_price>=2000 else sale_price*0.15
        elif any(x in cat for x in ["guitar","bass","guitarra"]): 
            fvf = sale_price*0.067
        elif any(x in cat for x in ["book","media","livro","dvd","blu"]): 
            fvf = sale_price*0.153
        elif any(x in cat for x in ["collect","colecion","trading card","comic"]): 
            fvf = sale_price*0.1325
        elif any(x in cat for x in ["tech","electr","laptop","phone","tv","camera"]): 
            fvf = sale_price*0.09
        elif any(x in cat for x in ["health","beauty","saúde","beleza","cosmetic","perfume"]): 
            fvf = sale_price*0.136
        else: 
            fvf = sale_price*0.136
            
        if top_rated: fvf *= (1 - _TOP_RATED_DISCOUNT)
        fees = fvf + _PER_ORDER_EU + sale_price * _REGULATORY_FEE
        
        if buyer_location != "Domestic":
            fees += sale_price * (_INTL_FEE_UK_EU if buyer_location=="UK" else _INTL_FEE_US_OWN if buyer_location=="USA" else _INTL_FEE_UK_ROW)
            
    return round(fees, 2)


# ==========================================
# 🔬 MOTOR DE PESQUISA & FILTROS DE QUALIDADE
# ==========================================

HARD_REJECT = ["for parts","not working","broken","faulty","defective","spares or repair","parts only","repair only","non functional","does not work","damaged","cracked","para peças","avariado","estragado","partido","não funciona"]
LIKELY_INCOMPLETE = ["no battery","no charger","no box","no cable","no controller","no remote","no power supply","no accessories","without charger","without battery","without box","unit only","console only","tablet only","device only","sem bateria","sem carregador","sem caixa"]
INFLATION_WORDS = ["bundle","lot ","lote","joblot","set of ","graded","wata games","vga graded","ukg graded","pcgs","x2 ","x3 ","x4 ","x5 ","2x ","3x ","4x ","5x ","pack of","collection of"]

def contains_word(text, word):
    return re.search(r'\b'+re.escape(word.strip())+r'\b', text) is not None

def item_passa_filtro(titulo, condicao, nome_pesquisado=""):
    t = titulo.lower()
    nl = nome_pesquisado.lower()
    for iw in INFLATION_WORDS:
        if iw.strip() in t and iw.strip() not in nl: 
            return False
    if condicao == "Parts":
        POS = ["complete","fully working","full set","includes charger","includes box","sealed","brand new"]
        return not any(contains_word(t,w) for w in POS)
    elif condicao == "Brand New":
        NOT_NEW = ["used","pre-owned","preowned","open box","loose","played","no box","without box","usado","montado","sem caixa","refurbished"]
        return not any(contains_word(t,w) for w in HARD_REJECT+LIKELY_INCOMPLETE+NOT_NEW)
    else:
        return not any(contains_word(t,w) for w in HARD_REJECT+LIKELY_INCOMPLETE)

def _limpar_q(q):
    stop = ["no barcode","unknown","barcode","n/a","not available","packaging","see photos","as pictured","as is","untested"]
    q2 = q.lower()
    for s in stop: q2 = q2.replace(s,"")
    q2 = re.sub(r'[^\w\s\-\.\(\)]','',q2)
    q2 = re.sub(r'\s+',' ',q2).strip()
    return q2

def _gerar_queries(nome_produto, ebay_query_gemini, categoria, condicao):
    """5 estratégias em cascata, da mais específica para a mais genérica."""
    bg = _limpar_q(ebay_query_gemini)
    bp = _limpar_q(nome_produto)
    queries = []
    
    # Q1 — Query exata do Gemini
    if bg: queries.append(("gemini_exact", bg))
    
    # Q2 — Nome do produto
    pp = bp.split()
    if len(pp) > 8: queries.append(("product_8w", " ".join(pp[:8])))
    elif bp and bp != bg: queries.append(("product_full", bp))
    
    # Q3 — Sem parênteses
    sp = re.sub(r'\s+', ' ', re.sub(r'\(.*?\)', '', bg)).strip()
    if sp and sp != bg: queries.append(("no_paren", sp))
    
    # Q4 — 5 primeiras palavras
    pg = bg.split()
    if len(pg) > 5: queries.append(("short_5w", " ".join(pg[:5])))
    
    # Q5 — Só marca+modelo (3 palavras)
    if len(pg) >= 3: queries.append(("brand_model_3w", " ".join(pg[:3])))
    
    # Deduplicar
    seen = set()
    out = []
    for lbl, q in queries:
        n = q.lower().strip()
        if n and n not in seen and len(n) > 3: 
            seen.add(n)
            out.append((lbl, q))
    return out

def _score_titulo(titulo, query, nome):
    """Score 0-100 de relevância de um título face à query e nome do produto."""
    t = titulo.lower()
    score = 0
    pw = set(query.lower().split())
    tw = set(re.findall(r'\w+', t))
    
    cobertura = len(pw & tw) / len(pw) if pw else 0
    score += cobertura * 60
    
    p2 = nome.lower().split()[:2]
    if all(p in t for p in p2): 
        score += 25
        
    for bom in ["complete","working","original","authentic","genuine","tested"]:
        if bom in t: 
            score += 3
            break
            
    return min(score, 100)

def pesquisar_ebay_profissional(token, nome_produto, ebay_query_gemini, categoria, condicao, marketplace_id):
    """
    Motor de pesquisa com 5 estratégias em cascata + scoring de relevância.
    Prioriza SOLD listings. Fallback: ACTIVE listings.
    Retorna: (items_filtrados, fonte, query_usada)
    """
    if not token: 
        return [], "empty", ebay_query_gemini
        
    queries = _gerar_queries(nome_produto, ebay_query_gemini, categoria, condicao)
    cf = "1000|1500|1750|2000" if condicao == "Brand New" else "7000" if condicao == "Parts" else "3000|4000|5000|6000"
    
    melhor = []
    melhor_fonte = "empty"
    melhor_q = ebay_query_gemini
    
    # FASE 1: SOLD
    for lbl, query in queries:
        dados = buscar_precos_ebay(token, query, marketplace_id=marketplace_id, limit=100, filter_condition=cf)
        items = dados.get("itemSummaries", [])
        fonte = dados.get("_source", "empty")
        
        if fonte == "sold" and len(items) >= 3:
            scored = [(_score_titulo(it.get("title", ""), query, nome_produto), it) for it in items]
            scored.sort(key=lambda x: x[0], reverse=True)
            filt = [x[1] for x in scored if x[0] >= 30]
            
            if len(filt) > len(melhor):
                melhor = filt
                melhor_fonte = "sold"
                melhor_q = query
            if len(melhor) >= 10: break
            
    if melhor and melhor_fonte == "sold": 
        return melhor, melhor_fonte, melhor_q
        
    # FASE 2: ACTIVE
    for lbl, query in queries[:3]:
        dados = buscar_precos_ebay(token, query, marketplace_id=marketplace_id, limit=80, filter_condition=cf)
        items = dados.get("itemSummaries", [])
        fonte = dados.get("_source", "empty")
        
        if fonte == "active" and len(items) >= 5:
            scored = [(_score_titulo(it.get("title", ""), query, nome_produto), it) for it in items]
            scored.sort(key=lambda x: x[0], reverse=True)
            filt = [x[1] for x in scored if x[0] >= 25]
            
            if len(filt) > len(melhor):
                melhor = filt
                melhor_fonte = "active"
                melhor_q = query
            if len(melhor) >= 8: break
            
    return melhor, melhor_fonte, melhor_q

def _calcular_str(n_sold, n_active):
    """Estima o Sell-Through Rate."""
    total = n_sold + n_active
    if total == 0: 
        return None, "No data", "⚪"
        
    if n_active == 0 and n_sold > 0:
        # Estimativa por volume de sold listings disponíveis
        str_pct = 85.0 if n_sold >= 50 else 70.0 if n_sold >= 20 else 55.0 if n_sold >= 10 else 40.0 if n_sold >= 5 else 25.0
    else:
        str_pct = (n_sold / total) * 100
        
    if str_pct >= 70:   lbl = f"🔥 Hot ({str_pct:.0f}%) — Sells fast";    cor = "🟢"
    elif str_pct >= 45: lbl = f"✅ Good ({str_pct:.0f}%) — Steady demand"; cor = "🟢"
    elif str_pct >= 25: lbl = f"🟡 Moderate ({str_pct:.0f}%) — Takes time"; cor = "🟡"
    else:               lbl = f"🔴 Slow ({str_pct:.0f}%) — Hard to sell";  cor = "🔴"
    
    return round(str_pct, 1), lbl, cor

def _preco_otimizado(dados_filtrados, fonte):
    """Calcula o preço de venda com base em percentis e spread do mercado."""
    if not dados_filtrados: return 0.0, 0.0, {}
    
    precos = [d["preco"] for d in dados_filtrados]
    n = len(precos)
    p_med = float(np.median(precos))
    p_mn = float(np.mean(precos))
    p25 = float(np.percentile(precos, 25))
    p40 = float(np.percentile(precos, 40))
    p75 = float(np.percentile(precos, 75))
    desvio = float(np.std(precos))
    spread = (desvio / p_med * 100) if p_med > 0 else 0
    
    stats = {
        "mediana": round(p_med, 2), "media": round(p_mn, 2), 
        "p25": round(p25, 2), "p75": round(p75, 2), 
        "spread_pct": round(spread, 1), "n": n
    }
    
    if fonte == "sold":
        if n >= 20:   pv = p40
        elif n >= 10: pv = p_med
        elif n >= 5:  pv = p_med * 1.02
        else:         pv = p_med
        if spread > 40: pv = (pv + p25) / 2
    else:  # active
        if n >= 15:   pv = float(np.percentile(precos, 35))
        elif n >= 8:  pv = p40
        else:         pv = p25
        
    # Psicologia de preço .99
    pv = round(pv, 2)
    if pv > 10: 
        pv = math.floor(pv) - 0.01 if pv % 1 > 0.5 else pv
    pv = max(pv, p25 * 0.8)
    
    portes = float(np.mean([d["envio"] for d in dados_filtrados]))
    return round(pv, 2), portes, stats


# ==========================================
# 🔐 SESSION STATE & INIT
# ==========================================

defaults = {
    "email_logado": None, "single_result": None,
    "chat_history_single": [], "chat_session_single": None,
    "bulk_results": [], "bulk_images": {}, "bulk_fase1": [],
    "chat_history_bulk": [], "chat_session_bulk": None,
    "current_bulk_item": None, "historico_conversas": [],
    "id_conversa_ativa": None,
    "regime_configurado": False, "regime_region": "🇺🇸 USA ($)",
    "regime_seller_type": "Business", "regime_store_plan": "No Store",
    "regime_vat": "Yes", "regime_top_rated": False, "regime_intl_shipping": "Own carrier",
    "esperando_resposta": False,
    "dados_ia_guardados": None,
    "pergunta_pendente": "",
    "img_temporaria": None,
}
for k, v in defaults.items():
    if k not in st.session_state: 
        st.session_state[k] = v


# ==========================================
# ⚙️ SIDEBAR
# ==========================================
with st.sidebar:
    st.header("⚙️ Settings")
    if st.session_state.email_logado:
        st.success(f"👤 {st.session_state.email_logado}")
        if st.session_state.email_logado in ADMINS: 
            st.metric("Plan", "👑 ADMIN / Unlimited")
        else: 
            st.metric("Credits Today", f"{obter_saldo_visual(st.session_state.email_logado)} / 1")
            
        if st.button("🚪 Exit / Change Account"):
            st.session_state.email_logado = None
            st.session_state.regime_configurado = False
            st.rerun()
    else: 
        st.warning("No user logged in.")
        
    st.divider()
    st.markdown("**Legend:**")
    st.markdown("🟢 Profitable | 🟡 Break-even | 🔴 Loss | 🔮 AI Estimate")


# ==========================================
# 📱 LOGIN INTERFACE
# ==========================================
st.title("💎 Valurise")
st.caption("AI-Powered Resale Intelligence — eBay Sold Listings Engine")

if not st.session_state.email_logado:
    st.info("👋 You are invited to test the Valurise prototype.")
    col1, col2 = st.columns([3, 1])
    with col1:
        email_input = st.text_input("Email:")
        termos = st.checkbox("I accept the Beta test terms and understand AI may make mistakes.")
    with col2:
        st.write(""); st.write("")
        if st.button("Access Beta", type="primary"):
            if not termos: 
                st.warning("Accept the terms first.")
            elif "@" not in email_input: 
                st.warning("Invalid email.")
            else:
                st.session_state.email_logado = email_input
                r = carregar_regime_utilizador(email_input)
                if r:
                    st.session_state.regime_region = r["region"]
                    st.session_state.regime_seller_type = r["seller_type"]
                    st.session_state.regime_store_plan = r["store_plan"]
                    st.session_state.regime_vat = r["vat_registered"]
                    st.session_state.regime_intl_shipping = r["intl_shipping"]
                    st.session_state.regime_configurado = True
                else:
                    st.session_state.regime_configurado = False
                st.rerun()
                
    with st.expander("ℹ️ About"):
        st.markdown("Prototype by an independent developer. Email used only for your account. Values are AI estimates — always verify.")
    st.stop()

st.sidebar.write(f"👤 **{st.session_state.email_logado}**")


# ==========================================
# ⚙️ PAINEL DE REGIME (Setup Inicial)
# ==========================================
def mostrar_painel_regime(is_setup=False):
    if is_setup:
        st.subheader("🛒 eBay Seller Profile Setup")
        st.info("Before using Valurise, configure your eBay seller profile. You can change this anytime in Settings.")
        
    r_opts = ["🇺🇸 USA ($)", "🇬🇧 UK (£)", "🇵🇹 Portugal (€)"]
    r_idx = r_opts.index(st.session_state.regime_region) if st.session_state.regime_region in r_opts else 0
    new_region = st.selectbox("📍 eBay Marketplace", r_opts, index=r_idx, key="setup_region")
    
    new_seller_type = "Business"
    new_vat = "Yes"
    new_store = "No Store"
    new_intl = "Own carrier"
    
    if new_region == "🇺🇸 USA ($)":
        so = ["No Store", "Starter", "Basic", "Premium", "Anchor", "Enterprise"]
        si = so.index(st.session_state.regime_store_plan) if st.session_state.regime_store_plan in so else 0
        new_store = st.selectbox("🏪 Store Subscription", so, index=si, key="setup_store", help="Affects FVF rate")
        st.caption("💡 No Store/Starter → 13.6% | Basic+ → 13.25% | Enterprise → 12.5%")
        
    elif new_region == "🇬🇧 UK (£)":
        sto = ["Private", "Business"]
        sti = sto.index(st.session_state.regime_seller_type) if st.session_state.regime_seller_type in sto else 1
        new_seller_type = st.radio("👤 Account Type", sto, index=sti, horizontal=True, key="setup_st")
        
        if new_seller_type == "Private": 
            st.success("🎉 UK Private sellers pay 0% Final Value Fees on domestic sales!")
        else:
            souk = ["No Shop", "Basic Shop (£27/mo)", "Featured Shop (£77/mo)", "Anchor Shop (£437/mo)"]
            si = 0
            for i, o in enumerate(souk):
                if st.session_state.regime_store_plan in o: 
                    si = i
                    break
            new_store = st.selectbox("🏪 Shop Subscription", souk, index=si, key="setup_store_uk").split(" (")[0]
            vo = ["Yes", "No"]
            vi = vo.index(st.session_state.regime_vat) if st.session_state.regime_vat in vo else 0
            new_vat = st.radio("🏛️ VAT Registered?", vo, index=vi, horizontal=True, key="setup_vat")
            if new_vat == "No": 
                st.warning("⚠️ Not VAT registered: eBay adds 20% VAT on fees — effective rate ~14%+.")
                
    elif new_region == "🇵🇹 Portugal (€)":
        soeu = ["No Store", "Basic (~€27/mo)", "Featured (~€77/mo)", "Anchor (~€437/mo)"]
        si = 0
        for i, o in enumerate(soeu):
            if st.session_state.regime_store_plan in o: 
                si = i
                break
        new_store = st.selectbox("🏪 Store Subscription", soeu, index=si, key="setup_store_eu").split(" (")[0]
        st.caption("ℹ️ Regulatory Operating Fee of 0.42% applies to all EU sales.")
        
    new_top_rated = st.checkbox("⭐ I am a Top Rated Seller (−10% on FVF)", value=st.session_state.regime_top_rated, key="setup_tr")
    
    if new_region == "🇺🇸 USA ($)":
        io = ["Own carrier", "eBay International Shipping (eIS)"]
        ii = io.index(st.session_state.regime_intl_shipping) if st.session_state.regime_intl_shipping in io else 0
        new_intl = st.selectbox("🌍 International Shipping Method", io, index=ii, key="setup_intl", help="eIS = exempt from international fee")
        if new_intl == "eBay International Shipping (eIS)": 
            st.success("✅ eIS: International fee waived!")
            
    if st.button("💾 Save Profile", type="primary", key="btn_save_regime"):
        st.session_state.regime_region = new_region
        st.session_state.regime_seller_type = new_seller_type
        st.session_state.regime_store_plan = new_store
        st.session_state.regime_vat = new_vat
        st.session_state.regime_top_rated = new_top_rated
        st.session_state.regime_intl_shipping = new_intl
        st.session_state.regime_configurado = True
        
        guardar_regime_utilizador(st.session_state.email_logado, new_region, new_seller_type, new_store, new_vat, new_intl)
        st.success("✅ Profile saved!")
        time.sleep(1)
        st.rerun()
        
    return new_region, new_seller_type, new_store, new_vat, new_top_rated, new_intl

if not st.session_state.regime_configurado:
    mostrar_painel_regime(is_setup=True)
    st.stop()

# Definir as globais para a sessão baseada no regime
region = st.session_state.regime_region
seller_type = st.session_state.regime_seller_type
store_plan = st.session_state.regime_store_plan
vat_registered = st.session_state.regime_vat
top_rated = st.session_state.regime_top_rated
intl_shipping = st.session_state.regime_intl_shipping

currency = {"🇺🇸 USA ($)": "$", "🇬🇧 UK (£)": "£", "🇵🇹 Portugal (€)": "€"}.get(region, "$")
mapa_marketplaces = {"🇺🇸 USA ($)": "EBAY_US", "🇬🇧 UK (£)": "EBAY_GB", "🇵🇹 Portugal (€)": "EBAY_ES"}
marketplace_atual = mapa_marketplaces.get(region, "EBAY_US")


# ==========================================
# 🤖 PIPELINE PRINCIPAL: GEMINI + PESQUISA
# ==========================================

def analisar_imagem_json(image, custo, objetivo, sabe_custo, condicao):
    try:
        if not pre_dados:
            prompt_id = f"""
            You are a world-class resale item identifier. Analyze this image with maximum precision.
            The user has stated the item condition is: "{condicao}". 
            Take this into account and only ask the condition in your extra question if it is about something really specific and important to the value of the object.
            Return ONLY a JSON object with these exact keys:

            "produto": Full commercial product name with brand + model + key variant.
            - Electronics: include storage/RAM if visible (e.g. "Apple iPhone 13 128GB Black")
            - Sneakers: brand + model + colorway (e.g. "Nike Air Max 90 White Black")
            - Perfumes: brand + name + concentration + size (e.g. "Chanel Bleu de Chanel EDP 100ml")
            - DO NOT include: condition words, barcodes, "no barcode"

            "ebay_query": 5-8 word search string a professional reseller would type on eBay to find SOLD listings.
            Include most identifying attributes (brand, model, key variant).
            Omit generic words: "good", "nice", "great", "original".
            Examples: "Apple iPhone 13 128GB Black Unlocked", "Nike Air Max 90 Black White", "Sony PS5 Disc Edition"

            "categoria": ONE of: Sneakers, Watches, Electronics, Guitars & Basses, Books/Media, Collectibles, Health & Beauty, Others

            "confianca": Integer 0-100. Certainty of exact model identification.
            90+: Brand AND model clearly readable. 70-89: Brand clear, model inferred. 50-69: Brand recognised model uncertain. <50: Uncertain.

            "atributos": List of max 3 key distinguishing attributes as strings.
            e.g. ["128GB","Black","Unlocked"] or ["UK Size 10","White Black"] or ["EDP","100ml"]

            "pergunta_extra": Based on this specific product, what single piece of information would most improve eBay price accuracy?
            Return a natural question in English the user can answer.
            If nothing important is missing, return null. 
            (only ask the question if you can not see that information on the image
            or if that information was not given to you).

            Region context: {region}. Write ALL values in English.
            Respond ONLY with valid JSON, no other text:
            {{"produto":"...","ebay_query":"...","categoria":"...","confianca":85,"atributos":[...],"pergunta_extra":"..."}}
                    """
        res_visao = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt_id, image])
        texto = res_visao.text.replace("```json", "").replace("```", "").strip()
        jm = re.search(r'\{.*?\}', texto, re.DOTALL)
        if jm: 
            texto = jm.group()
            
        try:
            di = json.loads(texto)
            nome_item = di.get("produto", "Unknown Item")
            ebay_query = di.get("ebay_query", nome_item)
            categoria_item = di.get("categoria", "Others")
            confianca = di.get("confianca", 50)
            atributos = di.get("atributos", [])
            pergunta_ai = di.get("pergunta_extra")
        except json.JSONDecodeError:
            nome_item = texto[:80].strip()
            ebay_query = nome_item
            categoria_item = "Others"
            confianca = 30
            atributos = []
            pergunta_ai = None

        # ── PASSO 2: PESQUISA PROFISSIONAL ──
        token = garantir_token_ebay()
        items_scored, fonte_dados, query_usada = pesquisar_ebay_profissional(
            token, nome_item, ebay_query, categoria_item, condicao, marketplace_atual)

        # ── PASSO 3: FILTROS DE QUALIDADE ──
        dados_validados = []
        for item in items_scored:
            try:
                titulo = item.get('title', '')
                cid = str(item.get('conditionId', ''))
                
                if condicao == "Brand New":
                    if cid not in ["1000", "1500", "1750", "2000"]: continue
                elif condicao == "Parts":
                    if cid != "7000": continue
                else:
                    if cid in ["1000", "1500", "1750", "7000"]: continue
                    
                if not item_passa_filtro(titulo, condicao, query_usada): continue
                
                valor = float(item.get('price', {}).get('value', 0))
                if valor < 3.0: continue
                
                try:
                    ops = item.get('shippingOptions', [])
                    envio = float(ops[0].get('shippingCost', {}).get('value', 0)) if ops else 0.0
                except: 
                    envio = 4.50
                    
                if envio > 40.0: continue
                dados_validados.append({"preco": valor, "envio": envio, "titulo": titulo})
            except: 
                continue

        # ── PASSO 4: IQR STATÍSTICO ──
        dados_filtrados = []
        if dados_validados:
            lp = [d["preco"] for d in dados_validados]
            med = np.median(lp)
            q1 = np.percentile(lp, 25)
            q3 = np.percentile(lp, 75)
            iqr = q3 - q1
            lower = max(q1 - 1.5 * iqr, med * 0.25)
            upper = q3 + 1.5 * iqr
            dados_filtrados = [d for d in dados_validados if lower <= d["preco"] <= upper]
            if not dados_filtrados: 
                dados_filtrados = dados_validados
        num_amostra = len(dados_filtrados)

        # ── PASSO 5: SELL-THROUGH RATE ──
        if fonte_dados == "sold": 
            str_pct, str_label, str_cor = _calcular_str(num_amostra, 0)
        elif fonte_dados == "active": 
            str_pct, str_label, str_cor = _calcular_str(0, num_amostra)
        else: 
            str_pct, str_label, str_cor = None, "No data", "⚪"

        # ── PASSO 6: PREÇO OTIMIZADO ──
        if dados_filtrados and num_amostra >= 2:
            p_venda, portes_medios, stats = _preco_otimizado(dados_filtrados, fonte_dados)
            p_medio = stats["mediana"]
            p25 = stats["p25"]
            p75 = stats["p75"]
            spread = stats["spread_pct"]
        else:
            p_venda = p_medio = portes_medios = 0.0
            p25 = p75 = spread = 0.0
            stats = {}

        # ── PASSO 7: TAXAS + LUCRO ──
        if p_medio > 0:
            comissao = calculate_ebay_fees(
                region=region, seller_type=seller_type, vat_registered=vat_registered,
                categoria=categoria_item, sale_price=p_venda, store_plan=store_plan, 
                top_rated=top_rated, intl_shipping_method=intl_shipping, buyer_location="Domestic"
            )
            taxas_estimadas = portes_medios + comissao
            custo_real = 0 if not sabe_custo else custo
            lucro = p_venda - custo_real - taxas_estimadas
            margem_pct = (lucro / p_venda * 100) if p_venda > 0 else 0
            roi_pct = (lucro / custo_real * 100) if custo_real > 0 else None
            
            dominios = {"🇺🇸 USA ($)": "ebay.com", "🇬🇧 UK (£)": "ebay.co.uk", "🇵🇹 Portugal (€)": "ebay.es"}
            dom = dominios.get(region, "ebay.com")
            cu = {"Brand New": "&LH_ItemCondition=3", "Parts": "&LH_ItemCondition=7000", "Used": "&LH_ItemCondition=4"}
            fu = cu.get(condicao, "&LH_ItemCondition=4")
            qu = query_usada.replace(' ', '+')
            link_sold = f"https://www.{dom}/sch/i.html?_nkw={qu}&LH_Sold=1&LH_Complete=1{fu}"
            link_active = f"https://www.{dom}/sch/i.html?_nkw={qu}{fu}"
            
            # Veredito
            if lucro < 0: cor = "🔴"
            elif margem_pct >= 20 and num_amostra >= 5: cor = "🟢"
            elif margem_pct >= 8: cor = "🟡"
            else: cor = "🔴"
            
            rl = f"{region}|{seller_type}"
            if seller_type == "Business" and store_plan not in ("No Store", "No Shop"): 
                rl += f"|{store_plan}"
            if top_rated: 
                rl += "|⭐TR"
                
            fl = "✅ Sold listings" if fonte_dados == "sold" else "⚠️ Active listings (no sold data)"
            pmc = round(p_venda - taxas_estimadas, 2)
            sv = f"|⚠️ Volatile mkt ({spread:.0f}%)" if spread > 35 else ""
            
            if not sabe_custo:
                estrategia = (
                    f"{fl}|{num_amostra} refs|Range:{currency}{p25}–{currency}{p75}|"
                    f"Target:{currency}{round(p_venda, 2)}|Fees:{currency}{round(taxas_estimadas, 2)}[{rl}]|"
                    f"Buy below {currency}{pmc} to profit{sv}"
                )
            else:
                rt = f"|ROI:{roi_pct:.0f}%" if roi_pct is not None else ""
                if lucro < 0: 
                    estrategia = f"❌ Loss {currency}{abs(round(lucro, 2))}|{fl}|{num_amostra} refs|Source below {currency}{pmc}{sv}"
                elif margem_pct < 8: 
                    estrategia = f"⚠️ Tight {round(margem_pct, 1)}% margin{rt}|{fl}|{num_amostra} refs[{rl}]{sv}"
                elif margem_pct >= 20: 
                    estrategia = f"🔥 Excellent {round(margem_pct, 1)}%{rt}|{fl}|{num_amostra} refs|Strong demand[{rl}]{sv}"
                else: 
                    estrategia = f"👍 Solid {round(margem_pct, 1)}%{rt}|{fl}|{num_amostra} refs[{rl}]{sv}"
                    
            if p_venda > 200: 
                estrategia += " | ⚠️ HIGH VALUE: verify edition on eBay."
                
        else:
            # Plano B: Gemini estima
            prompt_est = f"""
            No eBay sold data for "{nome_item}" condition "{condicao}".
            As expert appraiser for {region} market, estimate:
            {{"preco":X,"preco_min":Y,"preco_max":Z,"justificativa":"concise reason","confianca_estimativa":0-100}}
            Respond ONLY JSON.
            """
            try:
                re2 = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt_est, image])
                tj = re2.text.replace("```json", "").replace("```", "").strip()
                jm2 = re.search(r'\{.*?\}', tj, re.DOTALL)
                if jm2: 
                    tj = jm2.group()
                de = json.loads(tj)
                
                p_venda = float(de.get("preco", 0))
                justif = de.get("justificativa", "Visual estimate.")
                p_medio = p_venda
                portes_medios = 5.0
                p25 = float(de.get("preco_min", p_venda * 0.8))
                p75 = float(de.get("preco_max", p_venda * 1.2))
                
                comissao = calculate_ebay_fees(
                    region, seller_type, vat_registered, categoria_item, p_venda, store_plan, top_rated
                )
                taxas_estimadas = portes_medios + comissao
                custo_real = 0 if not sabe_custo else custo
                lucro = p_venda - custo_real - taxas_estimadas
                roi_pct = (lucro / custo_real * 100) if custo_real > 0 else None
                margem_pct = (lucro / p_venda * 100) if p_venda > 0 else 0
                
                dom = {"🇺🇸 USA ($)": "ebay.com", "🇬🇧 UK (£)": "ebay.co.uk", "🇵🇹 Portugal (€)": "ebay.es"}.get(region, "ebay.com")
                link_sold = f"https://www.{dom}/sch/i.html?_nkw={nome_item.replace(' ', '+')}"
                link_active = link_sold
                cor = "🔮"
                if lucro < 0: cor = "🔴"
                elif lucro > 15: cor = "🟢"
                
                estrategia = f"⚠️ No eBay data — AI estimate ({justif}). Range:{currency}{p25:.0f}–{currency}{p75:.0f}"
                str_pct, str_label, str_cor = None, "No data (AI estimate)", "⚪"
                num_amostra = 0
                spread = 0
            except:
                p_medio = p_venda = lucro = taxas_estimadas = 0
                p25 = p75 = spread = margem_pct = 0.0
                roi_pct = None
                portes_medios = 0
                dom = {"🇺🇸 USA ($)": "ebay.com", "🇬🇧 UK (£)": "ebay.co.uk", "🇵🇹 Portugal (€)": "ebay.es"}.get(region, "ebay.com")
                link_sold = f"https://www.{dom}/sch/i.html?_nkw={nome_item.replace(' ', '+')}"
                link_active = link_sold
                cor = "⚪"
                estrategia = "No eBay data found and AI couldn't estimate. Try a clearer photo."
                str_pct, str_label, str_cor = None, "No data", "⚪"
                num_amostra = 0

        return {
            "produto": nome_item,
            "ebay_query": ebay_query,
            "query_usada": query_usada if 'query_usada' in dir() else ebay_query,
            "categoria": categoria_item,
            "atributos": atributos,
            "confianca_ia": confianca,
            "fonte_dados": fonte_dados if 'fonte_dados' in dir() else "unknown",
            "preco_medio": round(p_medio, 2),
            "preco_p25": round(p25, 2),
            "preco_p75": round(p75, 2),
            "sugestao_venda": round(p_venda, 2),
            "taxas_estimadas": round(taxas_estimadas, 2),
            "lucro_estimado": round(lucro, 2),
            "margem_pct": round(margem_pct, 1),
            "roi_pct": round(roi_pct, 1) if roi_pct is not None else None,
            "custo_compra": custo if sabe_custo else 0,
            "link_pesquisa": link_sold if 'link_sold' in dir() else "",
            "link_ativo": link_active if 'link_active' in dir() else "",
            "estrategia_base": estrategia,
            "veredito_cor": cor,
            "num_amostra": num_amostra,
            "sell_through_rate": str_pct,
            "str_label": str_label,
            "str_cor": str_cor,
            "pergunta_extra": pergunta_ai if 'pergunta_ai' in dir() else None,
        }
    except Exception as e:
        return {
            "produto": "Read Error", "estrategia_base": f"Error: {str(e)}", "veredito_cor": "🔴",
            "preco_medio": 0, "sugestao_venda": 0, "taxas_estimadas": 0, "lucro_estimado": 0,
            "sell_through_rate": None, "str_label": "Error", "str_cor": "⚪", "roi_pct": None, "custo_compra": 0
        }


# ==========================================
# 💬 CHAT SESSION
# ==========================================
def criar_chat_session(dados_completos):
    if modo_simulacao: return "simulacao"
    nome = dados_completos.get('produto', 'Item')
    p_med = dados_completos.get('preco_medio', 0)
    sug = dados_completos.get('sugestao_venda', 0)
    lucro = dados_completos.get('lucro_estimado', 0)
    est = dados_completos.get('estrategia_base', '')
    ver = dados_completos.get('veredito_cor', '⚪')
    cat = dados_completos.get('categoria', 'Others')
    conf = dados_completos.get('confianca_ia', 50)
    refs = dados_completos.get('num_amostra', 0)
    fonte = dados_completos.get('fonte_dados', 'unknown')
    strl = dados_completos.get('str_label', 'No data')
    marg = dados_completos.get('margem_pct', 0)
    roi = dados_completos.get('roi_pct')
    p25 = dados_completos.get('preco_p25', 0)
    p75 = dados_completos.get('preco_p75', 0)
    
    ctx = f"""
    You are an elite Resale & Arbitrage Consultant. Be concise and data-driven.
    Item: {nome} | Category: {cat} | AI Confidence: {conf}%
    Data: {fonte} ({refs} refs) | Price range: {currency}{p25}–{currency}{p75}
    Median: {currency}{p_med} | Target: {currency}{sug} | Fees: {currency}{dados_completos.get('taxas_estimadas',0)}
    Profit: {currency}{lucro} | Margin: {marg}%{f" | ROI: {roi:.0f}%" if roi else ""} | STR: {strl}
    Verdict: {ver} | Strategy: {est}
    Region: {region} | Seller: {seller_type} | Store: {store_plan} | Top Rated: {top_rated}
    
    Your role: 
    1) Explain price strategy & data quality 
    2) Comment on STR 
    3) Suggest platforms 
    4) eBay listing title tips 
    5) If 🔴, suggest cheaper sourcing. 
    Be concise, use bullet points.
    """
    
    st.session_state.chat = client.chats.create(
        model='gemini-2.0-flash',
        history=[
            types.Content(role="user", parts=[types.Part.from_text(text=ctx)]),
            types.Content(role="model", parts=[types.Part.from_text(text=f"Ready to help maximize profit on **{nome}**. What would you like to know?")])
        ]
    )
    return st.session_state.chat


# ==========================================
# TABS
# ==========================================
aba1, aba2, aba3, aba_historico, aba_settings = st.tabs([
    "🔍 Single Analysis", "📦 Bulk Scan", "📰 Market News", "📜 History", "⚙️ Settings"
])

# ==========================================
# ABA 1: ANÁLISE INDIVIDUAL
# ==========================================
with aba1:
    col_input, col_res = st.columns([1, 2])
    with col_input:
        st.markdown("### 📸 Item Details")
        with st.container(border=True):
            rd = f"**{region}** | {seller_type}"
            if store_plan and store_plan not in ("No Store", "No Shop"): 
                rd += f" | {store_plan}"
            if top_rated: 
                rd += " | ⭐ TR"
            st.caption(f"🛒 Active profile: {rd}")
            
        objetivo_single = st.radio("Goal?", ["Sell", "Buy"], horizontal=True, key="obj_single_final")
        foto_single = st.file_uploader("Upload Photo", type=["jpg", "jpeg", "png", "webp"], key="single_up_final")
        sabe_custo_single = not st.checkbox("I don't know the item cost", key="check_custo_single")
        custo_single = st.number_input(f"Purchase Cost ({currency})", min_value=0.0, step=1.0, key="single_cost_final", disabled=not sabe_custo_single)
        condicao_single = st.selectbox("Item Condition", ["Used (Complete/Working)", "Brand New (Sealed)", "Incomplete / For Parts"], key="cond_single")
        cond_codigo_single = "Brand New" if condicao_single == "Brand New (Sealed)" else "Parts" if condicao_single == "Incomplete / For Parts" else "Used"
        
        if st.button("🚀 Analyse Item", type="primary", use_container_width=True):
            if not foto_single: 
                st.warning("Upload a photo first.")
            else:
                if trava_seguranca_global(): 
                    st.error("🛑 Daily limit reached.")
                    st.stop()
                    
                foto_single.seek(0)
                img = comprimir_imagem(PIL.Image.open(foto_single))
                pode_avancar, saldo = gerir_creditos(st.session_state.email_logado)
                
                if pode_avancar or modo_simulacao:
                    with st.spinner("🔍 Identifying + running professional eBay search..."):
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
            pr = (f"Analysed **{dados.get('produto','this item')}** | Verdict: **{dados.get('veredito_cor')}** | "
                  f"Target: **{currency}{dados.get('sugestao_venda',0)}** | Net profit: **{currency}{dados.get('lucro_estimado',0)}**. How can I help?")
            st.session_state.chat_history_single.append({"role": "assistant", "content": pr})
            
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
            m1.metric("Median Price", f"{currency}{dados.get('preco_medio',0)}")
            m2.metric("Target Price", f"{currency}{dados.get('sugestao_venda',0)}")
            m3.metric("Est. Fees", f"{currency}{dados.get('taxas_estimadas',0)}")
            m4.metric("Net Profit", f"{currency}{dados.get('lucro_estimado',0)}")
            
            p25 = dados.get('preco_p25', 0)
            p75 = dados.get('preco_p75', 0)
            roi = dados.get('roi_pct')
            marg = dados.get('margem_pct', 0)
            
            ic = st.columns(3)
            ic[0].metric("Price Range", f"{currency}{p25}–{currency}{p75}")
            ic[1].metric("Margin %", f"{marg:.1f}%")
            ic[2].metric("ROI", f"{roi:.0f}%" if roi is not None else "—")
            
            # STR
            sl = dados.get('str_label', 'No data')
            sp = dados.get('sell_through_rate')
            with st.container(border=True):
                st.caption("📊 Sell-Through Rate (demand signal)")
                if sp is not None: 
                    st.progress(min(int(sp), 100) / 100)
                st.markdown(f"**{sl}**")
                
            # Veredito
            cor = dados.get('veredito_cor', '⚪')
            ms = dados.get('estrategia_base', '')
            if cor == "🟢": st.success(f"**{cor} PROFITABLE** — {ms}")
            elif cor == "🟡": st.warning(f"**{cor} MARGINAL** — {ms}")
            elif cor == "🔴": st.error(f"**{cor} LOSS** — {ms}")
            else: st.info(f"**{cor} AI ESTIMATE** — {ms}")
            
            # Links
            lc = st.columns(2)
            if dados.get('link_pesquisa'): 
                lc[0].link_button("🔗 eBay Sold Listings", dados['link_pesquisa'])
            if dados.get('link_ativo'): 
                lc[1].link_button("🔍 eBay Active Listings", dados['link_ativo'])
                
            # Info
            conf = dados.get('confianca_ia', 0)
            if conf:
                cc = "green" if conf >= 75 else "orange" if conf >= 50 else "red"
                qu = dados.get('query_usada', dados.get('ebay_query', ''))
                st.markdown(f"🧠 AI Confidence: **:{cc}[{conf}%]** | 📊 **{dados.get('num_amostra',0)}** refs ({dados.get('fonte_dados','?')}) | 🔎 `{qu}`")
            atr = dados.get('atributos', [])
            if atr: 
                st.caption("🏷️ Key attributes: " + " · ".join([f"`{a}`" for a in atr]))
                
            st.write("---")
            
            # Chat
            cc_s = st.container(height=380)
            with cc_s:
                for msg in st.session_state.chat_history_single:
                    with st.chat_message(msg["role"]): 
                        st.markdown(msg["content"])
                        
            if prompt := st.chat_input("Ask about pricing, strategy, listing tips...", key="chat_input_unico"):
                st.session_state.chat_history_single.append({"role": "user", "content": prompt})
                with cc_s:
                    with st.chat_message("user"): 
                        st.markdown(prompt)
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
    with st.container(border=True):
        rd = f"**{region}** | {seller_type}"
        if store_plan and store_plan not in ("No Store", "No Shop"): 
            rd += f" | {store_plan}"
        if top_rated: 
            rd += " | ⭐ Top Rated"
        st.caption(f"🛒 Active profile: {rd} — fees calculated accordingly.")
        
    modo_geral = st.radio("Batch goal?", ["🛒 All for Buying", "🏠 All for Selling", "🔀 Mixed"], horizontal=True)
    fotos_bulk = st.file_uploader("Upload Photos", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="bulk_up")
    
    if fotos_bulk:
        if "tabela_base" not in st.session_state or len(st.session_state.tabela_base) != len(fotos_bulk):
            st.session_state.tabela_base = pd.DataFrame([{
                "Preview": obter_base64_imagem(f), "File": f.name,
                f"Cost ({currency})": 0.0, "Unknown Cost": False, "Condition": "Used", "Action": "Sell"
            } for f in fotos_bulk])
            
        col_cfg = {
            "Preview": st.column_config.ImageColumn("Image", width="small"),
            "Condition": st.column_config.SelectboxColumn("Condition", options=["Used", "Brand New", "Parts"]),
            f"Cost ({currency})": st.column_config.NumberColumn(f"Cost ({currency})", min_value=0.0),
            "Unknown Cost": st.column_config.CheckboxColumn("Unknown Cost")
        }
        if "Mixed" in modo_geral:
            col_cfg["Action"] = st.column_config.SelectboxColumn("Action", options=["Sell", "Buy"], required=True)
            
        tabela_editada = st.data_editor(st.session_state.tabela_base, num_rows="dynamic", use_container_width=True, key="editor_bulk", column_config=col_cfg)
        cb1, cb2 = st.columns([2, 1])
        with cb1: 
            btn_bulk = st.button("🚀 Process All Items", type="primary", use_container_width=True)
        with cb2: 
            st.info(f"📷 {len(fotos_bulk)} items")
            
        # ── FASE 1: identificar items + recolher perguntas ──
        if btn_bulk:
            if not st.session_state.get('email_logado'):
                st.warning("Must be logged in.")
            else:
                st.session_state.bulk_results = []
                st.session_state.bulk_images = {}
                st.session_state.bulk_fase1 = []
                barra = st.progress(0, text="Identifying items...")
                total = len(tabela_editada)

                for i, row in tabela_editada.iterrows():
                    nome_fich = row["File"]
                    foto_r = next((f for f in fotos_bulk if f.name == nome_fich), None)
                    if not foto_r:
                        continue
                    if i > 0:
                        time.sleep(1)
                    foto_r.seek(0)
                    img = comprimir_imagem(PIL.Image.open(foto_r))
                    st.session_state.bulk_images[nome_fich] = img
                    barra.progress((i + 0.5) / total, text=f"🔍 {nome_fich}...")

                    try:
                        prompt_id_rapido = f"""
You are a world-class resale item identifier. Analyze this image with maximum precision.
Return ONLY a JSON object:
"produto": Full commercial product name with brand + model + key variant.
"ebay_query": 5-8 word eBay search string a professional reseller would use.
"categoria": ONE of: Sneakers, Watches, Electronics, Guitars & Basses, Books/Media, Collectibles, Health & Beauty, Others
"confianca": Integer 0-100.
"atributos": List of max 3 key distinguishing attributes.
"pergunta_extra": The single most important piece of info NOT visible in the image that would improve eBay price accuracy. Write it as a natural question (e.g. "What size are these? (e.g. US 10)"). If nothing important is missing, return null.
Region context: {region}. Write ALL values in English.
Respond ONLY valid JSON: {{"produto":"...","ebay_query":"...","categoria":"...","confianca":85,"atributos":[...],"pergunta_extra":"..."}}
                        """
                        res_id = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt_id_rapido, img])
                        texto_id = res_id.text.replace("```json","").replace("```","").strip()
                        jm_id = re.search(r'\{.*?\}', texto_id, re.DOTALL)
                        if jm_id:
                            texto_id = jm_id.group()
                        di = json.loads(texto_id)
                    except:
                        di = {"produto": nome_fich, "ebay_query": nome_fich, "categoria": "Others", "confianca": 0, "atributos": [], "pergunta_extra": None}

                    custo = float(row.get(f"Cost ({currency})", row.get("Cost", 0.0)))
                    sabe = not row.get("Unknown Cost", False)
                    cond_t = row.get("Condition", "Used")
                    obj_f = "Buy" if "Buying" in modo_geral else "Sell" if "Selling" in modo_geral else row.get("Action", "Sell")

                    st.session_state.bulk_fase1.append({
                        "file": nome_fich,
                        "produto": di.get("produto", nome_fich),
                        "ebay_query": di.get("ebay_query", nome_fich),
                        "categoria": di.get("categoria", "Others"),
                        "confianca": di.get("confianca", 0),
                        "atributos": di.get("atributos", []),
                        "pergunta_extra": di.get("pergunta_extra"),
                        "resposta_extra": "",
                        "custo": custo,
                        "sabe_custo": sabe,
                        "condicao": cond_t,
                        "objetivo": obj_f,
                    })
                    barra.progress((i + 1) / total, text=f"✅ {nome_fich}")

                st.rerun()

        # ── FASE 1.5: mostrar perguntas ao utilizador ──
        if st.session_state.get("bulk_fase1") and not st.session_state.bulk_results:
            st.divider()
            st.markdown("### 🤖 AI identified your items — fill in any missing details")
            st.caption("Leave blank or click **Don't know** to run a general search.")

            for idx, item in enumerate(st.session_state.bulk_fase1):
                with st.container(border=True):
                    c_img, c_info, c_q = st.columns([1, 2, 2])
                    with c_img:
                        img_prev = st.session_state.bulk_images.get(item["file"])
                        if img_prev:
                            st.image(img_prev, use_container_width=True)
                    with c_info:
                        st.markdown(f"**{item['produto']}**")
                        st.caption(f"{item['categoria']} | AI confidence: {item['confianca']}%")
                    with c_q:
                        if item["pergunta_extra"]:
                            col_inp, col_dk = st.columns([3, 1])
                            with col_inp:
                                resposta = st.text_input(
                                    item["pergunta_extra"],
                                    value=item["resposta_extra"],
                                    key=f"resp_{idx}",
                                )
                                st.session_state.bulk_fase1[idx]["resposta_extra"] = resposta
                            with col_dk:
                                st.write("")
                                if st.button("Don't know", key=f"dk_{idx}"):
                                    st.session_state.bulk_fase1[idx]["resposta_extra"] = ""
                        else:
                            st.caption("✅ No extra info needed")

            btn_processar = st.button("🚀 Search eBay & Get Prices", type="primary", use_container_width=True)

            if btn_processar:
                barra2 = st.progress(0, text="Searching eBay...")
                total2 = len(st.session_state.bulk_fase1)

                for i, item in enumerate(st.session_state.bulk_fase1):
                    if trava_seguranca_global():
                        st.error(f"🛑 Global limit at item {i+1}.")
                        break
                    pode, saldo = gerir_creditos(st.session_state.email_logado)
                    if not modo_simulacao and not pode:
                        st.warning(f"⚠️ Credits exhausted at item {i+1}.")
                        break

                    nome_fich = item["file"]
                    img = st.session_state.bulk_images.get(nome_fich)
                    if not img:
                        continue

                    ebay_query_final = item["ebay_query"]
                    if item["resposta_extra"].strip():
                        ebay_query_final = f"{item['ebay_query']} {item['resposta_extra'].strip()}"

                    custo = item["custo"]
                    sabe = item["sabe_custo"]
                    cond_c = "Brand New" if item["condicao"] == "Brand New" else "Parts" if item["condicao"] == "Parts" else "Used"
                    obj_f = item["objetivo"]

                    if i > 0:
                        time.sleep(2)
                    barra2.progress((i + 0.5) / total2, text=f"🔍 {nome_fich}...")

                    if not modo_simulacao:
                        supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()

                    token = garantir_token_ebay()
                    items_scored, fonte_dados, query_usada = pesquisar_ebay_profissional(
                        token, item["produto"], ebay_query_final, item["categoria"], cond_c, marketplace_atual)

                    dados_validados = []
                    for it in items_scored:
                        try:
                            titulo = it.get('title','')
                            cid = str(it.get('conditionId',''))
                            if cond_c == "Brand New":
                                if cid not in ["1000","1500","1750","2000"]: continue
                            elif cond_c == "Parts":
                                if cid != "7000": continue
                            else:
                                if cid in ["1000","1500","1750","7000"]: continue
                            if not item_passa_filtro(titulo, cond_c, query_usada): continue
                            valor = float(it.get('price',{}).get('value',0))
                            if valor < 3.0: continue
                            try:
                                ops = it.get('shippingOptions',[])
                                envio = float(ops[0].get('shippingCost',{}).get('value',0)) if ops else 0.0
                            except:
                                envio = 4.50
                            if envio > 40.0: continue
                            dados_validados.append({"preco": valor, "envio": envio, "titulo": titulo})
                        except:
                            continue

                    dados_filtrados = []
                    if dados_validados:
                        lp = [d["preco"] for d in dados_validados]
                        med = np.median(lp)
                        q1_v = np.percentile(lp,25)
                        q3_v = np.percentile(lp,75)
                        iqr = q3_v - q1_v
                        lower = max(q1_v - 1.5*iqr, med*0.25)
                        upper = q3_v + 1.5*iqr
                        dados_filtrados = [d for d in dados_validados if lower <= d["preco"] <= upper]
                        if not dados_filtrados:
                            dados_filtrados = dados_validados
                    num_amostra = len(dados_filtrados)

                    if fonte_dados == "sold":
                        str_pct, str_label, str_cor = _calcular_str(num_amostra, 0)
                    elif fonte_dados == "active":
                        str_pct, str_label, str_cor = _calcular_str(0, num_amostra)
                    else:
                        str_pct, str_label, str_cor = None, "No data", "⚪"

                    if dados_filtrados and num_amostra >= 2:
                        p_venda, portes_medios, stats = _preco_otimizado(dados_filtrados, fonte_dados)
                        p_medio = stats["mediana"]
                        p25_v = stats["p25"]
                        p75_v = stats["p75"]
                        spread = stats["spread_pct"]
                    else:
                        p_venda = p_medio = portes_medios = 0.0
                        p25_v = p75_v = spread = 0.0
                        stats = {}

                    if p_medio > 0:
                        comissao = calculate_ebay_fees(
                            region=region, seller_type=seller_type, vat_registered=vat_registered,
                            categoria=item["categoria"], sale_price=p_venda, store_plan=store_plan,
                            top_rated=top_rated, intl_shipping_method=intl_shipping, buyer_location="Domestic"
                        )
                        taxas_estimadas = portes_medios + comissao
                        custo_real = 0 if not sabe else custo
                        lucro = p_venda - custo_real - taxas_estimadas
                        margem_pct = (lucro / p_venda * 100) if p_venda > 0 else 0
                        roi_pct = (lucro / custo_real * 100) if custo_real > 0 else None
                        dom = {"🇺🇸 USA ($)":"ebay.com","🇬🇧 UK (£)":"ebay.co.uk","🇵🇹 Portugal (€)":"ebay.es"}.get(region,"ebay.com")
                        cu_map = {"Brand New":"&LH_ItemCondition=3","Parts":"&LH_ItemCondition=7000","Used":"&LH_ItemCondition=4"}
                        fu = cu_map.get(cond_c,"&LH_ItemCondition=4")
                        qu = query_usada.replace(' ','+')
                        link_sold = f"https://www.{dom}/sch/i.html?_nkw={qu}&LH_Sold=1&LH_Complete=1{fu}"
                        link_active = f"https://www.{dom}/sch/i.html?_nkw={qu}{fu}"
                        if lucro < 0: cor = "🔴"
                        elif margem_pct >= 20 and num_amostra >= 5: cor = "🟢"
                        elif margem_pct >= 8: cor = "🟡"
                        else: cor = "🔴"
                        fl = "✅ Sold listings" if fonte_dados == "sold" else "⚠️ Active listings"
                        pmc = round(p_venda - taxas_estimadas, 2)
                        sv = f"|⚠️ Volatile mkt ({spread:.0f}%)" if spread > 35 else ""
                        rt = f"|ROI:{roi_pct:.0f}%" if roi_pct is not None else ""
                        rl = f"{region}|{seller_type}"
                        if lucro < 0:
                            estrategia = f"❌ Loss {currency}{abs(round(lucro,2))}|{fl}|{num_amostra} refs|Source below {currency}{pmc}{sv}"
                        elif margem_pct < 8:
                            estrategia = f"⚠️ Tight {round(margem_pct,1)}% margin{rt}|{fl}|{num_amostra} refs[{rl}]{sv}"
                        elif margem_pct >= 20:
                            estrategia = f"🔥 Excellent {round(margem_pct,1)}%{rt}|{fl}|{num_amostra} refs|Strong demand[{rl}]{sv}"
                        else:
                            estrategia = f"👍 Solid {round(margem_pct,1)}%{rt}|{fl}|{num_amostra} refs[{rl}]{sv}"
                    else:
                        taxas_estimadas = lucro = margem_pct = p_medio = p_venda = 0.0
                        roi_pct = None
                        p25_v = p75_v = spread = 0.0
                        cor = "⚪"
                        link_sold = link_active = ""
                        estrategia = "No eBay data found. Try a clearer photo or fill in more details."

                    dados = {
                        "produto": item["produto"],
                        "ebay_query": ebay_query_final,
                        "query_usada": query_usada,
                        "categoria": item["categoria"],
                        "atributos": item["atributos"],
                        "confianca_ia": item["confianca"],
                        "fonte_dados": fonte_dados,
                        "preco_medio": round(p_medio,2),
                        "preco_p25": round(p25_v,2),
                        "preco_p75": round(p75_v,2),
                        "sugestao_venda": round(p_venda,2),
                        "taxas_estimadas": round(taxas_estimadas,2),
                        "lucro_estimado": round(lucro,2),
                        "margem_pct": round(margem_pct,1),
                        "roi_pct": round(roi_pct,1) if roi_pct is not None else None,
                        "custo_compra": custo if sabe else 0,
                        "link_pesquisa": link_sold,
                        "link_ativo": link_active,
                        "estrategia_base": estrategia,
                        "veredito_cor": cor,
                        "num_amostra": num_amostra,
                        "sell_through_rate": str_pct,
                        "str_label": str_label,
                        "str_cor": str_cor,
                        "pergunta_extra": item["pergunta_extra"],
                    }

                    if not modo_simulacao:
                        gastar_credito(st.session_state.email_logado)

                    roi_v = dados.get('roi_pct')
                    roi_s = f"{roi_v:.0f}%" if roi_v is not None else "—"
                    st.session_state.bulk_results.append({
                        "File": nome_fich,
                        f"Cost ({currency})": f"{currency}{custo}",
                        "Item": dados.get('produto','Unknown'),
                        "Verdict": dados.get('veredito_cor','🟡'),
                        f"Median ({currency})": f"{currency}{dados.get('preco_medio',0)}",
                        f"Target ({currency})": f"{currency}{dados.get('sugestao_venda',0)}",
                        f"Fees ({currency})": f"{currency}{dados.get('taxas_estimadas',0)}",
                        f"Profit ({currency})": f"{currency}{dados.get('lucro_estimado',0)}",
                        "Margin %": f"{dados.get('margem_pct',0):.1f}%",
                        "ROI": roi_s,
                        "STR": dados.get('str_label','—'),
                        "AI Conf.": f"{dados.get('confianca_ia',0)}%",
                        "Source": dados.get('fonte_dados','?'),
                        "Strategy": dados.get('estrategia_base'),
                        "eBay Link": dados.get('link_pesquisa',''),
                        "Raw": dados
                    })
                    guardar_no_historico(dados, obj_f, st.session_state.email_logado)
                    barra2.progress((i + 1) / total2, text=f"✅ {nome_fich}")

                st.session_state.bulk_fase1 = []
                if st.session_state.bulk_results:
                    st.success(f"✅ Done! {len(st.session_state.bulk_results)}/{total2} analysed.")
                st.rerun()


                    
    if st.session_state.bulk_results:
        st.divider()
        st.markdown("### 📊 Batch Report")
        df_res = pd.DataFrame(st.session_state.bulk_results)
        cols = [c for c in df_res.columns if c != "Raw"]
        st.dataframe(df_res[cols], use_container_width=True)
        
        verdes = sum(1 for r in st.session_state.bulk_results if r.get("Verdict") == "🟢")
        profits = []
        for r in st.session_state.bulk_results:
            try: 
                v = r.get(f"Profit ({currency})", f"{currency}0")
                profits.append(float(str(v).replace(currency, '').replace(',', '.').strip()))
            except: 
                pass
        total_p = sum(profits)
        
        rois = []
        for r in st.session_state.bulk_results:
            try: 
                rv = r.get("ROI", "—").replace("%", "").strip()
                if rv != "—":
                    rois.append(float(rv))
            except: 
                pass
                
        cs1, cs2, cs3, cs4 = st.columns(4)
        cs1.metric("Total Items", len(st.session_state.bulk_results))
        cs2.metric("Profitable 🟢", verdes)
        cs3.metric("Total Profit", f"{currency}{round(total_p, 2)}")
        cs4.metric("Avg ROI", f"{np.mean(rois):.0f}%" if rois else "—")
        
        try:
            excel = converter_para_excel(df_res)
            st.download_button(
                "📥 Download Excel", excel, "valurise_report.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
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
                    bv = (f"👋 Ready for **{item_d['Item']}** {item_d['Verdict']} | Target:{item_d.get(f'Target ({currency})','?')} | "
                          f"Profit:{item_d.get(f'Profit ({currency})','?')} | STR:{item_d.get('STR','?')}. What do you want to know?")
                    st.session_state.chat_history_bulk.append({"role": "assistant", "content": bv})
                    
            cc_bulk = st.container(height=380)
            with cc_bulk:
                for msg in st.session_state.chat_history_bulk:
                    with st.chat_message(msg["role"]): 
                        st.markdown(msg["content"])
                        
            if pb := st.chat_input("Ask about this item...", key="chat_in_bulk"):
                st.session_state.chat_history_bulk.append({"role": "user", "content": pb})
                with cc_bulk:
                    with st.chat_message("user"): 
                        st.markdown(pb)
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
        resp_news = supabase.table("noticias").select("*").order("created_at", desc=True).limit(10).execute()
        noticias = resp_news.data
        if noticias:
            for n in noticias:
                with st.container(border=True):
                    ct, ci = st.columns([3, 1])
                    with ct:
                        st.subheader(n['titulo'])
                        dl = n['created_at'][:10] if 'created_at' in n else "Hoje"
                        st.caption(f"📅 {dl} | 🏷️ {n.get('categoria', 'Market Trends')}")
                        if 'conteudo' in n and n['conteudo']: 
                            st.markdown(n['conteudo'])
                        if 'link' in n and n['link']: 
                            st.link_button("Ler Artigo Completo 🔗", n['link'])
                    with ci:
                        if 'imagem_url' in n and n['imagem_url']: 
                            st.image(n['imagem_url'], use_container_width=True)
                        else: 
                            st.markdown("<h1 style='text-align:center;color:#475569;'>🗞️</h1>", unsafe_allow_html=True)
        else: 
            st.info("No news yet. Come back soon!")
    except Exception as e: 
        st.error(f"Error loading news: {e}")

# ==========================================
# ABA HISTÓRICO — ROI Dashboard + STR
# ==========================================
with aba_historico:
    st.markdown("### 📜 Your Analysis History")
    try:
        res_h = supabase.table("historico_scans").select("*").eq("email", st.session_state.email_logado).order("created_at", desc=True).execute()
        if res_h.data:
            df_h = pd.DataFrame(res_h.data)
            st.markdown("#### 💰 Accumulated ROI Dashboard")
            
            lucros_h = pd.to_numeric(df_h.get("lucro_estimado", pd.Series(dtype=float)), errors='coerce').fillna(0)
            custos_h = pd.to_numeric(df_h.get("custo_compra", pd.Series(dtype=float)), errors='coerce').fillna(0)
            vendas_h = pd.to_numeric(df_h.get("sugestao_venda", pd.Series(dtype=float)), errors='coerce').fillna(0)
            taxas_h = pd.to_numeric(df_h.get("taxas_estimadas", pd.Series(dtype=float)), errors='coerce').fillna(0)
            
            total_inv = custos_h.sum()
            total_lucro = lucros_h.sum()
            total_vendas = vendas_h.sum()
            total_taxas = taxas_h.sum()
            
            roi_ac = (total_lucro / total_inv * 100) if total_inv > 0 else None
            avg_lucro = lucros_h[lucros_h != 0].mean() if len(lucros_h[lucros_h != 0]) > 0 else 0
            n_luc = int((lucros_h > 0).sum())
            n_tot = len(df_h)
            
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Total Scans", n_tot)
            d2.metric("Profitable 🟢", f"{n_luc}/{n_tot}")
            d3.metric("Total Est. Profit", f"{currency}{round(total_lucro, 2)}")
            d4.metric("Accumulated ROI", f"{roi_ac:.0f}%" if roi_ac is not None else "—")
            
            d5, d6, d7, d8 = st.columns(4)
            d5.metric("Total Invested", f"{currency}{round(total_inv, 2)}")
            d6.metric("Est. Revenue", f"{currency}{round(total_vendas, 2)}")
            d7.metric("Total eBay Fees", f"{currency}{round(total_taxas, 2)}")
            d8.metric("Avg Profit/Item", f"{currency}{round(avg_lucro, 2)}")
            
            # Gráfico acumulado
            if 'created_at' in df_h.columns:
                try:
                    dc = df_h[["created_at", "lucro_estimado"]].copy()
                    dc["created_at"] = pd.to_datetime(dc["created_at"]).dt.date
                    dc["lucro_estimado"] = pd.to_numeric(dc["lucro_estimado"], errors='coerce').fillna(0)
                    dc = dc.sort_values("created_at")
                    dc["lucro_acum"] = dc["lucro_estimado"].cumsum()
                    dc = dc.rename(columns={"created_at": "Date", "lucro_acum": f"Cumulative Profit ({currency})"})
                    st.line_chart(dc.set_index("Date")[f"Cumulative Profit ({currency})"], height=200)
                except: 
                    pass
                    
            st.divider()
            st.markdown("#### 📋 Item History")
            
            cols_disp = [c for c in ["cor", "produto", "preco_medio", "sugestao_venda", "taxas_estimadas", "lucro_estimado", "custo_compra", "sell_through_rate", "objetivo", "estrategia", "link_mercado"] if c in df_h.columns]
            
            ccfg = {
                "cor": "Verdict", "produto": "Item Name",
                "preco_medio": st.column_config.NumberColumn("Median Price", format="%.2f"),
                "sugestao_venda": st.column_config.NumberColumn("Target Price", format="%.2f"),
                "taxas_estimadas": st.column_config.NumberColumn("Est. Fees", format="%.2f"),
                "lucro_estimado": st.column_config.NumberColumn("Net Profit", format="%.2f"),
                "custo_compra": st.column_config.NumberColumn("Cost Paid", format="%.2f"),
                "sell_through_rate": st.column_config.NumberColumn("STR %", format="%.0f%%"),
                "link_mercado": st.column_config.LinkColumn("eBay Link"),
                "estrategia": "Strategy", "objetivo": "Goal"
            }
            st.dataframe(df_h[cols_disp], column_config=ccfg, use_container_width=True, hide_index=True)
            
            if "sell_through_rate" in df_h.columns:
                sv = pd.to_numeric(df_h["sell_through_rate"], errors='coerce').dropna()
                if len(sv) > 0: 
                    st.caption(f"📊 Portfolio avg Sell-Through Rate: **{sv.mean():.0f}%**")
                    
            if st.button("🗑️ Clear All History"):
                supabase.table("historico_scans").delete().eq("email", st.session_state.email_logado).execute()
                st.success("🧹 Cleared!")
                time.sleep(1)
                st.rerun()
        else: 
            st.info("No analyses yet. Start scanning!")
    except Exception as e: 
        st.error(f"Error loading history: {e}")

# ==========================================
# ABA SETTINGS
# ==========================================
with aba_settings:
    st.markdown("### ⚙️ Your eBay Seller Profile")
    st.info("Change your marketplace, seller type, store plan or shipping settings. Changes are saved and apply to all future analyses.")
    
    with st.expander("🛒 Edit Seller Profile", expanded=True):
        mostrar_painel_regime(is_setup=False)
        
    st.divider()
    st.markdown("### 📊 Current Active Profile")
    c1, c2, c3 = st.columns(3)
    c1.metric("Marketplace", region)
    c2.metric("Seller Type", seller_type)
    c3.metric("Store Plan", store_plan or "No Store")
    
    c4, c5 = st.columns(2)
    c4.metric("VAT Registered", vat_registered if seller_type == "Business" else "N/A")
    c5.metric("Top Rated", "✅ Yes" if top_rated else "❌ No")
    
    st.divider()
    st.markdown("### 💡 Fee Impact Preview")
    st.caption(f"Estimated eBay fees for a {currency}100 sale in your current profile:")
    
    pf = calculate_ebay_fees(
        region=region, seller_type=seller_type, vat_registered=vat_registered,
        categoria="Others", sale_price=100.0, store_plan=store_plan, top_rated=top_rated
    )
    st.metric(f"Fees on a {currency}100 sale", f"{currency}{pf:.2f}", delta=f"{pf:.1f}% effective rate", delta_color="inverse")

def mostrar_rodape_legal():
    st.divider()
    st.caption("""
    ⚖️ **Legal Disclaimer:** Valurise is an independent AI-powered analysis tool. 
    Estimates are based on public eBay data and Gemini AI vision. 
    Final resale decisions and tax compliance are the sole responsibility of the user. 
    We are not affiliated with eBay Inc.
    """)
mostrar_rodape_legal()

# ==========================================
# 🕵️‍♂️ ZONA DE ADMINISTRAÇÃO 100% INVISÍVEL
# ==========================================
if st.query_params.get("admin") == "valurise2026":
    st.divider()
    st.success("Bem-vindo ao Backoffice, Admin.")
    mostrar_painel_noticias(supabase)