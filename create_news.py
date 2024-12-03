import requests
import os
import json
import unidecode
import re
from dotenv import load_dotenv
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

liferay_base_url = os.getenv("LIFERAY_API_BASE")
site_id = os.getenv("LIFERAY_SITE_ID")
content_structure_id = os.getenv("CONTENT_STRUCTURE_ID")
username = os.getenv("LIFERAY_USERNAME")
password = os.getenv("LIFERAY_PASSWORD")
WORDPRESS_API_URL = os.getenv("WORDPRESS_API_URL")

url_mapping_file = "url_mapping.json"
categories_mapping_file = "category_mapping.json"
liferay_api_url = f"{liferay_base_url}/o/headless-delivery/v1.0/sites/{site_id}/structured-contents"

def load_url_mapping(mapping_file):
    """Carregar o mapeamento de URLs antigas para novas"""
    logger.info(f"Carregando mapeamento de URLs do arquivo: {mapping_file}")
    if os.path.exists(mapping_file):
        with open(mapping_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_new_url_mapping(original_url, new_url):
    """Salvar mapeamento de URLs em arquivo JSON"""
    logger.info(f"Salvando mapeamento: {original_url} -> {new_url}")
    if os.path.exists(url_mapping_file):
        with open(url_mapping_file, "r", encoding="utf-8") as f:
            mapping = json.load(f)
    else:
        mapping = []

    mapping.append({"original_url": original_url, "new_url": new_url})

    with open(url_mapping_file, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=4)

def load_categories_mapping():
    """
    Carrega o mapeamento de categorias do arquivo JSON.
    :return: Lista de mapeamentos de categorias
    """
    logger.info(f"Carregando mapeamento de categorias do arquivo: {categories_mapping_file}")
    try:
        with open(categories_mapping_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Arquivo de mapeamento de categorias não encontrado: {categories_mapping_file}")
        return []

def replace_image_urls(content, url_mapping):
    """Substituir URLs de imagens no conteúdo"""
    logger.info("Substituindo URLs de imagens no conteúdo...")
    for mapping in url_mapping:
        original_url = mapping["original_url"]
        new_url = mapping["new_url"]
        content = content.replace(original_url, new_url)
    return content

def generate_friendly_url(title):
    """
    Gera uma URL amigável a partir de um título, removendo acentos e caracteres especiais.
    :param title: Título da postagem.
    :return: URL amigável.
    """
    # Remover acentos e normalizar o texto
    normalized_title = unidecode.unidecode(title)
    friendly_url = re.sub(r"[^\w\s-]", "", normalized_title)  # Remove caracteres não alfanuméricos
    friendly_url = re.sub(r"\s+", "-", friendly_url)  # Substitui espaços por hífens
    friendly_url = friendly_url.lower()  # Transforma em minúsculas
    return friendly_url.strip("-")  # Remove hífens do início ou do final

def fetch_posts(wordpress_categories):
    """
    Buscar todos os posts do WordPress com paginação e filtro de categorias
    :param wordpress_categories: Lista de IDs de categorias do WordPress
    """
    posts = []
    per_page = 100  # Número de posts por página
    logger.info(f"Iniciando busca por posts no WordPress. Categorias: {wordpress_categories}")

    # Se a lista de categorias estiver vazia, buscar todos os posts
    if not wordpress_categories:
        api_url = f"{WORDPRESS_API_URL}/posts?per_page={per_page}"
        response = requests.get(api_url)

        if response.status_code == 200:
            posts = response.json()
            logger.info(f"Total de {len(posts)} posts encontrados.")
            return posts
        else:
            logger.error(f"Erro ao acessar o JSON: {response.status_code} - {response.text}")
            raise Exception(f"Erro ao acessar o JSON: {response.status_code} - {response.text}")

    # Se houver categorias, buscar para cada categoria individualmente
    for category_id in wordpress_categories:
        page = 1
        while True:
            api_url = f"{WORDPRESS_API_URL}/posts?categories={category_id}&per_page={per_page}&page={page}"
            logger.info(f"Buscando página {page} de posts para categoria {category_id}: {api_url}")
            response = requests.get(api_url)

            if response.status_code == 200:
                data = response.json()
                posts.extend(data)  # Adiciona os posts da página atual
                logger.info(f"Página {page} carregada com sucesso. {len(data)} posts encontrados.")

                # Verificar se há mais páginas
                total_pages = int(response.headers.get("X-WP-TotalPages", 1))
                if page >= total_pages:
                    logger.info(f"Todas as páginas para categoria {category_id} foram carregadas.")
                    break  
                page += 1 
            else:
                logger.error(f"Erro ao acessar o JSON: {response.status_code} - {response.text}")
                raise Exception(f"Erro ao acessar o JSON: {response.status_code} - {response.text}")

    logger.info(f"Total de {len(posts)} posts encontrados.")
    return posts

def update_content_in_liferay(content_id, updated_html):
    """
    Atualizar o conteúdo no Liferay com novos links internos.
    :param content_id: ID do conteúdo no Liferay.
    :param updated_html: Novo conteúdo HTML com links atualizados.
    """
    logger.info(f"Atualizando conteúdo com ID: {content_id}")

    update_url = f"{liferay_base_url}/o/headless-delivery/v1.0/structured-contents/{content_id}"
    auth = (username, password)
    headers = {"Content-Type": "application/json"}

    payload = {
        "contentFields": [
            {
                "name": "TextoMateria",
                "contentFieldValue": {"data": updated_html},
            }
        ]
    }

    try:
        response = requests.patch(update_url, json=payload, auth=auth, headers=headers)

        if response.status_code == 200:
            logger.info(f"Conteúdo atualizado com sucesso: {content_id}")
        else:
            logger.error(f"Erro ao atualizar conteúdo: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao atualizar conteúdo: {e}")

def get_content_id_by_friendly_url(friendly_url):
    """
    Buscar o ID de um conteúdo no Liferay pelo Friendly URL.
    :param friendly_url: Friendly URL do conteúdo.
    :return: ID do conteúdo ou None se não encontrado.
    """
    logger.info(f"Buscando o ID do conteúdo pelo Friendly URL: {friendly_url}")
    search_url = f"{liferay_api_url}?filter=friendlyUrlPath eq '{friendly_url}'"
    auth = (username, password)

    try:
        response = requests.get(search_url, auth=auth)
        if response.status_code == 200:
            results = response.json().get("items", [])
            if results:
                return results[0]["id"]
        else:
            logger.error(f"Erro ao buscar conteúdo: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar conteúdo: {e}")

    return None

def replace_internal_links(content, url_mapping):
    """
    Substituir links internos no conteúdo com base no mapeamento.
    :param content: HTML do conteúdo original.
    :param url_mapping: Lista de mapeamento de URLs.
    :return: HTML com os links internos atualizados.
    """
    logger.info("Substituindo links internos no conteúdo...")
    for mapping in url_mapping:
        original_url = mapping["original_url"]
        new_url = mapping["new_url"]
        content = content.replace(original_url, new_url)
    return content

def format_date_for_liferay(post_date):
    """
    Formata a data no formato esperado pelo Liferay, com milissegundos e o sufixo 'Z' (UTC).
    """
    date_created = datetime.strptime(post_date, "%Y-%m-%dT%H:%M:%S")
    date_created_str = date_created.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"
    
    return date_created_str

def process_post(post_data, url_mapping, category_mapping):
    """
    Processar cada post e criar o conteúdo no Liferay
    :param post_data: Dados do post do WordPress
    :param url_mapping: Mapeamento de URLs
    :param category_mapping: Mapeamento de categorias
    """
    logger.info(f"Processando o post '{post_data.get('title', {}).get('rendered', 'Sem título')}'")

    liferay_category_ids = []
    for category in post_data.get('categories', []):
        matching_categories = [
            mapping['Liferay ID'] 
            for mapping in category_mapping 
            if mapping['WordPress ID'] == category
        ]
        liferay_category_ids.extend(matching_categories)

    content_html = post_data.get("content", {}).get("rendered", "")

    post_title = post_data["title"]["rendered"]
    friendly_url = generate_friendly_url(post_title)

    date_created_str = None
    if "date_gmt" in post_data:
        date_created_str = format_date_for_liferay(post_data["date_gmt"])

    content_html = replace_image_urls(content_html, url_mapping)

    payload = {
        "contentStructureId": content_structure_id,
        "title": post_title,
        "friendlyUrlPath": friendly_url,
        "dateCreated": date_created_str,
        "taxonomyCategoryIds": liferay_category_ids,
        "contentFields": [
            {
                "name": "TextoMateria",
                "contentFieldValue": {"data": content_html},
            }
        ],
    }

    excerpt = post_data.get("excerpt", {}).get("rendered")
    if excerpt:
        payload["contentFields"].append({
            "name": "Chamada",
            "contentFieldValue": {"data": excerpt},
        })

    auth = (username, password)
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(liferay_api_url, json=payload, auth=auth, headers=headers)

        if response.status_code in (200, 201):
            # Extrair a URL da nova página criada
            response_data = response.json()
            new_page_url = response_data.get("friendlyUrlPath", "URL não encontrada")
            logger.info(f"Conteúdo criado com sucesso: {new_page_url}")

            original_url = post_data.get("link", "URL antiga não encontrada")
            save_new_url_mapping(original_url, new_page_url)
        else:
            logger.error(f"Erro ao criar conteúdo: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao criar conteúdo: {e}")

def main():
    """Função principal para carregar os posts e processá-los"""
    try:
        logger.info("Iniciando processamento dos posts do WordPress.")
        
        category_mapping = load_categories_mapping()

        wordpress_categories = [
            mapping['WordPress ID'] 
            for mapping in category_mapping
        ]

        posts_data = fetch_posts(wordpress_categories)

        url_mapping = load_url_mapping(url_mapping_file)

        for post_data in posts_data:
            process_post(post_data, url_mapping, category_mapping)

        logger.info("Todos os conteúdos foram criados com sucesso.")

        url_mapping = load_url_mapping(url_mapping_file)

        for post_data in posts_data:
            post_title = post_data["title"]["rendered"]
            friendly_url = generate_friendly_url(post_title)

            content_id = get_content_id_by_friendly_url(friendly_url)

            if content_id:
                # Substituir links internos no conteúdo
                content_html = post_data["content"]["rendered"]
                updated_html = replace_internal_links(content_html, url_mapping)

                if updated_html != content_html:
                    update_content_in_liferay(content_id, updated_html)

        logger.info("Todos os conteúdos foram atualizados com links internos corrigidos.")

    except Exception as e:
        logger.critical(f"Erro crítico: {e}")


if __name__ == "__main__":
    main()