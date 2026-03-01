import requests
import base64

def get_ebay_token(app_id, cert_id):
    """Gera o token de acesso temporário (2h)"""
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    # O eBay exige as chaves em formato Base64 para segurança
    auth_str = f"{app_id}:{cert_id}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_auth}"
    }
    
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
    
    response = requests.post(url, headers=headers, data=data)
    return response.json().get("access_token")

def buscar_precos_ebay(token, produto, marketplace_id="EBAY_US"):
    """Procura itens vendidos para calcular a média real"""
    # Removemos o filtro USED do eBay. O nosso código Python (Guilhotina) é que faz o filtro das condições agora!
    url = f"https://api.ebay.com/buy/browse/v1/item_summary/search?q={produto}&limit=50"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": marketplace_id, # <--- AGORA É DINÂMICO (US, UK ou PT)
        "Accept-Language": "en-US",            
        "Content-Type": "application/json"
    }
    
    res = requests.get(url, headers=headers)
    return res.json()