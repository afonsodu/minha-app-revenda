import feedparser
import streamlit as st
import re # Usado para limpar as tags HTML chatas como o <p>

def buscar_noticias_automaticas():
    # Podes trocar este link se preferires outro site no futuro
    url_feed = "https://sneakerbardetroit.com/feed/"
    
    try:
        feed = feedparser.parse(url_feed)
        noticias = []
        
        # Traz 5 opções para teres por onde escolher
        for entry in feed.entries[:5]: 
            img_url = ""
            if 'media_content' in entry and len(entry.media_content) > 0:
                img_url = entry.media_content[0].get('url', '')
            
            # 1. Limpa o lixo HTML (tira os <p> e </p>)
            resumo_limpo = re.sub(r'<[^>]+>', '', entry.description)
            link_original = entry.link
            
            # 2. Formata o que vai aparecer aos TEUS utilizadores
            conteudo_final = f"{resumo_limpo[:300]}...\n\n🔗 **[Ler artigo original]({link_original})**"
            
            noticias.append({
                "titulo": entry.title,
                "conteudo": conteudo_final,
                "categoria": "Market Trends",
                "imagem_url": img_url,
                "link_original": link_original # Guardamos o link só para ti
            })
        return noticias
    except Exception as e:
        st.error(f"Erro ao ler feed: {e}")
        return []

def mostrar_painel_noticias(supabase_client):
    st.subheader("🕵️‍♂️ Radar Automático (Admin)")
    
    # Guarda as notícias na "memória" para não desaparecerem ao clicar nos botões
    if 'noticias_admin' not in st.session_state:
        st.session_state.noticias_admin = []
    
    # O botão de procurar
    if st.button("Procurar Notícias de Hoje", type="primary"):
        st.session_state.noticias_admin = buscar_noticias_automaticas()
        if not st.session_state.noticias_admin:
            st.warning("Não foi possível carregar as notícias hoje.")

    # Mostrar a lista de notícias guardadas na memória
    for i, noti in enumerate(st.session_state.noticias_admin):
        with st.container(border=True):
            st.markdown(f"### {noti['titulo']}")
            
            if noti['imagem_url']:
                st.image(noti['imagem_url'], width=200)
            
            # --- ISTO É SÓ PARA O ADMIN (TU) ---
            st.markdown(f"🔍 **[Clica aqui para ler a notícia inteira no site original]({noti['link_original']})**")
            
            with st.expander("👁️ Ver preview do que os utilizadores vão ler"):
                st.write(noti['conteudo'])
            
            # --- O BOTÃO DE PUBLICAR ---
            if st.button(f"✅ Publicar Oficialmente", key=f"pub_{i}"):
                try:
                    supabase_client.table('noticias').insert({
                        "titulo": noti['titulo'],
                        "conteudo": noti['conteudo'],
                        "categoria": noti['categoria'],
                        "imagem_url": noti['imagem_url']
                    }).execute()
                    
                    st.success("✅ Publicado com sucesso! Já podes ver na Aba 3 (News).")
                except Exception as e:
                    st.error(f"Erro ao inserir na base de dados: {e}")