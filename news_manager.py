import feedparser
import streamlit as st

def buscar_noticias_automaticas():
    # Fonte de exemplo: Sneaker Bar Detroit (podes trocar)
    url_feed = "https://sneakerbardetroit.com/feed/"
    
    try:
        feed = feedparser.parse(url_feed)
        noticias = []
        
        for entry in feed.entries[:3]:
            # Tentar extrair a imagem se vier no Feed RSS
            img_url = ""
            if 'media_content' in entry and len(entry.media_content) > 0:
                img_url = entry.media_content[0].get('url', '')
            
            # Limpar a descrição para não vir com lixo de HTML e adicionar o link no fim
            resumo_limpo = entry.description[:250].replace("<p>", "").replace("</p>", "")
            conteudo_final = f"{resumo_limpo}...\n\n🔗 **[Ler artigo original]({entry.link})**"
            
            noticias.append({
                "titulo": entry.title,
                "conteudo": conteudo_final,
                "categoria": "Market Trends", # Podes mudar para "Sneakers", etc.
                "imagem_url": img_url
            })
        return noticias
    except Exception as e:
        st.error(f"Erro ao ler feed: {e}")
        return []

def mostrar_painel_noticias(supabase_client):
    st.subheader("🕵️‍♂️ Radar Automático (Admin)")
    
    if st.button("Procurar Notícias de Hoje", type="primary"):
        noticias_frescas = buscar_noticias_automaticas()
        
        if not noticias_frescas:
            st.warning("Não foi possível carregar as notícias hoje.")
            return

        for i, noti in enumerate(noticias_frescas):
            st.markdown(f"### {noti['titulo']}")
            st.caption(noti['conteudo'])
            if noti['imagem_url']:
                st.image(noti['imagem_url'], width=150)
            
            # O momento mágico: Enviar para as colunas exatas do teu Supabase
            if st.button(f"✅ Publicar Oficialmente", key=f"pub_{i}"):
                try:
                    supabase_client.table('noticias').insert({
                        "titulo": noti['titulo'],
                        "conteudo": noti['conteudo'],
                        "categoria": noti['categoria'],
                        "imagem_url": noti['imagem_url']
                    }).execute()
                    
                    st.success("Publicado com sucesso! Já está visível para os utilizadores.")
                except Exception as e:
                    st.error(f"Erro ao inserir na base de dados: {e}")
            st.markdown("---")