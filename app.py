import re
import statistics
from urllib.parse import quote_plus

import requests
import streamlit as st
from bs4 import BeautifulSoup


# ==============================
# CONFIGURAÇÃO DO APP
# ==============================

st.set_page_config(
    page_title="Wise Part Number Finder",
    page_icon="🔎",
    layout="centered",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

PALAVRAS_LADO_DIREITO = ["direito", "direita", "ld", "lado direito", "right"]
PALAVRAS_LADO_ESQUERDO = ["esquerdo", "esquerda", "le", "lado esquerdo", "left"]

MARCAS = [
    "Yamaha", "Honda", "Suzuki", "Kawasaki", "Dafra", "BMW", "Harley-Davidson",
    "Triumph", "KTM", "Royal Enfield", "Haojue", "Shineray", "Kasinski", "Sundown"
]

PALAVRAS_RUIDO_TITULO = [
    "novo", "usado", "promoção", "promocao", "frete", "grátis", "gratis",
    "envio", "imediato", "original", "genuíno", "genuino", "peça", "peca"
]


# ==============================
# FUNÇÕES DE LIMPEZA E EXTRAÇÃO
# ==============================

def limpar_part_number(codigo: str) -> str:
    return codigo.strip().upper().replace(" ", "")


def normalizar_texto(texto: str) -> str:
    texto = texto.replace("\n", " ").replace("\t", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def detectar_marca(texto: str) -> str:
    texto_lower = texto.lower()
    for marca in MARCAS:
        if marca.lower() in texto_lower:
            return marca
    return "Não identificado"


def detectar_lado(texto: str) -> str:
    texto_lower = texto.lower()

    for termo in PALAVRAS_LADO_DIREITO:
        if termo in texto_lower:
            return "Direito"

    for termo in PALAVRAS_LADO_ESQUERDO:
        if termo in texto_lower:
            return "Esquerdo"

    return "Sem lado identificado"


def detectar_anos(texto: str) -> str:
    anos = re.findall(r"\b(19\d{2}|20\d{2})\b", texto)
    anos = sorted(set(int(ano) for ano in anos if 1990 <= int(ano) <= 2035))

    if not anos:
        return "Não identificado"

    if len(anos) == 1:
        return str(anos[0])

    return f"{anos[0]} a {anos[-1]}"


def extrair_modelos(textos: list[str], marca: str) -> str:
    texto_total = " ".join(textos)

    padroes_modelo = [
        r"\bMT[- ]?03\b",
        r"\bMT[- ]?07\b",
        r"\bMT[- ]?09\b",
        r"\bYZF[- ]?R3\b",
        r"\bR3\b",
        r"\bFZ25\b",
        r"\bFazer\s?250\b",
        r"\bFazer\s?150\b",
        r"\bFactor\s?150\b",
        r"\bNMAX\s?160\b",
        r"\bXJ6\b",
        r"\bCB\s?300\b",
        r"\bCB\s?500F\b",
        r"\bCB\s?500X\b",
        r"\bCG\s?160\b",
        r"\bCG\s?150\b",
        r"\bBiz\s?125\b",
        r"\bLead\s?110\b",
        r"\bElite\s?125\b",
        r"\bApache\s?150\b",
    ]

    encontrados = []
    for padrao in padroes_modelo:
        matches = re.findall(padrao, texto_total, flags=re.IGNORECASE)
        encontrados.extend(matches)

    encontrados = list(dict.fromkeys([m.upper().replace("  ", " ") for m in encontrados]))

    if encontrados:
        return " / ".join(encontrados[:4])

    return "Não identificado"


def inferir_nome_peca(textos: list[str]) -> str:
    texto = " ".join(textos).lower()

    mapa_pecas = {
        "carenagem": ["carenagem", "aba", "lateral", "capa lateral"],
        "paralama": ["paralama", "para-lama"],
        "farol": ["farol", "bloco óptico", "bloco optico"],
        "lanterna": ["lanterna", "sinaleira traseira"],
        "pisca": ["pisca", "seta", "sinalizador"],
        "retrovisor": ["retrovisor", "espelho"],
        "manete": ["manete", "alavanca"],
        "manicoto": ["manicoto", "suporte manete"],
        "pedal de freio": ["pedal de freio"],
        "pedal de câmbio": ["pedal de cambio", "pedal de câmbio"],
        "tampa lateral": ["tampa lateral"],
        "protetor de escapamento": ["protetor escapamento", "protetor de escape", "capa escapamento"],
        "painel": ["painel", "velocímetro", "velocimetro"],
        "tanque": ["tanque"],
        "rabeta": ["rabeta"],
        "bengala": ["bengala", "cilindro interno"],
    }

    for nome, termos in mapa_pecas.items():
        if any(termo in texto for termo in termos):
            return nome.title()

    return "Peça"


def limitar_titulo_60(titulo: str) -> str:
    titulo = normalizar_texto(titulo)
    if len(titulo) <= 60:
        return titulo

    substituicoes = {
        "Esquerda": "Esq",
        "Esquerdo": "Esq",
        "Direita": "Dir",
        "Direito": "Dir",
        "Original": "Orig",
        "Yamaha": "Yam",
        "Honda": "Honda",
    }

    for antigo, novo in substituicoes.items():
        titulo = titulo.replace(antigo, novo)
        if len(titulo) <= 60:
            return titulo

    return titulo[:60].rstrip()


# ==============================
# BUSCA WEB GERAL
# ==============================

def buscar_web_duckduckgo(part_number: str, limite: int = 8) -> list[dict]:
    """
    Busca resultados públicos usando DuckDuckGo HTML.
    Observação: pode falhar se o buscador bloquear requisições automatizadas.
    """
    query = quote_plus(f'"{part_number}" motorcycle part OEM')
    url = f"https://duckduckgo.com/html/?q={query}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    resultados = []

    for item in soup.select(".result")[:limite]:
        titulo_tag = item.select_one(".result__title")
        link_tag = item.select_one(".result__a")
        snippet_tag = item.select_one(".result__snippet")

        titulo = normalizar_texto(titulo_tag.get_text(" ")) if titulo_tag else ""
        link = link_tag.get("href") if link_tag else ""
        snippet = normalizar_texto(snippet_tag.get_text(" ")) if snippet_tag else ""

        if titulo or snippet:
            resultados.append({
                "titulo": titulo,
                "link": link,
                "snippet": snippet,
            })

    return resultados


# ==============================
# BUSCA MERCADO LIVRE
# ==============================

def buscar_mercado_livre(termo: str, limite: int = 20) -> list[dict]:
    url = f"https://api.mercadolibre.com/sites/MLB/search?q={quote_plus(termo)}&limit={limite}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        dados = response.json()
    except Exception:
        return []

    resultados = []
    for item in dados.get("results", []):
        titulo = item.get("title", "")
        preco = item.get("price")
        link = item.get("permalink", "")
        condicao = item.get("condition", "")

        if titulo and preco:
            resultados.append({
                "titulo": titulo,
                "preco": float(preco),
                "link": link,
                "condicao": condicao,
            })

    return resultados


def filtrar_anuncios_relevantes(anuncios: list[dict], part_number: str, peca: str, marca: str, modelo: str) -> list[dict]:
    relevantes = []
    pn_limpo = part_number.lower().replace("-", "")
    termos_obrigatorios = []

    if marca != "Não identificado":
        termos_obrigatorios.append(marca.lower())

    if peca != "Peça":
        termos_obrigatorios.append(peca.lower())

    for anuncio in anuncios:
        titulo = anuncio["titulo"].lower()
        titulo_limpo = titulo.replace("-", "")

        pontos = 0

        if pn_limpo in titulo_limpo:
            pontos += 4

        for termo in termos_obrigatorios:
            if termo in titulo:
                pontos += 2

        if modelo != "Não identificado":
            for parte_modelo in modelo.lower().split("/"):
                if parte_modelo.strip() and parte_modelo.strip() in titulo:
                    pontos += 2

        if pontos >= 2:
            relevantes.append(anuncio | {"score": pontos})

    relevantes.sort(key=lambda x: x["score"], reverse=True)
    return relevantes


def calcular_media_precos(anuncios: list[dict]) -> dict:
    precos = [a["preco"] for a in anuncios if a.get("preco")]

    if not precos:
        return {
            "media": None,
            "mediana": None,
            "minimo": None,
            "maximo": None,
            "quantidade": 0,
        }

    # Remove extremos muito fora da curva quando houver volume
    precos_ordenados = sorted(precos)
    if len(precos_ordenados) >= 6:
        precos_filtrados = precos_ordenados[1:-1]
    else:
        precos_filtrados = precos_ordenados

    return {
        "media": round(statistics.mean(precos_filtrados), 2),
        "mediana": round(statistics.median(precos_filtrados), 2),
        "minimo": round(min(precos_filtrados), 2),
        "maximo": round(max(precos_filtrados), 2),
        "quantidade": len(precos_filtrados),
    }


# ==============================
# GERAÇÃO DO ANÚNCIO
# ==============================

def gerar_titulo(peca: str, lado: str, marca: str, modelo: str) -> str:
    partes = []

    partes.append(peca if peca != "Peça" else "Peça")

    if lado in ["Direito", "Esquerdo"]:
        partes.append(lado)

    if marca != "Não identificado":
        partes.append(marca)

    if modelo != "Não identificado":
        modelo_principal = modelo.split("/")[0].strip()
        partes.append(modelo_principal)

    partes.append("Original")

    return limitar_titulo_60(" ".join(partes))


def gerar_descricao(peca: str, marca: str, modelo: str, anos: str, lado: str, part_number: str) -> str:
    nome_peca = peca if peca != "Peça" else "Peça"
    marca_txt = marca if marca != "Não identificado" else ""
    modelo_txt = modelo if modelo != "Não identificado" else "modelo compatível"
    lado_txt = f" {lado}" if lado in ["Direito", "Esquerdo"] else ""
    anos_txt = f" ({anos})" if anos != "Não identificado" else ""

    return f"""Esse anúncio contém: 01 {nome_peca}{lado_txt} {marca_txt} {modelo_txt}{anos_txt} - ORIGINAL

Código da peça / Part Number: {part_number}

Produto usado em condições de uso. Favor verificar todas as fotos do anúncio antes da compra, pois elas fazem parte da descrição do produto.

Compatibilidade identificada:
Marca: {marca}
Modelo: {modelo}
Ano: {anos}
Lado: {lado}

Peça original retirada de veículo adquirido em leilão/sucata legalizada, com procedência e nota fiscal.

Antes da compra, confira o código da peça e compare com a peça da sua moto para garantir compatibilidade."""


def gerar_palavras_chave(peca: str, marca: str, modelo: str, anos: str, lado: str, part_number: str) -> str:
    termos = [part_number, peca, marca, modelo, anos, lado, "original", "peça usada", "moto"]
    termos = [t for t in termos if t and t not in ["Não identificado", "Sem lado identificado"]]
    return ", ".join(dict.fromkeys(termos))


# ==============================
# INTERFACE STREAMLIT
# ==============================

st.title("🔎 Wise Part Number Finder")
st.caption("Digite o código da peça e o app busca informações, preço médio e gera anúncio para Mercado Livre.")

part_number_input = st.text_input("Digite o Part Number", placeholder="Ex: BK6-F117W-00")

if part_number_input:
    part_number = limpar_part_number(part_number_input)

    with st.spinner("Buscando informações da peça na web e no Mercado Livre..."):
        resultados_web = buscar_web_duckduckgo(part_number)

        textos_web = []
        for r in resultados_web:
            textos_web.append(r.get("titulo", ""))
            textos_web.append(r.get("snippet", ""))

        texto_total_web = " ".join(textos_web)

        marca = detectar_marca(texto_total_web)
        lado = detectar_lado(texto_total_web)
        anos = detectar_anos(texto_total_web)
        modelo = extrair_modelos(textos_web, marca)
        peca = inferir_nome_peca(textos_web)

        termo_ml_1 = part_number
        anuncios_pn = buscar_mercado_livre(termo_ml_1, limite=20)

        termo_ml_2 = " ".join([x for x in [peca, marca, modelo.split("/")[0].strip() if modelo != "Não identificado" else ""] if x and x != "Não identificado"])
        anuncios_nome = buscar_mercado_livre(termo_ml_2, limite=20) if termo_ml_2 else []

        anuncios_total = anuncios_pn + anuncios_nome
        anuncios_relevantes = filtrar_anuncios_relevantes(anuncios_total, part_number, peca, marca, modelo)

        # Caso o filtro fique rígido demais, usa os anúncios pelo part number
        anuncios_para_preco = anuncios_relevantes if anuncios_relevantes else anuncios_pn
        preco_info = calcular_media_precos(anuncios_para_preco)

        titulo_ml = gerar_titulo(peca, lado, marca, modelo)
        descricao = gerar_descricao(peca, marca, modelo, anos, lado, part_number)
        palavras_chave = gerar_palavras_chave(peca, marca, modelo, anos, lado, part_number)

    st.subheader("Informações identificadas")

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Código:** {part_number}")
        st.write(f"**Peça:** {peca}")
        st.write(f"**Marca:** {marca}")
    with col2:
        st.write(f"**Modelo:** {modelo}")
        st.write(f"**Ano:** {anos}")
        st.write(f"**Lado:** {lado}")

    st.subheader("Média de valores Mercado Livre")

    if preco_info["media"]:
        st.write(f"**Preço médio:** R$ {preco_info['media']:.2f}".replace(".", ","))
        st.write(f"**Mediana:** R$ {preco_info['mediana']:.2f}".replace(".", ","))
        st.write(f"**Faixa analisada:** R$ {preco_info['minimo']:.2f} a R$ {preco_info['maximo']:.2f}".replace(".", ","))
        st.write(f"**Anúncios considerados:** {preco_info['quantidade']}")
    else:
        st.warning("Não foi possível calcular uma média confiável com os anúncios encontrados.")

    st.subheader("Título Mercado Livre")
    st.code(titulo_ml)
    st.caption(f"Caracteres: {len(titulo_ml)}/60")

    st.subheader("Descrição")
    st.text_area("Descrição gerada", descricao, height=300)

    st.subheader("Palavras-chave")
    st.text_area("Palavras-chave", palavras_chave, height=100)

    st.subheader("Fontes encontradas na web")
    if resultados_web:
        for r in resultados_web[:5]:
            st.markdown(f"- [{r['titulo']}]({r['link']})")
            if r.get("snippet"):
                st.caption(r["snippet"])
    else:
        st.info("Nenhuma fonte web encontrada pelo buscador público. Tente o código com hífen ou sem hífen.")

    st.subheader("Anúncios usados como referência")
    if anuncios_para_preco:
        for a in anuncios_para_preco[:8]:
            preco_fmt = f"R$ {a['preco']:.2f}".replace(".", ",")
            st.markdown(f"- [{a['titulo']}]({a['link']}) — **{preco_fmt}**")
    else:
        st.info("Nenhum anúncio encontrado no Mercado Livre para esse código/peça.")


st.divider()
st.caption("Observação: o app cruza fontes públicas e anúncios ativos. Sempre confira o código OEM e as fotos antes de publicar.")

