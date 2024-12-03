import requests
import os
import logging
import re
from dotenv import load_dotenv
import json

# Configurar logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # Log no console
        logging.FileHandler("migration.log", mode="w"),  # Log em arquivo
    ],
)

# Carregar configurações do .env
load_dotenv()

WORDPRESS_API_URL = os.getenv("WORDPRESS_API_URL")
LIFERAY_API_BASE = os.getenv("LIFERAY_API_BASE")
LIFERAY_SITE_ID = os.getenv("LIFERAY_SITE_ID")
LIFERAY_USERNAME = os.getenv("LIFERAY_USERNAME")
LIFERAY_PASSWORD = os.getenv("LIFERAY_PASSWORD")
TEMP_FOLDER = os.getenv("TEMP_FOLDER", "images_temp")
CATEGORY_MAPPING_FILE = os.getenv("CATEGORY_MAPPING_FILE", "category_mapping.json")

# Autenticação Liferay
AUTH = (LIFERAY_USERNAME, LIFERAY_PASSWORD)

liferay_api_url = f"{LIFERAY_API_BASE}/o/headless-delivery/v1.0"

# Contadores globais para logs de migração
folders_created = 0
images_uploaded = 0

# Criar pasta temporária para imagens
os.makedirs(TEMP_FOLDER, exist_ok=True)
logging.info(f"Pasta temporária configurada: {TEMP_FOLDER}")


def load_category_mapping():
    """Carregar mapeamento de categorias do JSON"""
    try:
        with open(CATEGORY_MAPPING_FILE, 'r', encoding='utf-8') as f:
            category_mapping = json.load(f)
        
        logging.info(f"Carregado mapeamento de {len(category_mapping)} categorias.")
        return category_mapping
    except Exception as e:
        logging.error(f"Erro ao carregar mapeamento de categorias: {e}")
        raise


def sanitize_folder_title(title):
    # Lista de palavras reservadas que não podem ser usadas como nome de pasta
    reserved_names = [
        "null", "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", 
        "com6", "com7", "com8", "com9", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", 
        "lpt6", "lpt7", "lpt8", "lpt9"
    ]

    # Verificar se o nome está em branco
    if not title:
        raise ValueError("O nome da pasta não pode estar em branco.")

    # Remover caracteres especiais
    invalid_chars = r'<>:"/\\|?*'
    for char in invalid_chars:
        title = title.replace(char, "")

    # Garantir que o título não termine com '..'
    if title.endswith(".."):
        title = title[:-2]

    # Garantir que o título não contenha sequências inválidas
    title = title.replace("../", "").replace("/...", "")

    # Verificar se o título é uma palavra reservada
    if title.lower() in reserved_names:
        title += "_safe"

    # Limitar o tamanho do título a 255 caracteres
    return title[:255]


def create_or_get_folder_in_liferay(title, site_id):
    global folders_created  # Usando variável global para contagem de pastas criadas

    sanitized_title = sanitize_folder_title(title)  # Sanitiza o título da pasta

    logging.info(f"Tentando obter ou criar a pasta '{sanitized_title}' no Liferay...")

    # Verificar se a pasta já existe
    try:
        response = requests.get(
            f"{liferay_api_url}/sites/{site_id}/document-folders",
            auth=AUTH,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        folders = data.get("items", [])

        # Verificar se a pasta já existe
        for folder in folders:
            if folder["name"] == sanitized_title:
                logging.info(
                    f"Pasta '{sanitized_title}' já existe no Liferay. Usando a pasta existente."
                )
                return folder["id"]  # Retorna o ID da pasta existente

        # Se a pasta não existir, criar uma nova pasta
        payload = {
            "name": sanitized_title,
            "description": f"Pasta para {sanitized_title}",
        }
        response = requests.post(
            f"{liferay_api_url}/sites/{site_id}/document-folders",
            json=payload,
            auth=AUTH,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        folder_id = response.json()["id"]
        folders_created += 1  # Incrementa o contador de pastas criadas
        logging.info(f"Pasta '{sanitized_title}' criada com sucesso. ID: {folder_id}")
        return folder_id

    except requests.exceptions.HTTPError as e:
        logging.error(f"Erro ao verificar ou criar a pasta '{sanitized_title}': {e}")
        logging.error(f"Resposta do servidor: {response.text}")
        raise
    except Exception as e:
        logging.error(f"Erro inesperado ao verificar ou criar pasta: {e}")
        raise


def check_if_image_exists_in_folder(folder_id, image_name):
    try:
        # Verificar documentos na pasta para ver se a imagem já existe
        response = requests.get(
            f"{liferay_api_url}/document-folders/{folder_id}/documents",
            auth=AUTH,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

        # Verificar se a imagem já existe pelo nome
        for document in data["items"]:
            if document["title"] == image_name:
                logging.info(f"A imagem '{image_name}' já existe na pasta {folder_id}. Usando a URL existente.")
                return document["contentUrl"]  # Retorna a URL da imagem existente

        return None  # Se a imagem não foi encontrada

    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao verificar se a imagem '{image_name}' existe: {e}")
        raise


def upload_image_to_liferay(folder_id, image_path):
    global images_uploaded  # Usando variável global para contagem de imagens enviadas

    image_name = os.path.basename(image_path)
    existing_image_url = check_if_image_exists_in_folder(folder_id, image_name)

    if existing_image_url:
        # Se a imagem já existe, usar a URL existente
        images_uploaded += 1 
        logging.info(f"Imagem '{image_name}' já existe. Usando URL: {existing_image_url}")
        return existing_image_url

    logging.info(f"Fazendo upload da imagem '{image_path}' para o Liferay...")
    with open(image_path, "rb") as image_file:
        files = {"file": (image_name, image_file, "image/jpeg")}
        try:
            response = requests.post(
                f"{liferay_api_url}/document-folders/{folder_id}/documents",
                files=files,
                auth=AUTH,
            )
            response.raise_for_status()
            new_url = response.json()["contentUrl"]
            images_uploaded += 1
            logging.info(f"Upload concluído. Nova URL: {new_url}")
            return new_url
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro ao fazer upload da imagem '{image_name}': {e}")
            raise


def download_image(url, save_path):
    logging.info(f"Baixando imagem de: {url}")
    try:
        # Lidar com URLs relativas
        if url.startswith('/'):
            url = f"https://www2.tc.df.gov.br{url}"
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(save_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        logging.info(f"Imagem salva em: {save_path}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao baixar a imagem de {url}: {e}")
        raise


def extract_image_urls(content):
    # Regex para encontrar as URLs das imagens dentro das tags <img>
    image_urls = re.findall(r'<img[^>]+src="([^"]+)"', content)
    return image_urls


def filter_valid_image_urls(image_urls):
    valid_urls = []
    for url in image_urls:
        if (
            url.startswith("https://www2.tc.df.gov.br")
            or url.startswith("/wp-content")
            or url.startswith("/wp-conteudo")
        ):
            valid_urls.append(url)
    return valid_urls


def get_posts_by_category(category_id):
    """Buscar posts de uma categoria específica"""
    logging.info(f"Buscando posts da categoria {category_id}...")
    posts = []
    page = 1
    per_page = 100  # Número de posts por página

    while True:
        # Montar URL com paginação e categoria
        paginated_url = f"{WORDPRESS_API_URL}/posts?categories={category_id}&per_page={per_page}&page={page}"
        logging.info(f"Buscando página {page} de posts: {paginated_url}")
        
        try:
            response = requests.get(paginated_url)
            response.raise_for_status()

            # Adicionar os posts da página atual
            data = response.json()
            posts.extend(data)
            logging.info(
                f"Página {page} obtida com sucesso, {len(data)} posts adicionados."
            )

            # Verificar se há mais páginas
            if len(data) < per_page:
                logging.info("Todas as páginas foram processadas.")
                break

            page += 1

        except requests.exceptions.RequestException as e:
            logging.error(f"Erro ao buscar posts da categoria {category_id}: {e}")
            break

    logging.info(f"Total de {len(posts)} posts obtidos para a categoria {category_id}.")
    return posts

def generate_unique_name(base_name, existing_names):
    """Gera um nome único adicionando um sufixo numérico, se necessário."""
    counter = 1
    new_name = base_name
    while new_name in existing_names:
        new_name = f"{base_name}_{counter}"
        counter += 1
    return new_name


def generate_unique_folder_name(base_name, parent_folder_id):
    response = requests.get(
        f"{liferay_api_url}/document-folders/{parent_folder_id}/document-folders",
        auth=AUTH,
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    existing_names = [folder["name"] for folder in response.json().get("items", [])]

    return generate_unique_name(base_name, existing_names)

def create_or_get_subfolder(parent_folder_id, subfolder_name):
    if not subfolder_name.strip():
        subfolder_name = "SEM TITULO"
        
    
    sanitized_title = sanitize_folder_title(subfolder_name)
    logging.info(f"Tentando obter ou criar a subpasta '{sanitized_title}' dentro da pasta {parent_folder_id}...")

    try:
        # Verificar subpastas existentes
        response = requests.get(
            f"{liferay_api_url}/document-folders/{parent_folder_id}/document-folders",
            auth=AUTH,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

        # Obter os nomes das subpastas existentes
        existing_names = {folder["name"] for folder in data.get("items", [])}

        # Gerar um nome único se necessário
        unique_name = generate_unique_name(sanitized_title, existing_names)

        # Verificar se a subpasta já existe
        for folder in data.get("items", []):
            if folder["name"] == unique_name:
                logging.info(f"Subpasta '{unique_name}' já existe. ID: {folder['id']}")
                return folder["id"]

        # Criar subpasta se não existir
        payload = {
            "name": unique_name,
            "description": f"Subpasta para {unique_name}",
        }
        response = requests.post(
            f"{liferay_api_url}/document-folders/{parent_folder_id}/document-folders",
            json=payload,
            auth=AUTH,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        folder_id = response.json()["id"]
        logging.info(f"Subpasta '{unique_name}' criada com sucesso. ID: {folder_id}")
        return folder_id

    except requests.exceptions.HTTPError as e:
        # Log the error but continue processing
        logging.error(f"Erro ao verificar ou criar a subpasta '{sanitized_title}': {e}")
        logging.error(f"Resposta do servidor: {getattr(e.response, 'text', 'Sem detalhes adicionais')}")
        
        # Generate a unique name and try again with a different suffix
        try:
            unique_name = generate_unique_name(sanitized_title, 
                {folder["name"] for folder in requests.get(
                    f"{liferay_api_url}/document-folders/{parent_folder_id}/document-folders",
                    auth=AUTH,
                    headers={"Content-Type": "application/json"}
                ).json().get("items", [])})
            
            payload = {
                "name": unique_name,
                "description": f"Subpasta para {unique_name}",
            }
            response = requests.post(
                f"{liferay_api_url}/document-folders/{parent_folder_id}/document-folders",
                json=payload,
                auth=AUTH,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            folder_id = response.json()["id"]
            logging.warning(f"Subpasta criada com nome alternativo: '{unique_name}'. ID: {folder_id}")
            return folder_id
        except Exception as retry_error:
            # Log the error but don't stop the entire process
            logging.error(f"Erro de contingência ao criar subpasta: {retry_error}")
            # Return the parent folder ID to ensure processing continues
            return parent_folder_id

    except Exception as e:
        # Log unexpected errors but continue processing
        logging.error(f"Erro inesperado ao verificar ou criar subpasta: {e}")
        # Return the parent folder ID to ensure processing continues
        return parent_folder_id
    
def process_posts():
    logging.info("Iniciando processamento dos posts...")
    
    # Carregar mapeamento de categorias
    category_mapping = load_category_mapping()
    
    # Dicionário para rastrear posts processados para evitar duplicatas
    processed_post_ids = set()

    for category_map in category_mapping:
        wordpress_category_id = category_map['WordPress ID']
        wordpress_category_name = category_map['WordPress Name']
        liferay_category_id = category_map['Liferay ID']
        liferay_category_name = category_map['Liferay Name']
        
        logging.info(f"Processando categoria: {wordpress_category_name} (WordPress ID: {wordpress_category_id}, Liferay ID: {liferay_category_id})")
        
        # Buscar posts desta categoria
        posts = get_posts_by_category(wordpress_category_id)
        
        for post in posts:
            post_id = post["id"]

            # Pular posts já processados
            if post_id in processed_post_ids:
                logging.info(f"Post {post_id} já processado. Pulando.")
                continue

            processed_post_ids.add(post_id)

            post_title = post["title"]["rendered"]
            post_content = post["content"]["rendered"]
            post_date = post["date"]

            logging.info(f"Processando post '{post_title}' (ID: {post_id}, Categoria: {wordpress_category_name})")

            # Extrair URLs das imagens do conteúdo
            image_urls = extract_image_urls(post_content)
            valid_image_urls = filter_valid_image_urls(image_urls)

            if not valid_image_urls:
                logging.info(f"Nenhuma imagem válida encontrada no post '{post_title}'. Pulando subpasta.")
                continue  # Se não houver imagens, pula para o próximo post

            # Criar ou obter a pasta principal da categoria
            folder_id = create_or_get_folder_in_liferay(liferay_category_name, LIFERAY_SITE_ID)

            # Criar ou obter a subpasta correspondente ao título da página
            subfolder_id = create_or_get_subfolder(folder_id, post_title)

            # Baixar e carregar imagens na subpasta correspondente
            for image_url in valid_image_urls:
                try:
                    image_name = os.path.basename(image_url)
                    image_path = os.path.join(TEMP_FOLDER, image_name)

                    # Baixar imagem
                    download_image(image_url, image_path)

                    # Enviar imagem para o Liferay
                    upload_image_to_liferay(subfolder_id, image_path)

                    # Limpar imagem temporária
                    os.remove(image_path)
                except Exception as e:
                    logging.error(f"Erro ao processar a imagem {image_url} do post {post_id}: {e}")


            logging.info(f"Processamento completo. {folders_created} pastas criadas e {images_uploaded} imagens enviadas.")


# Iniciar o processamento dos posts
if __name__ == "__main__":
    try:
        process_posts()
    except Exception as e:
        logging.error(f"Erro no processo de migração: {e}")