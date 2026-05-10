import re
import statistics
from urllib.parse import quote_plus

import requests
import streamlit as st
from bs4 import BeautifulSoup


# =====================================================
# WISE PART NUMBER FINDER - V2
# Busca por Part Number com prioridade em fontes OEM/catálogos
# e usa Mercado Livre apenas como referência de preço/título.
# =====================================================

st.set_page_config(
    page_title="Wise Part Number Finder V2",
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

MARCAS = [
    "Yamaha", "Honda", "Suzuki", "Kawasaki", "Dafra", "BMW",
    "Harley-Davidson", "Triumph", "KTM", "Royal Enfield",
    "Haojue", "Shineray", "Kasinski", "Sundown"
]

FONTES_ALTA_CONFIANCA = [
    "parts catalog", "oem", "fiche", "microfiche", "parts list",
    "partzilla", "cmsnl", "bike-parts", "yamaha parts", "honda parts",
    "suzuki parts", "kawasaki parts", "genuine parts", "genuine motorcycle parts",
    "catálogo", "catalogo", "catálogo de peças", "catalogo de pecas"
]

MARKETPLACES = [
    "mercadolivre", "mercado livre", "shopee", "olx", "amazon", "ebay", "aliexpress"
]

PALAVRAS_LADO_DIREITO = [
    "direito", "direita", "lado direito", "right", "right hand", "r/h", "rh"
]

PALAVRAS_LADO_ESQUERDO = [
    "esquerdo", "esquerda", "lado esquerdo", "left", "left hand", "l/h", "lh"
]


# =====================================================
# LIMPEZA E NORMALIZAÇÃO
# =====================================================

def limpar_part_number(codigo: str) -> str:
    return codigo.strip().upper().replace(" ", "")


def normalizar_texto(texto: str) -> str:
    texto = texto or ""
    texto = texto.replace("\n", " ").replace("\t", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def texto_total_resultados(resultados: list[dict]) -> str:
    partes = []
    for r in resultados:
        partes.append(r.get("titulo", ""))
        partes.append(r.get("snippet", ""))
        partes.append(r.get("link", ""))
    return " ".join(partes)


# =====================================================
# IDENTIFICAÇÃO DA PEÇA
# =====================================================

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


def extrair_modelos(texto: str) -> str:
    padroes_modelo = [
        r"\bMT[- ]?03\b", r"\bMT[- ]?07\b", r"\bMT[- ]?09\b",
        r"\bYZF[- ]?R3\b", r"\bYZF[- ]?R1\b", r"\bR3\b",
        r"\bFZ25\b", r"\bFazer\s?250\b", r"\bFazer\s?150\b",
        r"\bFactor\s?150\b", r"\bNMAX\s?160\b", r"\bXJ6\b",
        r"\bXTZ\s?250\b", r"\bLander\s?250\b",
        r"\bCB\s?300\b", r"\bCB\s?500F\b", r"\bCB\s?500X\b",
        r"\bCBR\s?500R\b", r"\bCG\s?160\b", r"\bCG\s?150\b",
        r"\bBiz\s?125\b", r"\bBiz\s?110\b", r"\bLead\s?110\b",
        r"\bElite\s?125\b", r"\bPCX\s?150\b", r"\bPCX\s?160\b",
        r"\bXRE\s?300\b", r"\bBros\s?160\b", r"\bNXR\s?160\b",
        r"\bApache\s?150\b",
    ]

    encontrados = []
    for padrao in padroes_modelo:
        matches = re.findall(padrao, texto, flags=re.IGNORECASE)
        encontrados.extend(matches)

    modelos = []
    for item in encontrados:
        item = normalizar_texto(item.upper().replace("- ", "-").replace("  ", " "))
        if item not in modelos:
            modelos.append(item)

    return " / ".join(modelos[:4]) if modelos else "Não identificado"


def inferir_nome_peca(texto: str) -> str:
    texto_lower = texto.lower()

    mapa_pecas = {
        "Carenagem": ["carenagem", "cover", "cowling", "fairing", "aba", "capa lateral"],
        "Paralama": ["paralama", "para-lama", "fender", "mudguard"],
        "Farol": ["farol", "headlight", "bloco óptico", "bloco optico"],
        "Lanterna": ["lanterna", "tail light", "taillight"],
        "Pisca": ["pisca", "seta", "turn signal", "sinalizador", "indicator"],
        "Retrovisor": ["retrovisor", "mirror", "espelho"],
        "Manete": ["manete", "lever", "alavanca"],
        "Manicoto": ["manicoto", "holder", "suporte manete"],
        "Pedal De Freio": ["pedal de freio", "brake pedal"],
        "Pedal De Câmbio": ["pedal de cambio", "pedal de câmbio", "shift pedal", "gear pedal"],
        "Tampa Lateral": ["tampa lateral", "side cover"],
        "Protetor De Escapamento": ["protetor escapamento", "protetor de escape", "heat guard", "muffler cover"],
        "Painel": ["painel", "speedometer", "velocímetro", "velocimetro", "meter assy"],
        "Tanque": ["tanque", "fuel tank"],
        "Rabeta": ["rabeta", "rear cowl", "rear cover"],
        "Bengala": ["bengala", "front fork", "fork pipe"],
        "Suporte": ["suporte", "bracket", "stay"],
        "Tampa": ["tampa", "cap", "cover"],
    }

    for nome, termos in mapa_pecas.items():
        if any(termo in texto_lower for termo in termos):
            return nome

    return "Peça"


# =====================================================
# CONFIANÇA DAS FONTES
# =====================================================

def calcular_confianca_fonte(titulo: str, snippet: str, link: str) -> str:
    texto = f"{titulo} {snippet} {link}".lower()

    if any(fonte in texto for fonte in FONTES_ALTA_CONFIANCA):
        return "Alta"

    if any(market in texto for market in MARKETPLACES):
        return "Baixa"

    return "Média"


def calcular_confianca_final(resultados: list[dict]) -> str:
    confiancas = [r.get("confianca", "Baixa") for r in resultados]

    if "Alta" in confiancas:
        return "Alta"
    if "Média" in confiancas:
        return "Média"
    if resultados:
        return "Baixa"
    return "Não encontrado"


def ordenar_resultados_por_confianca(resultados: list[dict]) -> list[dict]:
    ordem = {"Alta": 0, "Média": 1, "Baixa": 2}
    return sorted(resultados, key=lambda r: ordem.get(r.get("confianca", "Baixa"), 3))


# =====================================================
# BUSCA WEB OEM / CATÁLOGOS
# =====================================================

def buscar_duckduckgo(query_texto: str, limite: int = 8) -> list[dict]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query_texto)}"

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
            confianca = calcular_confianca_fonte(titulo, snippet, link)
            resultados.append({
                "titulo": titulo,
                "link": link,
                "snippet": snippet,
                "confianca": confianca,
            })

    return resultados


def buscar_fontes_oem(part_number: str) -> list[dict]:
    consultas = [
        f'"{part_number}" "parts catalog"',
        f'"{part_number}" OEM motorcycle part',
        f'"{part_number}" fiche motorcycle',
        f'"{part_number}" "genuine parts" motorcycle',
        f'"{part_number}" "catálogo de peças"',
        f'"{part_number}" Honda Yamaha Suzuki Kawasaki Dafra',
    ]

    todos = []
    links_vistos = set()

    for consulta in consultas:
        resultados = buscar_duckduckgo(consulta, limite=6)
        for r in resultados:
            chave = r.get("link") or r.get("titulo")
            if chave and chave not in links_vistos:
                todos.append(r)
                links_vistos.add(chave)

    return ordenar_resultados_por_confianca(todos)


# =====================================================
# MERCADO LIVRE
# =====================================================

def buscar_mercado_livre(termo: str, limite: int = 30) -> list[dict]:
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

    for anuncio in anuncios:
        titulo = anuncio["titulo"].lower()
        titulo_limpo = titulo.replace("-", "")
        pontos = 0

        if pn_limpo in titulo_limpo:
            pontos += 5

        if marca != "Não identificado" and marca.lower() in titulo:
            pontos += 2

        if peca != "Peça" and peca.lower() in titulo:
            pontos += 2

        if modelo != "Não identificado":
            for parte_modelo in modelo.lower().split("/"):
                parte_modelo = parte_modelo.strip()
                if parte_modelo and parte_modelo in titulo:
                    pontos += 2

        if pontos >= 2:
            anuncio_com_score = dict(anuncio)
            anuncio_com_score["score"] = pontos
            relevantes.append(anuncio_com_score)

    relevantes.sort(key=lambda x: x["score"], reverse=True)
    return relevantes


def calcular_media_precos(anuncios: list[dict]) -> dict:
    precos = [a["preco"] for a in anuncios if a.get("preco")]

    if not precos:
        return {"media": None, "mediana": None, "minimo": None, "maximo": None, "quantidade": 0}

    precos_ordenados = sorted(precos)

    # Remove o menor e o maior valor quando houver volume suficiente,
    # para reduzir distorção de anúncios fora da realidade.
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


def dinheiro(valor: float) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")


# =====================================================
# GERAÇÃO DE TÍTULO / DESCRIÇÃO
# =====================================================

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
        "Carenagem": "Carenag",
        "Paralama": "Paralam",
        "Yamaha": "Yam",
    }

    for antigo, novo in substituicoes.items():
        titulo = titulo.replace(antigo, novo)
        if len(titulo) <= 60:
            return titulo

    return titulo[:60].rstrip()


def gerar_titulo(peca: str, lado: str, marca: str, modelo: str) -> str:
    partes = []
    partes.append(peca if peca != "Peça" else "Peça")

    if lado in ["Direito", "Esquerdo"]:
        partes.append(lado)

    if marca != "Não identificado":
        partes.append(marca)

    if modelo != "Não identificado":
        partes.append(modelo.split("/")[0].strip())

    partes.append("Original")

    return limitar_titulo_60(" ".join(partes))


def gerar_descricao(peca: str, marca: str, modelo: str, anos: str, lado: str, part_number: str, confianca: str) -> str:
    nome_peca = peca if peca != "Peça" else "Peça"
    lado_txt = f" {lado}" if lado in ["Direito", "Esquerdo"] else ""
    marca_txt = marca if marca != "Não identificado" else ""
    modelo_txt = modelo if modelo != "Não identificado" else "modelo compatível"
    anos_txt = f" ({anos})" if anos != "Não identificado" else ""

    return f"""Esse anúncio contém: 01 {nome_peca}{lado_txt} {marca_txt} {modelo_txt}{anos_txt} - ORIGINAL

Código da peça / Part Number: {part_number}

Produto usado em condições de uso. Favor verificar todas as fotos do anúncio antes da compra, pois elas fazem parte da descrição do produto.

Compatibilidade identificada:
Marca: {marca}
Modelo: {modelo}
Ano: {anos}
Lado: {lado}
Código OEM: {part_number}
Nível de confiança da identificação: {confianca}

Peça original retirada de veículo adquirido em leilão/sucata legalizada, com procedência e nota fiscal.

Antes da compra, confira o código da peça e compare com a peça da sua moto para garantir compatibilidade."""


def gerar_palavras_chave(peca: str, marca: str, modelo: str, anos: str, lado: str, part_number: str) -> str:
    termos = [part_number, peca, marca, modelo, anos, lado, "original", "peça usada", "moto", "OEM"]
    termos = [t for t in termos if t and t not in ["Não identificado", "Sem lado identificado"]]
    return ", ".join(dict.fromkeys(termos))


# =====================================================
# INTERFACE STREAMLIT
# =====================================================

st.title("🔎 Wise Part Number Finder V2")
st.caption("Digite o código da peça. O app prioriza catálogo/OEM e usa Mercado Livre apenas para preço e referência comercial.")

part_number_input = st.text_input("Digite o Part Number", placeholder="Ex: 64320-K2G-9200")

if part_number_input:
    part_number = limpar_part_number(part_number_input)

    with st.spinner("Buscando em catálogos/OEM, web pública e Mercado Livre..."):
        resultados_web = buscar_fontes_oem(part_number)
        texto_web = texto_total_resultados(resultados_web)

        confianca_final = calcular_confianca_final(resultados_web)
        marca = detectar_marca(texto_web)
        lado = detectar_lado(texto_web)
        anos = detectar_anos(texto_web)
        modelo = extrair_modelos(texto_web)
        peca = inferir_nome_peca(texto_web)

        anuncios_pn = buscar_mercado_livre(part_number, limite=30)

        termo_nome = " ".join([
            item for item in [
                peca,
                marca,
                modelo.split("/")[0].strip() if modelo != "Não identificado" else ""
            ]
            if item and item != "Não identificado" and item != "Peça"
        ])

        anuncios_nome = buscar_mercado_livre(termo_nome, limite=30) if termo_nome else []

        anuncios_total = anuncios_pn + anuncios_nome
        anuncios_relevantes = filtrar_anuncios_relevantes(anuncios_total, part_number, peca, marca, modelo)
        anuncios_para_preco = anuncios_relevantes if anuncios_relevantes else anuncios_pn
        preco_info = calcular_media_precos(anuncios_para_preco)

        titulo_ml = gerar_titulo(peca, lado, marca, modelo)
        descricao = gerar_descricao(peca, marca, modelo, anos, lado, part_number, confianca_final)
        palavras_chave = gerar_palavras_chave(peca, marca, modelo, anos, lado, part_number)

    st.subheader("Informações identificadas")

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Código:** {part_number}")
        st.write(f"**Peça:** {peca}")
        st.write(f"**Marca:** {marca}")
        st.write(f"**Confiança:** {confianca_final}")
    with col2:
        st.write(f"**Modelo:** {modelo}")
        st.write(f"**Ano:** {anos}")
        st.write(f"**Lado:** {lado}")

    if confianca_final in ["Baixa", "Não encontrado"]:
        st.warning("A identificação ainda não está totalmente confiável. Confira o código OEM antes de publicar.")
    elif confianca_final == "Média":
        st.info("Identificação com confiança média. Recomendado conferir as fontes antes de publicar.")
    else:
        st.success("Identificação com confiança alta por fonte compatível com catálogo/OEM.")

    st.subheader("Média de valores Mercado Livre")

    if preco_info["media"]:
        st.write(f"**Preço médio:** {dinheiro(preco_info['media'])}")
        st.write(f"**Mediana:** {dinheiro(preco_info['mediana'])}")
        st.write(f"**Faixa analisada:** {dinheiro(preco_info['minimo'])} a {dinheiro(preco_info['maximo'])}")
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

    st.subheader("Fontes encontradas")
    if resultados_web:
        for r in resultados_web[:10]:
            emoji = "🟢" if r["confianca"] == "Alta" else "🟡" if r["confianca"] == "Média" else "🔴"
            st.markdown(f"{emoji} **Confiança {r['confianca']}** — [{r['titulo']}]({r['link']})")
            if r.get("snippet"):
                st.caption(r["snippet"])
    else:
        st.info("Nenhuma fonte web encontrada. Tente o código com hífen ou sem hífen.")

    st.subheader("Anúncios Mercado Livre usados como referência")
    if anuncios_para_preco:
        for a in anuncios_para_preco[:10]:
            st.markdown(f"- [{a['titulo']}]({a['link']}) — **{dinheiro(a['preco'])}**")
    else:
        st.info("Nenhum anúncio encontrado no Mercado Livre para esse código/peça.")

st.divider()
st.caption("Observação: o app prioriza fontes de catálogo/OEM, mas a conferência final do código e fotos ainda é recomendada.")
