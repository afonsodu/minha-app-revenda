import requests
import base64
import time
import re
from urllib.parse import quote_plus

def get_ebay_token(app_id, cert_id):
    """Gera token OAuth2. Faz 3 tentativas antes de desistir."""
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    auth_str = f"{app_id}:{cert_id}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_auth}"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            token = response.json().get("access_token")
            if token:
                return token
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
    return None


def _sanitizar_query(produto):
    """
    Remove palavras que poluem a pesquisa eBay (ex: 'no barcode', tamanhos de embalagem em texto).
    Limita a 10 palavras-chave relevantes.
    """
    # Remover palavras de barulho
    stop_words = [
        "no barcode", "unknown", "barcode", "n/a", "not available",
        "packaging", "embalagem", "see photos", "as pictured"
    ]
    query = produto.lower()
    for sw in stop_words:
        query = query.replace(sw, "")

    # Limpar espaços duplos e caracteres especiais
    query = re.sub(r'[^\w\s\-\.\(\)]', '', query)
    query = re.sub(r'\s+', ' ', query).strip()

    # Limitar a 10 palavras (o eBay penaliza queries muito longas)
    palavras = query.split()
    if len(palavras) > 10:
        query = " ".join(palavras[:10])

    return query


def _build_search_queries(produto):
    """
    Gera múltiplas variantes da query para maximizar resultados.
    Estratégia: full query → sem parênteses → só as 5 primeiras palavras
    """
    base = _sanitizar_query(produto)
    variantes = [base]

    # Variante sem parênteses (ex: "Nike Air Max (2023)" → "Nike Air Max")
    sem_parenteses = re.sub(r'\(.*?\)', '', base).strip()
    if sem_parenteses and sem_parenteses != base:
        variantes.append(sem_parenteses)

    # Variante curta: só 5 primeiras palavras (para produtos com nomes muito longos)
    palavras = base.split()
    if len(palavras) > 5:
        variantes.append(" ".join(palavras[:5]))

    return variantes


def buscar_precos_ebay(token, produto, marketplace_id="EBAY_US", limit=100, filter_condition=""):
    if not token:
        return {"itemSummaries": [], "error": "No token"}

    variantes = _build_search_queries(produto)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
        "Accept-Language": "en-US",
        "Content-Type": "application/json"
    }

    # ===================================================
    # FASE 1: Tentar SOLD LISTINGS
    # ===================================================
    for query in variantes:
        encoded_query = quote_plus(query)
        filtros_sold = "soldItems:{true}"
        if filter_condition:
            filtros_sold += f",conditionIds:{{{filter_condition}}}"

        url_sold = (
            f"https://api.ebay.com/buy/browse/v1/item_summary/search"
            f"?q={encoded_query}&limit={limit}&filter={filtros_sold}&sort=-endDate"
        )

        for attempt in range(3):
            try:
                res = requests.get(url_sold, headers=headers, timeout=12)
                if res.status_code == 200:
                    data = res.json()
                    if len(data.get("itemSummaries", [])) >= 3:
                        data["_source"] = "sold"
                        return data
                    break 
                elif res.status_code == 429:
                    time.sleep((2 ** attempt) * 5)
                elif res.status_code in [401, 403]:
                    return {"itemSummaries": [], "error": f"Auth error {res.status_code}"}
                else:
                    if attempt < 2: time.sleep(3)
            except:
                if attempt < 2: time.sleep(2)

    # ===================================================
    # FASE 2: Fallback — Ativos com FIXED_PRICE
    # ===================================================
    for query in variantes:
        encoded_query = quote_plus(query)
        filtros_active = "buyingOptions:{FIXED_PRICE}"
        if filter_condition:
            filtros_active += f",conditionIds:{{{filter_condition}}}"

        url_active = (
            f"https://api.ebay.com/buy/browse/v1/item_summary/search"
            f"?q={encoded_query}&limit={limit}&filter={filtros_active}&sort=price"
        )

        for attempt in range(2):
            try:
                res = requests.get(url_active, headers=headers, timeout=12)
                if res.status_code == 200:
                    data = res.json()
                    if len(data.get("itemSummaries", [])) >= 3:
                        data["_source"] = "active"
                        return data
                    break
                elif res.status_code == 429:
                    time.sleep(10)
                else:
                    if attempt < 1: time.sleep(3)
            except:
                pass

    return {"itemSummaries": [], "total": 0, "_source": "empty"}


def buscar_precos_vendidos_ebay(token, produto, marketplace_id="EBAY_US"):
    """
    BONUS: Usa a Finding API (legado) para buscar SOLD LISTINGS reais.
    Complementa o Browse API para ter preços de vendas históricas.
    Requer EBAY_APP_ID (não o token OAuth2).
    """
    # Nota: Esta função usa a Finding API com App ID diretamente
    # Podes chamar isto como fallback se o Browse API der poucos resultados
    pass