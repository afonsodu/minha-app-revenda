import feedparser
import streamlit as st

def buscar_noticias_automaticas():
    # Podes mudar este link para o blog/site de resell que preferires
    url_feed = "https://sneakerbardetroit.com/feed/"
    
    try:
        feed = feedparser.parse(url_feed)
        noticias = []
        # Vai buscar apenas as 3 notícias mais recentes
        for entry in feed.entries[:3]:
            noticias.append({
                "titulo": entry.title,
                "link": entry.link,
                "resumo": entry.description[:150] + "..." # Corta o texto
            })
        return noticias
    except Exception as e:
        st.error(f"Erro ao carregar o feed: {e}")
        return []

def mostrar_painel_noticias(supabase_client):
    """
    Esta função cria a interface visual.
    Recebe o teu cliente do Supabase para poder guardar as notícias.
    """
    st.subheader("🕵️‍♂️ Radar de Notícias Automático")
    
    if st.button("Procurar Notícias de Hoje"):
        noticias_frescas = buscar_noticias_automaticas()
        
        if not noticias_frescas:
            st.warning("Não foi possível encontrar notícias hoje.")
            return

        for i, noticia in enumerate(noticias_frescas):
            st.markdown(f"**{noticia['titulo']}**")
            st.caption(noticia['resumo'])
            
            # O botão que liga ao TEU Supabase
            if st.button(f"✅ Publicar no Supabase", key=f"pub_{i}"):
                try:
                    # ATENÇÃO: Confirma se o nome da tabela é 'noticias'
                    # e se as colunas são 'titulo' e 'link'
                    supabase_client.table('noticias').insert({
                        "titulo": noticia['titulo'],
                        "link": noticia['link']
                    }).execute()
                    
                    st.success("Notícia publicada na plataforma com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao guardar no Supabase: {e}")
            st.markdown("---")