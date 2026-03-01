import streamlit as st
import PIL.Image
import json
import time
import random
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


# --- 1. ZONA DE CONFIGURAÇÃO (O Canto do Ecrã) ---
st.sidebar.header("⚙️ Market Settings")

# O utilizador escolhe a Região logo de início
region = st.sidebar.selectbox(
    "Select your Region", 
    ["🇺🇸 USA ($)", "🇬🇧 UK (£)", "🇵🇹 Portugal (€)"]
)

# --- DEFINIR O MERCADO DO EBAY GLOBALMENTE ---
mapa_marketplaces = {
    "🇺🇸 USA ($)": "EBAY_US",
    "🇬🇧 UK (£)": "EBAY_GB",
    "🇵🇹 Portugal (€)": "EBAY_ES" 
}
marketplace_atual = mapa_marketplaces.get(region, "EBAY_US")

# Definir variáveis padrão (para não dar erro noutras regiões)
# Definir variáveis padrão (para não dar erro noutras regiões)
seller_type = "Business" 
vat_registered = "Yes"
currency = "€"

# A Lógica Inteligente para o UK e US
if region == "🇬🇧 UK (£)":
    currency = "£"
    seller_type = st.sidebar.radio("Account Type", ["Private", "Business"])
    
    # Só pergunta do IVA se for Business
    if seller_type == "Business":
        vat_registered = st.sidebar.radio("Are you VAT Registered?", ["Yes", "No"])
        st.sidebar.caption("If 'No', eBay charges 20% VAT on your seller fees.")
    else:
        st.sidebar.success(f"Private sellers pay 0% final value fees in the UK! 🎉")

elif region == "🇺🇸 USA ($)":
    currency = "$"
    # Nos EUA não há Private/Business nestes moldes, a IA só precisa da categoria depois.


# No início do teu webapp.py
if "client" not in st.session_state:
    try:
        # Puxa as credenciais do cofre
        info_servico = st.secrets["gcp_service_account"]
        
        # DEFINIMOS O SCOPE (O segredo para matar o erro de invalid_scope)
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
        
client = st.session_state.client


def comprimir_imagem(pil_image):
    """Reduz o tamanho da imagem para evitar 429 Resource Exhausted no Tier 1."""
    img_copy = pil_image.copy()
    img_copy.thumbnail((1024, 1024)) # Redimensiona para max 1024px
    return img_copy



def garantir_token_ebay():
    if 'ebay_token' not in st.session_state:
        # Puxa do cofre do Streamlit em vez de estar no código
        try:
            app_id = st.secrets["EBAY_APP_ID"]
            cert_id = st.secrets["EBAY_CERT_ID"]
            st.session_state.ebay_token = get_ebay_token(app_id, cert_id)
        except Exception as e:
            st.error("Error: eBay keys not found in secrets.")
            return None
    return st.session_state.ebay_token


# Lista de e-mails que têm créditos ilimitados
ADMINS = ["afonsocgomesduarte@gmail.com"] # SUBSTITUI pelo teu e-mail real

# Logo no início do código, antes de tudo:

def set_app_icon(icon_path):
    
    # Verifica se o ficheiro existe mesmo antes de tentar ler
    if os.path.exists(icon_path):
        with open(icon_path, "rb") as f:
            data = f.read()
            b64_encoded = base64.b64encode(data).decode()
        
        # O código abaixo "força" o ícone no navegador e no iPhone/Android
        st.markdown(f"""
            <script>
                var link = document.querySelector("link[rel*='icon']") || document.createElement('link');
                link.type = 'image/png';
                link.rel = 'shortcut icon';
                link.href = 'data:image/png;base64,{b64_encoded}?v=2';
                document.getElementsByTagName('head')[0].appendChild(link);
                
                var apple_link = document.querySelector("link[rel='apple-touch-icon']") || document.createElement('link');
                apple_link.rel = 'apple-touch-icon';
                apple_link.href = 'data:image/png;base64,{b64_encoded}?v=2';
                document.getElementsByTagName('head')[0].appendChild(apple_link);
            </script>
        """, unsafe_allow_html=True)
    else:
        # Se não encontrar o ficheiro, avisa-te na barra lateral (apenas para tu saberes)
        st.sidebar.error(f"Error: The file '{icon_path}' was not found on the server.")

# Chama a função logo no início
set_app_icon("app_icon_512.png")

@st.dialog("🚀 Upgrade to PRO Plan")
def popup_upgrade():
    st.write("You've run out of your daily free credits!")
    st.write("With the **PRO Plan**, you get:")
    st.write("- 💎 Unlimited Analyses")
    st.write("- ⚡ Faster Bulk Processing")
    st.write("- 📈 Detailed Reports in Excel")
    
    st.divider()
    st.link_button(f"💎 Obtain Pro - 9.99{currency}/month", "https://tuolinkdostripe.com", use_container_width=True)
    if st.button("Continue on the free plan"):
        st.rerun()

def obter_saldo_visual(email_user):
    """Procura o saldo na base de dados para exibir na interface."""
    try:
        res = supabase.table("users_credits").select("creditos").eq("email", email_user).execute()
        if res.data:
            return res.data[0]['creditos']
        return 0
    except Exception:
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
        print(f"Erro ao guardar no Supabase: {e}")

# ==========================================
# 🏁 INICIALIZAÇÃO DE VARIÁVEIS (MUITO IMPORTANTE)
# ==========================================
modo_simulacao = False # <--- ADICIONA ISTO PARA MATAR OS AVISOS AMARELOS


if "email_logado" not in st.session_state:
    st.session_state.email_logado = None # Começa vazio

if "logado" not in st.session_state:
    st.session_state.logado = False # Para o login de senha inicial

# --- LIGAÇÃO AO SUPABASE ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)


def trava_seguranca_global():
    """Verifica se a App atingiu o limite de segurança de 1400 pedidos hoje."""
    hoje = datetime.now().date().isoformat()
    try:
        # Conta todos os registos na tabela historico_geral para o dia de hoje
        res = supabase.table("historico_geral").select("id", count="exact").eq("data", hoje).execute()
        
        if res.count >= 1400:
            return True # Limite atingido, deve bloquear
        return False
    except Exception as e:
        print(f"Erro na trava global: {e}")
        return False # Em caso de erro técnico, deixa passar

def gerir_creditos(email_user):
    if not email_user:
        return False, 0
    if email_user in ADMINS:
        return True, 9999

    try:
        # 1. Tenta ir buscar o utilizador à tabela
        res = supabase.table("users_credits").select("*").eq("email", email_user).execute()
        user_data = res.data

        # ---------------------------------------------------------
        # 2. SE O UTILIZADOR NÃO EXISTE (O TEU CASO AGORA)
        # ---------------------------------------------------------
        if not user_data:
            # Cria o utilizador com 1 crédito inicial e a data de hoje
            hoje = datetime.now().date().isoformat()
            supabase.table("users_credits").insert({
                "email": email_user, 
                "creditos": 1, 
                "ultimo_reset": hoje
            }).execute()
            
            # Como acabou de ser criado, tem 1 crédito disponível
            return True, 1

        # ---------------------------------------------------------
        # 3. SE O UTILIZADOR JÁ EXISTE
        # ---------------------------------------------------------
        dados_user = user_data[0]
        saldo_atual = dados_user.get("creditos", 0)
        data_ultimo_reset = dados_user.get("ultimo_reset")
        hoje = datetime.now().date().isoformat()

        # Lógica de Reset Diário (Dá 1 crédito se for um novo dia)
        if data_ultimo_reset != hoje:
            supabase.table("users_credits").update({
                "creditos": 1, 
                "ultimo_reset": hoje
            }).eq("email", email_user).execute()
            return True, 1
        
        # Se for o mesmo dia, verifica se tem saldo
        if saldo_atual > 0:
            return True, saldo_atual
        else:
            return False, 0

    except Exception as e:
        st.error(f"Database Error: {e}")
        return False, 0

def gastar_credito(email_utilizador):
    if email_utilizador in ADMINS:
        return
    """Retira 1 crédito após uma análise bem sucedida."""
    res = supabase.table("users_credits").select("creditos").eq("email", email_utilizador).execute()
    novo_saldo = res.data[0]['creditos'] - 1
    supabase.table("users_credits").update({"creditos": novo_saldo}).eq("email", email_utilizador).execute()

def converter_para_excel(df):
    """Converte DF para Excel com formatação condicional de cores (Semáforo)."""
    output = io.BytesIO()
    
    # Usamos o engine 'xlsxwriter' que permite formatar cores
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export = df.copy()
        

        if 'Verdict' in df_export.columns:
            df_export['Verdict'] = df_export['Verdict'].astype(str)\
                .str.replace('🟢', 'YES')\
                .str.replace('🟡', 'MAYBE')\
                .str.replace('🔴', 'NO')

        # 2. LIMPEZA DE NÚMEROS (Tirar a moeda e virar número real)
        colunas_dinheiro = [f'Cost ({currency})', f'Avg Price ({currency})', f'Target Price ({currency})', f'Est. Fees ({currency})', f'Net Profit ({currency})']
        for col in colunas_dinheiro:
            if col in df_export.columns:
                df_export[col] = df_export[col].astype(str).str.replace(f'{currency}', '').str.replace(',', '.').str.strip()
                df_export[col] = pd.to_numeric(df_export[col], errors='coerce')
        
        # Escrever os dados
        sheet_name = 'Results'
        df_export.to_excel(writer, index=False, sheet_name=sheet_name)
        
        # --- A MAGIA DAS CORES (Formatação Condicional) ---
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        
        # Definir as Cores (Fundo + Texto)
        formato_verde = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'}) # Verde Claro
        formato_amarelo = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C5700'}) # Amarelo
        formato_vermelho = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'}) # Vermelho
        
        # Descobrir onde está a coluna "Veredito" dinamicamente
        try:
            col_idx = df_export.columns.get_loc("Veredito")
            ultima_linha = len(df_export) + 1 # +1 por causa do cabeçalho
            
            # Aplicar Regra: Se a célula for igual a "SIM", pinta de Verde
            worksheet.conditional_format(1, col_idx, ultima_linha, col_idx,
                                         {'type': 'cell', 'criteria': 'equal to', 'value': '"SIM"', 'format': formato_verde})
            
            # Aplicar Regra: Se a célula for igual a "TALVEZ", pinta de Amarelo
            worksheet.conditional_format(1, col_idx, ultima_linha, col_idx,
                                         {'type': 'cell', 'criteria': 'equal to', 'value': '"TALVEZ"', 'format': formato_amarelo})
            
            # Aplicar Regra: Se a célula for igual a "NAO", pinta de Vermelho
            worksheet.conditional_format(1, col_idx, ultima_linha, col_idx,
                                         {'type': 'cell', 'criteria': 'equal to', 'value': '"NAO"', 'format': formato_vermelho})
            
            # (Opcional) Ajustar largura da coluna para ficar bonito
            worksheet.set_column(col_idx, col_idx, 15)
            
        except Exception as e:
            pass # Se não encontrar a coluna, segue em frente sem pintar

    return output.getvalue()

# ==========================================
# 🎨 CONFIGURAÇÃO
# ==========================================




# --- FUNÇÃO DE AVISO LEGAL (Coloca isto junto das outras funções) ---
def mostrar_rodape_legal():
    st.markdown("---") # Uma linha separadora subtil
    with st.expander("ℹ️ Legal Notice and Disclaimer (Read carefully)"):
        st.markdown("""
        **1. Informational Nature:** **Valurise** is a decision-support tool. Price estimates, profit margins, and descriptions are generated by Artificial Intelligence and do not constitute financial or professional advice.
        
        **2. Possibility of Error:** This application uses **Google Gemini** technology. Although advanced, AI can occasionally generate inaccurate, outdated, or incorrect information.
        
        **3. User Responsibility:** You are solely responsible for verifying the accuracy of information and the actual condition of items before any transaction. Valurise is not responsible for any financial losses.
        
        *By using this tool, you accept these terms.*
        """)
        st.caption("Powered by Google Gemini AI • Valurise © 2026")

# ==========================================
# 🔒 LOGIN
# ==========================================
SENHA_SECRETA = "1234" 

if "logado" not in st.session_state:
    st.session_state["logado"] = False

if not st.session_state["logado"]:
    st.title("🔒 Restricted Area")
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        entrada = st.text_input("Password:", type="password")
        if st.button("Login", type="primary", use_container_width=True):
            if entrada == SENHA_SECRETA:
                st.session_state["logado"] = True
                st.rerun()
            else:
                st.error("Wrong password!")
    st.stop()
#=============================================
if "historico_conversas" not in st.session_state: 
    st.session_state.historico_conversas = []

if "id_conversa_ativa" not in st.session_state: 
    st.session_state.id_conversa_ativa = None

# (Verifica também se tens estas aqui, já agora)
if "single_result" not in st.session_state: st.session_state.single_result = None
if "chat_history_single" not in st.session_state: st.session_state.chat_history_single = []
if "chat_session_single" not in st.session_state: st.session_state.chat_session_single = None
#==============================================

# --- 2. O MOTOR DE CÁLCULO DAS TAXAS ---
def calculate_ebay_fees(region, seller_type, vat_registered, category, sale_price):
    fees = 0.0
    fixed_fee = 0.0

    # ---------------- MERCADO EUA 🇺🇸 ----------------
    if region == "🇺🇸 USA ($)":
        fixed_fee = 0.30
        
        if category == "Sneakers":
            if sale_price >= 150:
                fees = (sale_price * 0.08) + 0.00 # Isento de taxa fixa acima de $150
            else:
                fees = (sale_price * 0.1325) + fixed_fee
        
        elif category == "Tech":
            # Exemplo Tech EUA (podes afinar este valor depois se quiseres)
            fees = (sale_price * 0.0635) + fixed_fee
            
        else: # Categoria Geral
            fees = (sale_price * 0.1325) + fixed_fee

    # ---------------- MERCADO UK 🇬🇧 ----------------
    elif region == "🇬🇧 UK (£)":
        if seller_type == "Private":
            return 0.0 # A regra de ouro: Zero taxas!
            
        fixed_fee = 0.30
        
        if category == "Sneakers":
            if sale_price >= 100:
                fees = (sale_price * 0.07) + fixed_fee
            else:
                fees = (sale_price * 0.119) + fixed_fee
                
        elif category == "Tech":
            if sale_price <= 400:
                fees = (sale_price * 0.069) + fixed_fee
            else:
                fees = (400 * 0.069) + ((sale_price - 400) * 0.02) + fixed_fee
                
        else: # Categoria Geral (Clothes, etc)
            fees = (sale_price * 0.119) + fixed_fee

        # A "Rasteira" do IVA: Se é Business e NÃO está registado, o eBay cobra +20%
        if seller_type == "Business" and vat_registered == "No":
            fees = fees * 1.20

    # ---------------- MERCADO EUROPA 🇪🇺 ----------------
    elif region == "🇵🇹 Portugal (€)":
        fixed_fee = 0.35

        # 1. Calçado Esportivo (Sneakers)
        if category == "Calçado Esportivo":
            if sale_price >= 150:
                return sale_price * 0.08 # 8% e isento da tarifa fixa
            else:
                return (sale_price * 0.136) + fixed_fee

        # 2. Relógios de Luxo e Normais
        elif category == "Relógios":
            if sale_price >= 2000:
                return (sale_price * 0.065) # 6.5% para relógios de luxo
            else:
                return (sale_price * 0.15) + fixed_fee # 15% para relógios normais

        # 3. Guitarras e Baixos
        elif category == "Guitarras e Baixos":
            return (sale_price * 0.067) + fixed_fee # 6.7%

        # 4. Livros, Filmes e Música
        elif category == "Livros/Mídia":
            return (sale_price * 0.153) + fixed_fee # 15.3%

        # 5. Colecionáveis (Cartas, Moedas, Figuras)
        elif category == "Colecionáveis":
            return (sale_price * 0.1325) + fixed_fee # 13.25%

        # 6. Eletrónica (Telemóveis, Consolas, Computadores)
        elif category == "Eletrónica":
            return (sale_price * 0.09) + fixed_fee # Geralmente ronda os 9%

        # 7. Regra Geral (Para tudo o resto)
        else:
            return (sale_price * 0.136) + fixed_fee
    return fees


# --- SISTEMA DE FILTRO DE CONDIÇÃO AVANÇADO ---
HARD_REJECT = ["for parts", "for part", "not working", "broken", "faulty", "defective", "spares or repair", "spares and repair", "parts only", "repair only", "non functional", "does not work", "don't work", "damaged", "cracked","para peças", "avariado", "estragado", "partido", "defeito", "não funciona"]
LIKELY_INCOMPLETE = ["missing", "no battery", "no charger", "no box", "no cable", "no cables", "no controller", "no remote", "no power supply", "no psu", "no accessories", "without charger", "without battery", "without box", "without accessories", "unit only", "console only", "tablet only", "device only", "base unit only", "main unit only","em falta", "falta", "sem bateria", "sem carregador", "sem caixa", "apenas consola"]
SUSPECT = ["untested", "test not done", "unable to test", "not tested", "unknown condition", "read description", "see description", "as is", "as-is", "no returns", "fair condition",]
POSITIVE = ["complete", "fully working", "full set", "all accessories", "includes charger", "includes box", "includes accessories", "original box included", "perfect working"]

# Novas Listas para separar Novos de Usados
NEW_KEYWORDS = ["sealed", "bnib", "nib", "unopened", "brand new", "factory sealed", "new in box","selado", "novo", "na caixa", "fechado", "por abrir"]
USED_KEYWORDS = ["used", "pre-owned", "preowned", "open box", "loose", "built", "played", "good condition", "excellent condition","usado", "segunda mão", "estimado", "montado"]

# Adiciona as palavras que inflam preços
AVOID_INFLATION = ["console", "consola", "bundle", "lot ", "lote", "joblot", "set of", "graded", "wata", "vga", "ukg", "pcgs"]

def contains_word(text, word):
    """Garante que a palavra é exata (não confunde 'unused' com 'used')"""
    return re.search(r'\b' + re.escape(word) + r'\b', text) is not None

def item_passa_filtro(titulo_ebay, condicao_item, nome_pesquisado=""):
    titulo = titulo_ebay.lower()
    
    # Se é para peças, não queremos coisas a dizer que funcionam perfeitamente
    if condicao_item == "Parts":
        if any(contains_word(titulo, word) for word in POSITIVE + NEW_KEYWORDS): return False
        return True

    # Se é Novo, apenas bloqueamos se o título confessar que é usado, partido ou suspeito
    elif condicao_item == "Brand New":
        NOT_NEW = ["used", "pre-owned", "preowned", "open box", "loose", "built", "played", "no box", "without box", "usado", "montado", "sem caixa"]
        if any(contains_word(titulo, word) for word in HARD_REJECT + LIKELY_INCOMPLETE + SUSPECT + NOT_NEW): return False
        return True

    # Se é Usado, bloqueamos o lixo avariado, mas deixamos os títulos normais passarem
    else: # "Used"
        if any(contains_word(titulo, word) for word in HARD_REJECT + LIKELY_INCOMPLETE): return False
        # Retiramos a proibição de palavras "NEW" aqui, porque muitos vendedores escrevem "Like New" (Como Novo) nos usados.
        return True

def analisar_imagem_json(image, custo, objetivo, sabe_custo, condicao):
    try:
        prompt_id = """
        Act as an expert inventory scanner. Analyze the image and extract:
        1. OCR: All text on the packaging (Brand, Model, Shades, Editions).
        2. BARCODE: If visible, extract the numbers.
        3. If no barcode, identify the exact model by design.
        
        Classify the item STRICTLY into one of these eBay categories: 
        "Sneakers", "Watches", "Electronics", "Guitars & Basses", "Books/Media", "Collectibles" or "Others".
        
        Respond ONLY in a valid JSON format. Provide the values in English, but keep these exact Portuguese keys:
        {"produto": "Full Commercial Name + Barcode(if it has one)", "categoria": "Chosen Category"}
        """
        
        res_visao = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=[prompt_id, image]
        )
        
        # Lógica de extração segura para não quebrar a app se a IA falhar o JSON
        texto_limpo = res_visao.text.replace("```json", "").replace("```", "").strip()
        try:
            dados_ia = json.loads(texto_limpo)
            nome_item = dados_ia.get("produto", "Item Desconhecido")
            categoria_item = dados_ia.get("categoria", "Outros")
        except:
            nome_item = res_visao.text.strip() # Fallback para o teu método antigo
            categoria_item = "Outros"
        
        # --- PASSO 2: CONSULTA AO MOTOR EBAY ---
        token = garantir_token_ebay()
        dados_ebay = buscar_precos_ebay(token, nome_item, marketplace_id=marketplace_atual)
        
        item_summaries = dados_ebay.get('itemSummaries', [])
        dados_validados = [] 
        
        for item in item_summaries:
            try:
                titulo_anuncio = item.get('title', '')
                condition_id = item.get('conditionId', '')
                
                # Rejeitar lixo logo pelo ID do eBay (7000 = Para Peças)
                if condicao != "Parts" and condition_id == "7000":
                    continue

                # Passamos o nome_item para bloquear as palavras inflacionárias
                if not item_passa_filtro(titulo_anuncio, condicao, nome_item):
                    continue

                valor = float(item.get('price', {}).get('value', 0))
                if valor > 3.0:
                    try:
                        opcoes_envio = item.get('shippingOptions', [])
                        custo_envio = float(opcoes_envio[0].get('shippingCost', {}).get('value', 0)) if opcoes_envio else 0.0
                    except:
                        custo_envio = 4.50

                    if custo_envio > 30.0:
                        continue

            
                    dados_validados.append({"preco": valor, "envio": custo_envio})
            except:
                continue

        # --- PASSO 3: MOTOR DE PUREZA ESTATÍSTICA (AMOSTRA GRANDE) ---
        # --- PASSO 3: MOTOR DE PUREZA ESTATÍSTICA (VERSÃO EQUILIBRADA) ---
        if dados_validados:
            lista_precos = [d["preco"] for d in dados_validados]
            mediana_real = np.median(lista_precos)
            
            # 1. Filtro de Chão (Suavizado para 35% e 15%)
            if condicao == "Brand New":
                dados_validados = [d for d in dados_validados if d["preco"] >= (mediana_real * 0.35)]
            else:
                dados_validados = [d for d in dados_validados if d["preco"] >= (mediana_real * 0.15)]
            
            # 2. Filtro de Teto (Alargado para 1.8x)
            # Ex: Se a mediana for 50€, aceitamos preços até 90€. Corta na mesma consolas de 160€!
            dados_validados = [d for d in dados_validados if d["preco"] <= (mediana_real * 1.8)]
            
            # 3. Guilhotina de Desvio Padrão (Mais justa)
            if len(dados_validados) >= 3:
                lista_atualizada = [d["preco"] for d in dados_validados]
                media_bruta = np.mean(lista_atualizada)
                desvio = np.std(lista_atualizada)

                # 1.5 é o padrão de ouro estatístico. Retém dados normais e apaga só os absurdos.
                dados_seguros = [d for d in dados_validados if abs(d["preco"] - media_bruta) <= (desvio * 1.5)]
                if dados_seguros:
                    dados_validados = dados_seguros

            # 4. Exigimos apenas 2 anúncios sobreviventes
            if len(dados_validados) >= 2:
                p_medio = sum(d["preco"] for d in dados_validados) / len(dados_validados)
                portes_medios = sum(d["envio"] for d in dados_validados) / len(dados_validados)
                p_venda = p_medio * 0.9 
            else:
                p_medio = p_venda = portes_medios = 0.0
        else:
            p_medio = p_venda = portes_medios = 0.0

        # --- PASSO 4: CÁLCULO DE TAXAS E ESTRATÉGIA ---
        # Se encontrou preços válidos no eBay, faz a matemática:
        if p_medio > 0:
            comissao_plataforma = calculate_ebay_fees(region, seller_type, vat_registered, categoria_item, p_venda) 
            taxas_estimadas = portes_medios + comissao_plataforma
            
            custo_real = 0 if not sabe_custo else custo
            lucro = p_venda - custo_real - taxas_estimadas
            
            # Garantir o domínio certo para o link do botão
            dominio = "ebay.co.uk" if region == "🇬🇧 UK (£)" else "ebay.es" if region == "🇵🇹 Portugal (€)" else "ebay.com"
            link_mercado = f"https://www.{dominio}/sch/i.html?_nkw=\"{nome_item.replace(' ', '+')}\"&LH_Sold=1"
            
            cor = "🟢" if lucro > 10 else "🟡"
            if lucro < 0: cor = "🔴"
            
            if not sabe_custo:
                estrategia = f"Active market ({len(dados_validados)} sales). Since you don't know the cost, any purchase you make must leave a margin given the {currency}{round(lucro, 2)} net profit remaining after fees."
            else:
                if lucro < 0:
                    estrategia = "❌ Loss ahead! The cost and fees devour the sale value. You should try to find it much cheaper."
                elif lucro < 5:
                    estrategia = "⚠️ Very tight margin. Only worth it if the sale is extremely fast."
                elif lucro >= 15 and len(dados_validados) > 5:
                    estrategia = "🔥 Excellent deal! You'll make substantial profit and the market is eager for this item."
                else:
                    estrategia = "👍 Solid business. Acceptable margin and stable market for selling."
            
            if p_venda > 200:
                estrategia += " ⚠️ HIGH VALUE: This item appears to be high-end. Always check the eBay link to confirm special editions before investing."
                
        # Se NÃO encontrou preços, ativa o Plano B (A IA tenta adivinhar o preço pela imagem)
        else:
            prompt_estimativa = f"""
            I couldn't find recent sales references on eBay for "{nome_item}". 
            Act as a specialist appraiser of resale items. Look carefully at the image, evaluate the product type, brand, materials and apparent condition.
            Give me a realistic selling price in the local currency ({currency}) and a brief justification for that value.
            Respond ONLY in this exact JSON format:
            {{"preco": X, "justificativa": "Although there is no sales history, similar products from this brand/style usually sell for around X because..."}}
            """
            
            try:    
                res_estimativa = client.models.generate_content(
                    model='gemini-2.0-flash', 
                    contents=[prompt_estimativa, image]
                )
                texto_json = res_estimativa.text.replace("```json", "").replace("```", "").strip()
                dados_ia = json.loads(texto_json)
                
                p_venda = float(dados_ia.get("preco", 0))
                justificativa = dados_ia.get("justificativa", "Evaluation based on general appearance.")
                
                p_medio = p_venda 
                portes_medios = 4.50 
                comissao_plataforma = p_venda * 0.13
                taxas_estimadas = portes_medios + comissao_plataforma
                
                custo_real = 0 if not sabe_custo else custo
                lucro = p_venda - custo_real - taxas_estimadas
                
                dominio = "ebay.co.uk" if region == "🇬🇧 UK (£)" else "ebay.es" if region == "🇵🇹 Portugal (€)" else "ebay.com"
                link_mercado = f"https://www.{dominio}/sch/i.html?_nkw={nome_item.replace(' ', '+')}"
                
                cor = "🔮" 
                if lucro < 0: cor = "🔴"
                elif lucro > 10: cor = "🟢"
                
                estrategia = f"I did not find any recent sales data for this item on eBay. My AI estimated the value based on visual inspection: {justificativa}"
                
            except Exception as e:
                p_medio = p_venda = lucro = taxas_estimadas = 0
                dominio = "ebay.co.uk" if region == "🇬🇧 UK (£)" else "ebay.es" if region == "🇵🇹 Portugal (€)" else "ebay.com"
                link_mercado = f"https://www.{dominio}/sch/i.html?_nkw={nome_item.replace(' ', '+')}"
                cor = "⚪"
                estrategia = "I did not find any recent sales data for this item on eBay and the AI could not estimate the value."

        return {
            "produto": nome_item,
            "preco_medio": round(p_medio, 2),
            "sugestao_venda": round(p_venda, 2),
            "taxas_estimadas": round(taxas_estimadas, 2),
            "lucro_estimado": round(lucro, 2),
            "link_pesquisa": link_mercado,
            "estrategia_base": estrategia,
            "veredito_cor": cor
        }

    except Exception as e:
        return {
            "produto": "Read Error",
            "estrategia_base": f"Technical Error: {str(e)}",
            "veredito_cor": "🔴"
        }
    

def criar_chat_session(dados_completos):
    """Cria uma sessão de chat especialista no contexto do produto analisado."""
    if modo_simulacao:
        return "simulacao"
    
    # Extraímos os dados para criar o contexto "mental" da IA
    nome = dados_completos.get('produto', 'Produto')
    preco_medio = dados_completos.get('preco_medio', 0)
    sugestao = dados_completos.get('sugestao_venda', 0)
    lucro = dados_completos.get('lucro_estimado', 0)
    estrategia = dados_completos.get('estrategia_base', '')
    veredito = dados_completos.get('veredito_cor', '⚪')
    ref = dados_completos.get('estrategia_base', '')

    # Este é o "GPS" da IA. Ela agora sabe PORQUÊ respondeu aquilo.
    contexto_especialista = f"""
    Act as an Expert Consultant in Arbitrage and Reselling.
    You have just analyzed the following product:
    
    - PRODUCT: {nome}
    - AVERAGE PRICE ON EBAY: {currency}{preco_medio}
    - YOUR SUGGESTED SELLING PRICE: {currency}{sugestao}
    - ESTIMATED PROFIT: {currency}{lucro}
    - VERDICT: {veredito}
    - APPLIED LOGIC: {estrategia}
    - REFERENCE: {ref}
    
    INSTRUCTIONS FOR THE CONVERSATION:
    1. Explain your action plan: why did you suggest this price? (Ex: fast-sale strategy vs maximum profit).
    2. If the verdict is 💎 (Rare), warn the user not to rush and explain that there is no stock.
    3. If the user asks "Is it worth it?", use the profit data to justify (ex: "Yes, because the margin is over 30%").
    4. Stay true to the table data, but you can give tips on where to advertise (Vinted, eBay, Wallapop).
    """
    
    
    # Criamos a sessão de chat garantindo que todas as partes são do tipo correto
    st.session_state.chat = client.chats.create(
        model='gemini-2.0-flash',
        history=[
            types.Content(role="user", parts=[types.Part.from_text(text=contexto_especialista)]),
            types.Content(role="model", parts=[types.Part.from_text(text="Understood. I am ready to explain the strategy for this product.")])
        ]
    )
    return st.session_state.chat
# ==========================================
# ⚙️ SIDEBAR
# ==========================================

with st.sidebar:
    st.header("⚙️ Panel")
    
    # 1. IDENTIFICAÇÃO E CRÉDITOS
    if st.session_state.email_logado:
        st.success(f"👤 {st.session_state.email_logado}")
        if st.session_state.email_logado in ADMINS:
            st.metric(label="Plan", value="👑 ADMIN / Unlimited")
        else:
            saldo_atual = obter_saldo_visual(st.session_state.email_logado)
            st.metric(label="Credits available", value=f"{saldo_atual} / 1")
        # ------------------------------

        if st.button("🚪 Exit / Change Account"):
            st.session_state.email_logado = None
            st.rerun()
    else:
        st.warning("No user logged in.")

    st.divider()

# ==========================================
# 📱 INTERFACE
# ==========================================
# No ecrã de Login
st.title("💎 Valurise (Beta Version)")

if not st.session_state.email_logado:
    st.info("👋 You are invited to test the Valurise prototype.")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        email_input = st.text_input("Email (just to create account):")
        
        # Checkbox Simples e Direta
        termos = st.checkbox("I accept to participate in the Beta test and understand that the AI may make mistakes.")

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

    # Rodapé simples (sem moradas nem NIFs)
    with st.expander("ℹ️ About This Prototype and Data Usage"):
        st.markdown("""
        **What is this?**
        This is a prototype created by an independent developer for testing purposes.
        
        **Your data:**
        Your email is only used to log into your account. It will not be sold, shared, or used for spam.
        
        **Disclaimer:**
        The values presented are AI (Gemini) estimates. Always verify actual prices before selling.
        """)
    
    st.stop()

# Se chegou aqui, o email_logado já existe!
st.sidebar.write(f"👤 User: **{st.session_state.email_logado}**")

# Gestão de Sessão (Memória)
if "single_result" not in st.session_state: st.session_state.single_result = None
if "chat_history_single" not in st.session_state: st.session_state.chat_history_single = []
if "chat_session_single" not in st.session_state: st.session_state.chat_session_single = None

if "bulk_results" not in st.session_state: st.session_state.bulk_results = []
if "bulk_images" not in st.session_state: st.session_state.bulk_images = {}
if "chat_history_bulk" not in st.session_state: st.session_state.chat_history_bulk = []
if "chat_session_bulk" not in st.session_state: st.session_state.chat_session_bulk = None
if "current_bulk_item" not in st.session_state: st.session_state.current_bulk_item = None
if "historico_conversas" not in st.session_state: st.session_state.historico_conversas = []
if "id_conversa_ativa" not in st.session_state: st.session_state.id_conversa_ativa = None

# ONDE SUBSTITUIR: Procura onde tens "aba1, aba2 = st.tabs(..."
aba1, aba2, aba3, aba_historico = st.tabs(["🔍 Single Analysis", "📦 Bulk", "📰 News", "📜 History"])


# -----------------------------------------------------------------------------
# ABA 1: INDIVIDUAL (CORRIGIDA - SEM DUPLICAÇÃO)
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# ABA 1: INDIVIDUAL (PROTEGIDA: SÓ GASTA SE NÃO FOR SIMULAÇÃO)
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# ABA 1: AVALIAÇÃO INDIVIDUAL (COM PROTEÇÃO GLOBAL E CRÉDITOS)
# -----------------------------------------------------------------------------
with aba1:
    col_input, col_res = st.columns([1, 2])
    
    with col_input:
        st.write("### 1. Item Data")
        objetivo_single = st.radio("Goal?", ["Sell", "Buy"], horizontal=True, key="obj_single_final")

        # Gestão de custos/estado
        if "temp_custo_ia" in st.session_state:
            st.session_state['single_cost'] = st.session_state.temp_custo_ia
            del st.session_state.temp_custo_ia

        foto_single = st.file_uploader("Upload Photo", type=["jpg", "png"], key="single_up_final")
        
        # --- NOVA CHECKBOX DE CUSTO ---
        # --- NOVA CHECKBOX DE CUSTO E CONDIÇÃO ---
        # --- NOVA ZONA DE CUSTO E CONDIÇÃO ---
        sabe_custo_single = not st.checkbox("I don't know the item cost", key="check_custo_single")
        custo_single = st.number_input(f"Cost ({currency})", min_value=0.0, step=1.0, key="single_cost_final", disabled=not sabe_custo_single)
        
        condicao_single = st.selectbox("Item Condition", ["Used (Complete/Working)", "Brand New (Sealed)", "Incomplete / For Parts"], key="cond_single")
        
        # Traduzir a escolha para a palavra-chave do motor
        if condicao_single == "Brand New (Sealed)": cond_codigo_single = "Brand New"
        elif condicao_single == "Incomplete / For Parts": cond_codigo_single = "Parts"
        else: cond_codigo_single = "Used"

        # --- BOTÃO DE ANÁLISE COM TRAVAS DE SEGURANÇA ---
        if st.button("🚀 Analyse Item", type="primary"):
            if foto_single:
                # 🛡️ TRAVA 1: Limite Global Antibot (1400/dia)
                if trava_seguranca_global():
                    st.error("🛑 The system has reached the daily bonus limit (1400/1500). Try again tomorrow!")
                    st.stop()

                # POR ISTO:
                foto_single.seek(0)
                img_bruta = PIL.Image.open(foto_single)
                img = comprimir_imagem(img_bruta)
                
                # 🛡️ TRAVA 2: Créditos do Utilizador (10 iniciais ou 1 diário)
                pode_avancar, saldo = gerir_creditos(st.session_state.email_logado)
                
                # --- CENÁRIO A: MODO SIMULAÇÃO (Para testes sem gastar API) ---
                if modo_simulacao:
                    with st.spinner("Simulating AI analysis..."):
                        # Registar no contador global para monitorizar tráfego mesmo em simulação
                        supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()
                        
                        dados = analisar_imagem_json(img, custo_single, objetivo_single, sabe_custo_single, cond_codigo_single)
                        dados['id_unico'] = time.time()
                        st.session_state.single_result = dados

                # --- CENÁRIO B: MODO REAL (Gasta Google Grounding) ---
                else:
                    if pode_avancar:
                        with st.spinner(f"Analyzing with Real AI... (Balance: {saldo})"):
                            # 1. Registar pedido no contador global de 1400
                            supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()
                            
    
                            dados = analisar_imagem_json(img, custo_single, objetivo_single, sabe_custo_single, cond_codigo_single)
                            
                            if dados:
                                # --- GUARDAR AUTOMATICAMENTE NO SUPABASE ---
                                
                                guardar_no_historico(dados, objetivo_single,st.session_state.email_logado)

                            # 3. Se a IA respondeu bem, descontar crédito ao utilizador
                            
                            # 3. Se a IA respondeu bem, descontar crédito ao utilizador
                            if "Limite" not in dados.get("produto", ""):
                                gastar_credito(st.session_state.email_logado)
                            
                            dados['id_unico'] = time.time()
                            st.session_state.single_result = dados
                    else:
                        # Se não tem créditos, abre o pop-up de venda
                        popup_upgrade()
            else:
                st.warning("Please upload a photo first.")

    # -------------------------------------------------------------------------
    # MOSTRAR RESULTADOS E CHAT (COLUNA DA DIREITA)
    # -------------------------------------------------------------------------
    if st.session_state.single_result:
        dados = st.session_state.single_result
        
        # Preparar Resumo para o histórico/chat (Atualizado para dados do eBay)
        texto_resumo = f"""**{dados['veredito_cor']} {dados['produto']}**

💰 **Avg Price:** {currency}{dados.get('preco_medio', 0)}
🚀 **Target Price:** {currency}{dados.get('sugestao_venda', 0)}
💸 **Est. Fees:** {currency}{dados.get('taxas_estimadas', 0)}
💶 **Net Profit:** {currency}{dados.get('lucro_estimado', 0)}

📊 **Strategy:** {dados.get('estrategia_base', '')}
"""
        # Guardar no histórico da barra lateral se for um ID novo
        if "ultimo_id_salvo" not in st.session_state or st.session_state.ultimo_id_salvo != dados['id_unico']:
            if foto_single:
                foto_single.seek(0) 
                imagem_aberta = PIL.Image.open(foto_single)
            else: 
                imagem_aberta = None

            st.session_state.chat_history_single = []
            st.session_state.chat_session_single = criar_chat_session(dados)
            primeira_resposta = "Hello! I've analyzed the eBay references for this item. How can I help with your selling plan?"
            st.session_state.chat_history_single.append({"role": "assistant", "content": primeira_resposta})
            
            nova_sessao = {
                "id": dados['id_unico'], 
                "titulo": dados['produto'], 
                "imagem": imagem_aberta, 
                "dados_analise": dados, 
                "resumo": texto_resumo, 
                "historico_chat": st.session_state.chat_history_single
            }
            st.session_state.historico_conversas.insert(0, nova_sessao)
            st.session_state.ultimo_id_salvo = dados['id_unico']
            st.session_state.id_conversa_ativa = dados['id_unico']

        with col_res:
            if foto_single:
                foto_single.seek(0)
                st.image(foto_single, width=220)
            
            st.write("---")
            # Área de Conversa com a IA sobre o item
            container_chat = st.container(height=400)
            with container_chat:
                for msg in st.session_state.chat_history_single:
                    with st.chat_message(msg["role"]): 
                        st.markdown(msg["content"])

            if prompt := st.chat_input("Ask a question about this item...", key="chat_input_unico"):
                st.session_state.chat_history_single.append({"role": "user", "content": prompt})
                with container_chat:
                    with st.chat_message("user"): 
                        st.markdown(prompt)
                    with st.chat_message("assistant"):
                        if modo_simulacao: 
                            resp = f"Simulation response for: {prompt}"
                        else:
                            try: 
                                resp = st.session_state.chat_session_single.send_message(prompt).text
                            except: 
                                resp = "Sorry, an error occurred while processing your question."
                        st.markdown(resp)
                        st.session_state.chat_history_single.append({"role": "assistant", "content": resp})


# ABA 2: BULK (COM CONSUMO DE CRÉDITOS POR ITEM)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# ABA 2: BULK (COM CONSUMO DE CRÉDITOS E TRAVA GLOBAL POR ITEM)
# -----------------------------------------------------------------------------
with aba2:
    st.write("### 1. Configure Batch")
    modo_geral = st.radio("What is this batch?", ["🛒 All for Buying", "🏠 All for Selling", "🔀 Mixed (Decide 1 by 1)"], horizontal=True)
    fotos_bulk = st.file_uploader("Upload Photos", type=["jpg", "png"], accept_multiple_files=True, key="bulk_up")
    
    if fotos_bulk:
        # 1. Criar o "Cofre" BASE (Nunca sobrecrevemos isto com o editor!)
        if "tabela_base" not in st.session_state or len(st.session_state.tabela_base) != len(fotos_bulk):
            dados_iniciais = []
            for f in fotos_bulk:
                dados_iniciais.append({"File": f.name, f"Cost ({currency})": 0.0, "Unknown Cost": False, "Condition": "Used", "Action": "Sell"})
            st.session_state.tabela_base = pd.DataFrame(dados_iniciais)
            
        # 2. Configurar as colunas (Dropdowns)
        col_config = {
            "Condition": st.column_config.SelectboxColumn("Condition", width="medium", options=["Used", "Brand New", "Parts"])
        }
        
        if "Mixed" in modo_geral:
            col_config["Action"] = st.column_config.SelectboxColumn("Action", width="medium", options=["Sell", "Buy"], required=True)
        else:
            col_config["Action"] = None
            
        # 3. O SEGREDO: A tabela editada é uma nova variável e lê da base, mas NÃO sobrecreve a base!
        tabela_editada = st.data_editor(
            st.session_state.tabela_base, 
            num_rows="dynamic", 
            use_container_width=True, 
            key="editor_bulk_limpo", 
            column_config=col_config
        )

        if st.button("🚀 Process Bulk"):
            if not st.session_state.get('email_logado'):
                st.warning("⚠️ You must be logged in to process bulk items.")
            else:
                st.session_state.bulk_results = []
                st.session_state.bulk_images = {}
                barra = st.progress(0)
                
                # 4. Usamos a tabela_editada para o Loop!
                total_items = len(tabela_editada)
                
                for i, row in tabela_editada.iterrows():
                    # --- 🛡️ 1. TRAVAS DE SEGURANÇA ---
                    # --- 🛡️ 1. TRAVAS DE SEGURANÇA ---
                    if trava_seguranca_global():
                        st.error(f"🛑 Global limit reached. Stopped at item {i+1}.")
                        break

                    pode_avancar, saldo = gerir_creditos(st.session_state.email_logado)
                    if not modo_simulacao and not pode_avancar:
                        st.warning(f"⚠️ Credits exhausted on item {i+1}.")
                        popup_upgrade()
                        break

                    # --- 2. DEFINIÇÃO DE DADOS DO ITEM ---
                    nome_fich = row["File"]
                    custo = row[f"Cost ({currency})"]
                    sabe_custo_bulk = not row.get("Unknown Cost", False)
                    
                    # Converter a escolha da tabela para a variável do motor
                    escolha_tabela = row.get("Condition", "Used")
                    if escolha_tabela == "Brand New": cond_codigo_bulk = "Brand New"
                    elif escolha_tabela == "Parts": cond_codigo_bulk = "Parts"
                    else: cond_codigo_bulk = "Used"
                
                    
                    if "Buying" in modo_geral: objetivo_final = "Comprar"
                    elif "Selling" in modo_geral: objetivo_final = "Vender"
                    else: objetivo_final = row["Action"]

                    foto_real = next((f for f in fotos_bulk if f.name == nome_fich), None)
                    
                    if foto_real:
                        if i > 0:
                            time.sleep(3)
                        # POR ISTO:
                        foto_real.seek(0) 
                        img_bruta = PIL.Image.open(foto_real)
                        img = comprimir_imagem(img_bruta) 
                        st.session_state.bulk_images[nome_fich] = img
                        
                        # --- 3. LOOP DE TENTATIVAS (RETRY LOGIC) ---
                        tentativas = 0
                        sucesso = False
                        dados = {}

                        while tentativas < 3 and not sucesso:
                            # Registar pedido no histórico Supabase (apenas se não for simulação)
                            if not modo_simulacao:
                                supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()
                            
                            dados = analisar_imagem_json(img, custo, objetivo_final, sabe_custo_bulk, cond_codigo_bulk)
                            
                            # Detetar erro de Limite (429)
                            if "429" in str(dados) or "Resource exhausted" in str(dados):
                                tentativas += 1
                                st.warning(f"⏳ Google busy. Attempt {tentativas}/3 for '{nome_fich}'. Waiting...")
                                time.sleep(10 * tentativas) 
                            
                            # Detetar outros erros
                            elif "Erro" in dados.get("produto", ""):
                                st.error(f"❌ Error in item {nome_fich}: {dados.get('estrategia_base')}")
                                break 
                            
                            else:
                                sucesso = True
                                if not modo_simulacao:
                                    gastar_credito(st.session_state.email_logado)

                        # --- 4. GUARDAR RESULTADOS (APENAS SE TEVE SUCESSO) ---
            
                        if sucesso:
                            st.session_state.bulk_results.append({
                                "File": nome_fich,
                                f"Cost ({currency})": f"{currency}{custo}",
                                "Item": dados.get('produto', 'Unknown'),
                                "Verdict": dados.get('veredito_cor', '🟡'),
                                f"Avg Price ({currency})": f"{currency}{dados.get('preco_medio', 0)}",
                                f"Target Price ({currency})": f"{currency}{dados.get('sugestao_venda', 0)}",
                                f"Est. Fees ({currency})": f"{currency}{dados.get('taxas_estimadas', 0)}",
                                f"Net Profit ({currency})": "Pending" if dados.get('veredito_cor') == "💎" else f"{currency}{dados.get('lucro_estimado')}",
                                "Strategy": dados.get('estrategia_base'),
                                "Market Link": dados.get('link_pesquisa', ''),
                                "Raw": dados
                            })
                            guardar_no_historico(dados, objetivo_final,st.session_state.email_logado)
                    
                    barra.progress((i+1)/total_items)
                
                if st.session_state.bulk_results:
                    st.success("✅ Processing completed (or interrupted by limits).")


    # MOSTRAR TABELA DE RESULTADOS
    if st.session_state.bulk_results:
        st.divider()
        st.write("### 📊 Report of the Bulk")
        df_res = pd.DataFrame(st.session_state.bulk_results)
        cols_para_tabela = [c for c in df_res.columns if c != "Raw"]
        st.dataframe(df_res[cols_para_tabela], use_container_width=True)
        
        try:
            excel_data = converter_para_excel(df_res)
            st.download_button("📥 Download Excel", excel_data, "relatorio_valurise.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.error(f"⚠️ Error generating Excel file: {e}")
        
        st.write("---")
        opcoes = [row["File"] for row in st.session_state.bulk_results]
        if opcoes:
            escolha = st.selectbox("Chat about which item?", opcoes, key="seletor_bulk")
            if escolha != st.session_state.current_bulk_item:
                st.session_state.current_bulk_item = escolha
                st.session_state.chat_history_bulk = [] 
                item_dados = next(r for r in st.session_state.bulk_results if r["File"] == escolha)
                img_selecionada = st.session_state.bulk_images.get(escolha)
                if img_selecionada:
                    st.session_state.chat_session_bulk = criar_chat_session(item_dados['Raw'])
                    nome_prod = item_dados['Item']
                    veredito = item_dados['Verdict']
                    boas_vindas = f"👋 I'm ready to chat about **{nome_prod}** {veredito}. \n\nBased on the references I found, do you want to know more about the pricing strategy or how to prepare the ad?"
                    st.session_state.chat_history_bulk.append({"role": "assistant", "content": boas_vindas})

            container_chat_bulk = st.container(height=400)
            with container_chat_bulk:
                for msg in st.session_state.chat_history_bulk:
                    with st.chat_message(msg["role"]): st.markdown(msg["content"])
            
            if prompt_bulk := st.chat_input("Ask about this item...", key="chat_in_bulk"):
                st.session_state.chat_history_bulk.append({"role": "user", "content": prompt_bulk})
                
                with container_chat_bulk:
                    with st.chat_message("user"): st.markdown(prompt_bulk)
                    with st.chat_message("assistant"):
                        try:
                            # Tentativa normal de envio
                            response = st.session_state.chat_session_bulk.send_message(prompt_bulk)
                            resp = response.text
                        except Exception as e:
                            # Se o cliente fechou ou deu 429, recuperamos a sessão aqui
                            if "closed" in str(e).lower() or "429" in str(e):
                                # Forçamos a recriação da sessão usando os dados que já temos
                                st.session_state.chat_session_bulk = criar_chat_session(item_dados['Raw'])
                                response = st.session_state.chat_session_bulk.send_message(prompt_bulk)
                                resp = response.text
                            else:
                                resp = f"Unexpected error: {e}"
                        
                        st.markdown(resp)
                        st.session_state.chat_history_bulk.append({"role": "assistant", "content": resp})
                        
                        # RECOMENDADO: st.rerun() ajuda a manter a interface sincronizada após a resposta
                        st.rerun()
    
    
# -----------------------------------------------------------------------------
# ABA 3: RADAR DE MERCADO (NOTÍCIAS)
# -----------------------------------------------------------------------------
with aba3:
    st.header("📈 Trends and Opportunities")
    st.write("Stay alert to price variations and weekly tips to maximize your profit.")   
    st.divider()

    try:
        # Busca as últimas 20 notícias, ordenadas da mais recente para a mais antiga
        # Como usas a service_role, isto lê direto sem problemas de permissão
        response = supabase.table("noticias").select("*").order("created_at", desc=True).limit(20).execute()
        lista_noticias = response.data

        if lista_noticias:
            for news in lista_noticias:
                # Cria um cartão visual para cada notícia
                with st.container(border=True):
                    col_texto, col_img = st.columns([3, 1])
                    
                    with col_texto:
                        # Título e Categoria
                        st.subheader(f"{news['titulo']}")
                        st.caption(f"📅 {news['created_at'][:10]} | 🏷️ {news.get('categoria', 'Geral')}")
                        
                        # Texto da notícia
                        st.markdown(news['conteudo'])
                    
                    with col_img:
                        # Se tiveres posto um link de imagem no Supabase, mostra aqui
                        if news.get('imagem_url'):
                            st.image(news['imagem_url'], use_container_width=True)
                        else:
                            # Ícone genérico se não houver imagem
                            st.markdown("# 🗞️")
        else:
            st.info("There are no news published this week yet. Come back soon!")

    except Exception as e:
        st.error("Error loading news.")
        # Se quiseres ver o erro real para debug, descomenta a linha abaixo:
        # st.write(e)

with aba_historico:
    st.subheader("📜 General Record of Analyses")
    
    # Procurar dados no Supabase
    res = supabase.table("historico_scans").select("*").eq("email", st.session_state.email_logado).order("created_at", desc=True).execute()
    
    if res.data:
        df_hist = pd.DataFrame(res.data)
        
        # Reordenar e renomear colunas para ficar "bonito"
        df_display = df_hist[[
            "cor", "produto", "preco_medio", "sugestao_venda", 
            "taxas_estimadas", "lucro_estimado", "objetivo", "estrategia", "link_mercado"
        ]]
        
        st.dataframe(
            df_display,
            column_config={
                "produto": "Item Name",
                "preco_medio": st.column_config.NumberColumn(f"Avg Price ({currency})", format=f"%.2f {currency}"),
                "sugestao_venda": st.column_config.NumberColumn(f"Target Price ({currency})", format=f"%.2f {currency}"),
                "taxas_estimadas": st.column_config.NumberColumn(f"Est. Fees ({currency})", format=f"%.2f {currency}"),
                "lucro_estimado": st.column_config.NumberColumn(f"Net Profit ({currency})", format=f"%.2f {currency}"),
                "link_mercado": st.column_config.LinkColumn("eBay Link"),
                "estrategia": "Strategy",
                "objetivo": "Goal",
                "cor": "Verdict"
            },
            use_container_width=True,
            hide_index=True
        )
        
        if st.button("🗑️ Clear All History"):     
            try:
                # O Supabase exige um filtro para o delete, por isso dizemos "onde ID não seja 0"
                supabase.table("historico_scans").delete().eq("email", st.session_state.email_logado).execute()
                
                st.success("🧹 History completely cleared!")
                time.sleep(1) # Pequena pausa para a mensagem de sucesso piscar no ecrã
                st.rerun()    # Atualiza a página para a tabela vazia aparecer
                
            except Exception as e:
                st.error(f"Error clearing history: {e}")
    else:
        st.info("There are no products in the history yet. Start analyzing to populate this table!")


mostrar_rodape_legal()