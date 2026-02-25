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


st.set_page_config(page_title="Valurise", page_icon="💎", layout="wide")


# No início do teu webapp.py
if "client" not in st.session_state:
    st.session_state.client = genai.Client(
        vertexai=True, 
        project="gen-lang-client-0850234234", # Vê o ID no topo do Google Cloud Console
        location="us-central1"
    )
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
            st.error("Erro: Chaves do eBay não encontradas no cofre.")
            return None
    return st.session_state.ebay_token


# Lista de e-mails que têm créditos ilimitados
ADMINS = ["afonsocgomesduarte@gmail.com"] # SUBSTITUI pelo teu e-mail real

# Logo no início do código, antes de tudo:
st.set_page_config(
    page_title="Valurise App",
    page_icon="app_icon.png",  # O nome do teu ficheiro aqui
    layout="wide"
)

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
        st.sidebar.error(f"Erro: O ficheiro '{icon_path}' não foi encontrado no servidor.")

# Chama a função logo no início
set_app_icon("app_icon_512.png")

@st.dialog("🚀 Upgrade para Plano PRO")
def popup_upgrade():
    st.write("Esgotaste os teus créditos diários gratuitos!")
    st.write("Com o **Plano PRO**, tens:")
    st.write("- 💎 Análises Ilimitadas")
    st.write("- ⚡ Processamento Bulk mais rápido")
    st.write("- 📈 Relatórios detalhados em Excel")
    
    st.divider()
    st.link_button("💎 Obter Plano PRO - 9.99€/mês", "https://tuolinkdostripe.com", use_container_width=True)
    if st.button("Continuar no plano grátis"):
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
        st.error(f"Erro na Base de Dados: {e}")
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
        
        # 1. MUDAR EMOJIS PARA TEXTO (Para o Excel conseguir ler a regra)
        # Vamos usar palavras curtas que funcionam bem nas regras
        if 'Veredito' in df_export.columns:
            df_export['Veredito'] = df_export['Veredito'].astype(str)\
                .str.replace('🟢', 'SIM')\
                .str.replace('🟡', 'TALVEZ')\
                .str.replace('🔴', 'NAO')

        # 2. LIMPEZA DE NÚMEROS (Tirar o € e virar número real)
        colunas_dinheiro = ['Anunciar (€)', 'Valor Real', 'Input (€)', 'Lucro Est. (€)']
        for col in colunas_dinheiro:
            if col in df_export.columns:
                df_export[col] = df_export[col].astype(str).str.replace('€', '').str.replace(',', '.').str.strip()
                df_export[col] = pd.to_numeric(df_export[col], errors='coerce')
        
        # Escrever os dados
        sheet_name = 'Resultados'
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
    with st.expander("ℹ️ Aviso Legal e Isenção de Responsabilidade (Ler com atenção)"):
        st.markdown("""
        **1. Natureza Informativa:** A **Valurise** é uma ferramenta de auxílio à decisão. As estimativas de preço, margens de lucro e descrições são geradas por Inteligência Artificial e não constituem aconselhamento financeiro ou profissional.
        
        **2. Possibilidade de Erro:** Esta aplicação utiliza a tecnologia **Google Gemini**. Embora avançada, a IA pode ocasionalmente gerar informações imprecisas, desatualizadas ou incorretas.
        
        **3. Responsabilidade do Utilizador:** Tu és o único responsável por verificar a veracidade das informações e o estado real dos itens antes de qualquer transação. A Valurise não se responsabiliza por eventuais perdas financeiras.
        
        *Ao utilizar esta ferramenta, aceitas estes termos.*
        """)
        st.caption("Powered by Google Gemini AI • Valurise © 2026")

# ==========================================
# 🔒 LOGIN
# ==========================================
SENHA_SECRETA = "1234" 

if "logado" not in st.session_state:
    st.session_state["logado"] = False

if not st.session_state["logado"]:
    st.title("🔒 Área Restrita")
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        entrada = st.text_input("Password:", type="password")
        if st.button("Entrar", type="primary", use_container_width=True):
            if entrada == SENHA_SECRETA:
                st.session_state["logado"] = True
                st.rerun()
            else:
                st.error("Senha errada!")
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
def analisar_imagem_json(image, custo, objetivo, sabe_custo):
    try:
        # --- PASSO 1: IDENTIFICAÇÃO MULTI-FATOR (OCR + BARCODE + VISÃO) ---
        prompt_id = """
        Atua como um scanner de inventário. Analisa a imagem e extrai:
        1. OCR: Todo o texto da embalagem (Marca, Modelo, Tons, Edições).
        2. BARCODE: Se houver um código de barras, extrai os números.
        3. Se não houver barcode, identifica o modelo exato pelo design.
        
        Responde APENAS com o nome comercial completo + Código de Barras (se houver).
        """
        
        res_visao = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=[prompt_id, image]
        )
        nome_item = res_visao.text.strip()
        
        # --- PASSO 2: CONSULTA AO MOTOR EBAY ---
        token = garantir_token_ebay()
        dados_ebay = buscar_precos_ebay(token, nome_item)
        
        item_summaries = dados_ebay.get('itemSummaries', [])
        precos = []
        envios = [] # <--- NOVA LISTA PARA PORTES
        
        for item in item_summaries:
            try:
                valor = float(item.get('price', {}).get('value', 0))
                if valor > 3.0:
                    precos.append(valor)
                    # --- APANHAR OS PORTES REAIS DA API ---
                    try:
                        opcoes_envio = item.get('shippingOptions', [])
                        if opcoes_envio:
                            custo_envio = float(opcoes_envio[0].get('shippingCost', {}).get('value', 0))
                            envios.append(custo_envio)
                        else:
                            envios.append(0) # Portes grátis
                    except:
                        envios.append(4.50) # Valor de segurança médio
            except:
                continue

        # --- PASSO 3: LÓGICA DE NEGÓCIO COM TAXAS AUTOMÁTICAS ---
        if precos:
            precos.sort()
            if len(precos) > 4:
                precos = precos[1:-1]
            
            p_medio = sum(precos) / len(precos)
            p_venda = p_medio * 0.9
            
            # --- CÁLCULO DA IA PARA TAXAS ---
            portes_medios = sum(envios) / len(envios) if envios else 4.50
            comissao_plataforma = p_venda * 0.13 # 13% de taxa (padrão eBay/Marketplaces)
            taxas_estimadas = portes_medios + comissao_plataforma
            
            custo_real = 0 if not sabe_custo else custo
            lucro = p_venda - custo_real - taxas_estimadas
            
            link_mercado = f"https://www.ebay.com/sch/i.html?_nkw=\"{nome_item.replace(' ', '+')}\"&LH_Sold=1"
          
            cor = "🟢" if lucro > 10 else "🟡"
            if lucro < 0: cor = "🔴"
            
            # Gerador de Estratégia
            if not sabe_custo:
                estrategia = f"Mercado ativo ({len(precos)} vendas). Como não sabes o custo, qualquer compra que faças tem de deixar margem face aos {round(lucro, 2)}€ líquidos que sobram após taxas."
            else:
                if lucro < 0:
                    estrategia = "❌ Prejuízo à vista! O custo e as taxas engolem o valor de venda. Devias tentar encontrar muito mais barato."
                elif lucro < 5:
                    estrategia = "⚠️ Margem muito curta. Só vale a pena avançar se a venda for extremamente rápida."
                elif lucro >= 15 and len(precos) > 5:
                    estrategia = "🔥 Excelente negócio! Vais fazer bastante lucro e o mercado procura muito este item."
                else:
                    estrategia = "👍 Negócio sólido. Margem aceitável e mercado estável para venda."
            
            if p_venda > 200:
                estrategia += " ⚠️ VALOR ELEVADO: Este item parece ser de alta gama. Verifica sempre o link do eBay para confirmar edições especiais antes de investir."
            
        else:
            # --- FALLBACK: A IA VIRA AVALIADORA QUANDO O EBAY FALHA ---
            prompt_estimativa = f"""
            Não encontrei referências de vendas recentes no eBay para "{nome_item}". 
            Atua como um avaliador especialista de artigos de revenda. Olha bem para a imagem, avalia o tipo de produto, a marca, os materiais e o estado aparente.
            Dá-me um preço de venda realista em euros e uma breve justificação do porquê desse valor.
            Responde APENAS neste formato JSON exato:
            {{"preco": 25.0, "justificativa": "Apesar de não haver histórico, produtos similares desta marca/estilo costumam valer à volta de X devido a..."}}
            """
            
            try:
                # Chamamos a IA de novo para olhar para a foto com o novo objetivo
                res_estimativa = client.models.generate_content(
                    model='gemini-2.0-flash', 
                    contents=[prompt_estimativa, image]
                )
                
                # Limpar a resposta para garantir que o Python consegue ler o JSON
                texto_json = res_estimativa.text.replace("```json", "").replace("```", "").strip()
                dados_ia = json.loads(texto_json)
                
                # Extrair os valores que a IA imaginou
                p_venda = float(dados_ia.get("preco", 0))
                justificativa = dados_ia.get("justificativa", "Avaliação baseada no aspeto geral.")
                
                # Fazer a matemática das taxas com a estimativa da IA
                p_medio = p_venda 
                portes_medios = 4.50 # Como não há anúncios reais, usamos o porte médio padrão
                comissao_plataforma = p_venda * 0.13
                taxas_estimadas = portes_medios + comissao_plataforma
                
                custo_real = 0 if not sabe_custo else custo
                lucro = p_venda - custo_real - taxas_estimadas
                
                link_mercado = f"https://www.ebay.com/sch/i.html?_nkw={nome_item.replace(' ', '+')}"
                
                # Definimos o veredito com a nova estratégia
                cor = "🔮" # Emoji de bola de cristal para saberes que foi uma estimativa da IA e não do mercado
                if lucro < 0: cor = "🔴"
                elif lucro > 10: cor = "🟢"
                
                estrategia = f"Não encontrei este exato produto à venda, mas tendo em conta a minha análise visual: {justificativa}"
                
            except Exception as e:
                # Se a IA se engasgar a tentar adivinhar, não crashamos, devolvemos 0
                p_medio = p_venda = lucro = taxas_estimadas = 0
                link_mercado = f"https://www.ebay.com/sch/i.html?_nkw={nome_item.replace(' ', '+')}"
                cor = "⚪"
                estrategia = "Não encontrei preços no mercado e a IA não conseguiu estimar o valor com precisão por esta imagem."

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
            "produto": "Erro de Leitura",
            "estrategia_base": f"Erro técnico: {str(e)}",
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
    Atua como um Consultor Expert em Arbitragem e Revenda. 
    Acabaste de analisar o seguinte produto:
    
    - PRODUTO: {nome}
    - PREÇO MÉDIO NO EBAY EUROPA: {preco_medio}€
    - TUA SUGESTÃO DE VENDA: {sugestao}€
    - LUCRO ESTIMADO: {lucro}€
    - VEREDITO: {veredito}
    - LÓGICA APLICADA: {estrategia}
    - REFERÊNCIA: {ref}
    
    INSTRUÇÕES PARA A CONVERSA:
    1. Explica o teu plano de ação: por que sugeriste este preço? (Ex: estratégia de venda rápida vs lucro máximo).
    2. Se o veredito for 💎 (Raro), avisa o utilizador para não ter pressa e explicar que não há stock.
    3. Se o utilizador perguntar "Vale a pena?", usa os dados de lucro para justificar (ex: "Sim, porque a margem é superior a 30%").
    4. Mantém-te fiel aos dados da tabela, mas podes dar dicas de onde anunciar (Vinted, eBay, Wallapop).
    """
    
    
    # Criamos a sessão de chat garantindo que todas as partes são do tipo correto
    st.session_state.chat = client.chats.create(
        model='gemini-2.0-flash',
        history=[
            types.Content(role="user", parts=[types.Part.from_text(text=contexto_especialista)]),
            types.Content(role="model", parts=[types.Part.from_text(text="Entendido. Estou pronto para explicar a estratégia deste produto.")])
        ]
    )
    return st.session_state.chat
# ==========================================
# ⚙️ SIDEBAR
# ==========================================

with st.sidebar:
    st.header("⚙️ Painel")
    
    # 1. IDENTIFICAÇÃO E CRÉDITOS
    if st.session_state.email_logado:
        st.success(f"👤 {st.session_state.email_logado}")
        if st.session_state.email_logado in ADMINS:
            st.metric(label="Plano", value="👑 ADMIN / Ilimitado")
        else:
            saldo_atual = obter_saldo_visual(st.session_state.email_logado)
            st.metric(label="Créditos Disponíveis", value=f"{saldo_atual} / 1")
        # ------------------------------

        if st.button("🚪 Sair / Mudar Conta"):
            st.session_state.email_logado = None
            st.rerun()
    else:
        st.warning("Pendente login...")

    st.divider()

# ==========================================
# 📱 INTERFACE
# ==========================================
# No ecrã de Login
st.title("💎 Valurise (Versão Beta)")

if not st.session_state.email_logado:
    st.info("👋 Está convidado para testar o protótipo da Valurise.")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        email_input = st.text_input("Email (apenas para criar conta):")
        
        # Checkbox Simples e Direta
        termos = st.checkbox("Aceito participar no teste Beta e compreendo que a IA pode cometer erros.")

    with col2:
        st.write("")
        st.write("")
        if st.button("Entrar", type="primary"):
            if not termos:
                st.warning("Precisa de aceitar para testar.")
            elif "@" not in email_input:
                st.warning("Email inválido.")
            else:
                st.session_state.email_logado = email_input
                st.rerun()

    # Rodapé simples (sem moradas nem NIFs)
    with st.expander("ℹ️ Sobre este teste"):
        st.markdown("""
        **O que é isto?**
        Este é um protótipo criado por um programador independente para fins de teste.
        
        **Os teus dados:**
        O teu email serve apenas para entrares na conta. Não será vendido, partilhado nem usado para spam.
        
        **Isenção de Responsabilidade:**
        Os valores apresentados são estimativas de IA (Gemini). Verifica sempre os preços reais antes de vender.
        """)
    
    st.stop()

# Se chegou aqui, o email_logado já existe!
st.sidebar.write(f"👤 Utilizador: **{st.session_state.email_logado}**")

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
aba1, aba2, aba3, aba_historico = st.tabs(["🔍 Análise Individual", "📦 Bulk", "📰 Notícias","📜 Histórico"])


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
        st.write("### 1. Dados")
        objetivo_single = st.radio("Qual o objetivo?", ["Vender", "Comprar"], horizontal=True, key="obj_single_final")

        # Gestão de custos/estado
        if "temp_custo_ia" in st.session_state:
            st.session_state['single_cost'] = st.session_state.temp_custo_ia
            del st.session_state.temp_custo_ia

        foto_single = st.file_uploader("Carregar Foto", type=["jpg", "png"], key="single_up_final")
        
        # --- NOVA CHECKBOX DE CUSTO ---
        sabe_custo_single = not st.checkbox("Não sei o custo do item", key="check_custo_single")
        custo_single = st.number_input("Custo (€)", min_value=0.0, step=1.0, key="single_cost_final", disabled=not sabe_custo_single)

        # --- BOTÃO DE ANÁLISE COM TRAVAS DE SEGURANÇA ---
        if st.button("🚀 Analisar Item", type="primary"):
            if foto_single:
                # 🛡️ TRAVA 1: Limite Global Antibot (1400/dia)
                if trava_seguranca_global():
                    st.error("🛑 O sistema atingiu o limite de bónus diário (1400/1500). Tenta novamente amanhã!")
                    st.stop()

                # POR ISTO:
                foto_single.seek(0)
                img_bruta = PIL.Image.open(foto_single)
                img = comprimir_imagem(img_bruta)
                
                # 🛡️ TRAVA 2: Créditos do Utilizador (10 iniciais ou 1 diário)
                pode_avancar, saldo = gerir_creditos(st.session_state.email_logado)
                
                # --- CENÁRIO A: MODO SIMULAÇÃO (Para testes sem gastar API) ---
                if modo_simulacao:
                    with st.spinner("A simular análise..."):
                        # Registar no contador global para monitorizar tráfego mesmo em simulação
                        supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()
                        
                        dados = analisar_imagem_json(img, custo_single, objetivo_single, sabe_custo_single)
                        dados['id_unico'] = time.time()
                        st.session_state.single_result = dados

                # --- CENÁRIO B: MODO REAL (Gasta Google Grounding) ---
                else:
                    if pode_avancar:
                        with st.spinner(f"A analisar com IA Real... (Saldo: {saldo})"):
                            # 1. Registar pedido no contador global de 1400
                            supabase.table("historico_geral").insert({"data": datetime.now().date().isoformat()}).execute()
                            
    
                            dados = analisar_imagem_json(img, custo_single, objetivo_single, sabe_custo_single)
                            
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
                st.warning("Por favor, carrega uma foto primeiro.")

    # -------------------------------------------------------------------------
    # MOSTRAR RESULTADOS E CHAT (COLUNA DA DIREITA)
    # -------------------------------------------------------------------------
    if st.session_state.single_result:
        dados = st.session_state.single_result
        
        # Preparar Resumo para o histórico/chat (Atualizado para dados do eBay)
        texto_resumo = f"""**{dados['veredito_cor']} {dados['produto']}**

💰 **Preço Médio (Europa):** {dados.get('preco_medio', 0)}€
🚀 **Sugestão de Venda:** {dados.get('sugestao_venda', 0)}€
💸 **Taxas Estimadas:** {dados.get('taxas_estimadas', 0)}€
💶 **Lucro Líquido:** {dados.get('lucro_estimado', 0)}€

📊 **Análise:** {dados.get('estrategia_base', '')}
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
            primeira_resposta = "Olá! Analisei as referências do eBay para este item. Como posso ajudar no teu plano de venda?"
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

            if prompt := st.chat_input("Faz uma pergunta sobre este produto...", key="chat_input_unico"):
                st.session_state.chat_history_single.append({"role": "user", "content": prompt})
                with container_chat:
                    with st.chat_message("user"): 
                        st.markdown(prompt)
                    with st.chat_message("assistant"):
                        if modo_simulacao: 
                            resp = f"Simulação de resposta para: {prompt}"
                        else:
                            try: 
                                resp = st.session_state.chat_session_single.send_message(prompt).text
                            except: 
                                resp = "Desculpa, ocorreu um erro ao processar a tua pergunta."
                        st.markdown(resp)
                        st.session_state.chat_history_single.append({"role": "assistant", "content": resp})
# ABA 2: BULK (COM CONSUMO DE CRÉDITOS POR ITEM)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# ABA 2: BULK (COM CONSUMO DE CRÉDITOS E TRAVA GLOBAL POR ITEM)
# -----------------------------------------------------------------------------
with aba2:
    st.write("### 1. Configurar Lote")
    modo_geral = st.radio("O que é este lote?", ["🛒 Tudo para Comprar", "🏠 Tudo para Vender", "🔀 Misto (Decidir 1 a 1)"], horizontal=True)
    fotos_bulk = st.file_uploader("Carregar Fotos", type=["jpg", "png"], accept_multiple_files=True, key="bulk_up")
    
    if fotos_bulk:
        if "tabela_editavel" not in st.session_state or len(st.session_state.tabela_editavel) != len(fotos_bulk):
            dados_iniciais = []
            for f in fotos_bulk:
                # ADICIONAMOS AQUI O "NÃO SEI CUSTO"
                dados_iniciais.append({"Ficheiro": f.name, "Input (€)": 0.0, "Não sei custo": False, "Objetivo": "Vender"})
            st.session_state.tabela_editavel = pd.DataFrame(dados_iniciais)
        
        col_config = {}
        if "Misto" in modo_geral:
            col_config["Objetivo"] = st.column_config.SelectboxColumn("Ação", width="medium", options=["Vender", "Comprar"], required=True)
            colunas_visiveis = ["Ficheiro", "Input (€)", "Não sei custo", "Objetivo"]
        else:
            colunas_visiveis = ["Ficheiro", "Input (€)", "Não sei custo"]
        
        tabela_editada = st.data_editor(st.session_state.tabela_editavel[colunas_visiveis], num_rows="dynamic", use_container_width=True, key="editor_bulk", column_config=col_config)
        
        if "Misto" in modo_geral: st.session_state.tabela_editavel = tabela_editada
        else: st.session_state.tabela_editavel.update(tabela_editada)

        if st.button("🚀 Processar Lote"):
            if not st.session_state.get('email_logado'):
                st.warning("⚠️ Precisas de introduzir o teu e-mail primeiro.")
            else:
                st.session_state.bulk_results = []
                st.session_state.bulk_images = {}
                barra = st.progress(0)
                total_items = len(st.session_state.tabela_editavel)
                
                for i, row in st.session_state.tabela_editavel.iterrows():
                    # --- 🛡️ 1. TRAVAS DE SEGURANÇA ---
                    if trava_seguranca_global():
                        st.error(f"🛑 Limite global atingido. Parou no item {i+1}.")
                        break

                    pode_avancar, saldo = gerir_creditos(st.session_state.email_logado)
                    if not modo_simulacao and not pode_avancar:
                        st.warning(f"⚠️ Créditos esgotados no item {i+1}.")
                        popup_upgrade()
                        break

                    # --- 2. DEFINIÇÃO DE DADOS DO ITEM ---
                    nome_fich = row["Ficheiro"]
                    custo = row["Input (€)"]
                    sabe_custo_bulk = not row.get("Não sei custo", False)
                    
                    if "Comprar" in modo_geral: objetivo_final = "Comprar"
                    elif "Vender" in modo_geral: objetivo_final = "Vender"
                    else: objetivo_final = row["Objetivo"]

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
                            
                            dados = analisar_imagem_json(img, custo, objetivo_final, sabe_custo_bulk)
                            
                            # Detetar erro de Limite (429)
                            if "429" in str(dados) or "Resource exhausted" in str(dados):
                                tentativas += 1
                                st.warning(f"⏳ Google ocupado. Tentativa {tentativas}/3 para '{nome_fich}'. A aguardar...")
                                time.sleep(10 * tentativas) 
                            
                            # Detetar outros erros
                            elif "Erro" in dados.get("produto", ""):
                                st.error(f"❌ Erro no item {nome_fich}: {dados.get('estrategia_base')}")
                                break 
                            
                            else:
                                sucesso = True
                                if not modo_simulacao:
                                    gastar_credito(st.session_state.email_logado)

                        # --- 4. GUARDAR RESULTADOS (APENAS SE TEVE SUCESSO) ---
                        # --- 4. GUARDAR RESULTADOS (APENAS SE TEVE SUCESSO) ---
                        if sucesso:
                            st.session_state.bulk_results.append({
                                "Ficheiro": nome_fich,
                                "Input (€)": custo,
                                "Produto": dados.get('produto', 'Desconhecido'),
                                "Veredito": dados.get('veredito_cor', '🟡'),
                                "Preço Médio": f"{dados.get('preco_medio', 0)}€",
                                "Sugestão": f"{dados.get('sugestao_venda', 0)}€",
                                "Taxas Est.": f"{dados.get('taxas_estimadas', 0)}€",
                                "Lucro Líquido": "Pendente" if dados.get('veredito_cor') == "💎" else f"{dados.get('lucro_estimado')}€",
                                "Estratégia": dados.get('estrategia_base'),
                                "Validar Mercado": dados.get('link_pesquisa', ''),
                                "Raw": dados
                            })
                            guardar_no_historico(dados, objetivo_final,st.session_state.email_logado)
                    
                    barra.progress((i+1)/total_items)
                
                if st.session_state.bulk_results:
                    st.success("✅ Processamento concluído (ou interrompido por limites).")

    # MOSTRAR TABELA DE RESULTADOS
    # MOSTRAR TABELA DE RESULTADOS
    # MOSTRAR TABELA DE RESULTADOS
    if st.session_state.bulk_results:
        st.divider()
        st.write("### 📊 Relatório do Lote")
        df_res = pd.DataFrame(st.session_state.bulk_results)
        cols_para_tabela = [c for c in df_res.columns if c != "Raw"]
        st.dataframe(df_res[cols_para_tabela], use_container_width=True)
        
        try:
            excel_data = converter_para_excel(df_res)
            st.download_button("📥 Baixar Excel", excel_data, "relatorio_valurise.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except: pass
        
        st.write("---")
        opcoes = [row["Ficheiro"] for row in st.session_state.bulk_results]
        if opcoes:
            escolha = st.selectbox("Conversar sobre qual item?", opcoes, key="seletor_bulk")
            if escolha != st.session_state.current_bulk_item:
                st.session_state.current_bulk_item = escolha
                st.session_state.chat_history_bulk = [] 
                item_dados = next(r for r in st.session_state.bulk_results if r["Ficheiro"] == escolha)
                img_selecionada = st.session_state.bulk_images.get(escolha)
                if img_selecionada:
                    st.session_state.chat_session_bulk = criar_chat_session(item_dados['Raw'])
                    nome_prod = item_dados['Produto']
                    veredito = item_dados['Veredito']
                    boas_vindas = f"👋 Estou pronto para discutir o item **{nome_prod}** {veredito}. \n\nBaseado nas referências que encontrei, queres saber mais sobre a estratégia de preço ou como preparar o anúncio?"
                    st.session_state.chat_history_bulk.append({"role": "assistant", "content": boas_vindas})

            container_chat_bulk = st.container(height=400)
            with container_chat_bulk:
                for msg in st.session_state.chat_history_bulk:
                    with st.chat_message(msg["role"]): st.markdown(msg["content"])
            
            if prompt_bulk := st.chat_input("Perguntar sobre este item...", key="chat_in_bulk"):
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
                                resp = f"Erro inesperado: {e}"
                        
                        st.markdown(resp)
                        st.session_state.chat_history_bulk.append({"role": "assistant", "content": resp})
                        
                        # RECOMENDADO: st.rerun() ajuda a manter a interface sincronizada após a resposta
                        st.rerun()
    
    
# -----------------------------------------------------------------------------
# ABA 3: RADAR DE MERCADO (NOTÍCIAS)
# -----------------------------------------------------------------------------
with aba3:
    st.header("📈 Tendências e Oportunidades")
    st.write("Fica atento às variações de preços e dicas semanais para maximizares o teu lucro.")   
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
            st.info("Ainda não há notícias publicadas esta semana. Volta em breve!")

    except Exception as e:
        st.error("Erro ao carregar as notícias.")
        # Se quiseres ver o erro real para debug, descomenta a linha abaixo:
        # st.write(e)

with aba_historico:
    st.subheader("📜 Registo Geral de Análises")
    
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
                "link_mercado": st.column_config.LinkColumn("Link eBay"),
                "lucro_estimado": st.column_config.NumberColumn("Lucro (€)", format="%.2f €"),
                "cor": "Veredito"
            },
            use_container_width=True,
            hide_index=True
        )
        
        if st.button("🗑️ Limpar Todo o Histórico"):     
            try:
                # O Supabase exige um filtro para o delete, por isso dizemos "onde ID não seja 0"
                supabase.table("historico_scans").delete().eq("email", st.session_state.email_logado).execute()
                
                st.success("🧹 Histórico completamente limpo!")
                time.sleep(1) # Pequena pausa para a mensagem de sucesso piscar no ecrã
                st.rerun()    # Atualiza a página para a tabela vazia aparecer
                
            except Exception as e:
                st.error(f"Erro ao limpar histórico: {e}")
    else:
        st.info("Ainda não tens produtos no histórico. Começa a analisar para popular esta tabela!")

# ==========================================
# ⚖️ RODAPÉ LEGAL (Fica fora das abas)
# ==========================================
# Como usas st.stop() no login lá em cima, este código só corre
# se o utilizador já estiver logado, por isso é seguro pôr aqui.

mostrar_rodape_legal()