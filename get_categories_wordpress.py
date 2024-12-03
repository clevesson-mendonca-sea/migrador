import requests
import os
import json
from dotenv import load_dotenv
import time  # Importando para adicionar delay

load_dotenv()

# Carregar variáveis de ambiente
WORDPRESS_API_URL = os.getenv("WORDPRESS_API_URL")
LIFERAY_API_BASE = os.getenv("LIFERAY_API_BASE")
LIFERAY_USERNAME = os.getenv("LIFERAY_USERNAME")
LIFERAY_PASSWORD = os.getenv("LIFERAY_PASSWORD")
LIFERAY_SITE_ID = os.getenv("LIFERAY_SITE_ID")

# URL para as categorias do WordPress
wp_api_url = f"{WORDPRESS_API_URL}/categories"

# Nome do vocabulário
taxonomy_vocabulary_name = "Categorias"

# Configuração de autenticação básica
auth = (LIFERAY_USERNAME, LIFERAY_PASSWORD)

# Função para obter todas as categorias do WordPress
def get_all_categories(api_url):
    categories = []
    page = 1

    while True:
        response = requests.get(api_url, params={"page": page, "per_page": 100})
        if response.status_code == 200:
            data = response.json()
            categories.extend(data)

            print(f"Página {page}: {len(data)} categorias obtidas do WordPress.")  # Log para verificar a quantidade de categorias por página

            if len(data) == 0:
                break
            page += 1
        else:
            print(f"Erro ao obter categorias do WordPress: {response.status_code}")
            break

    print(f"Total de categorias coletadas do WordPress: {len(categories)}")
    return categories

# Função para obter o vocabulário "Categorias" no Liferay
def get_taxonomy_vocabulary():
    url = f"{LIFERAY_API_BASE}/o/headless-admin-taxonomy/v1.0/sites/{LIFERAY_SITE_ID}/taxonomy-vocabularies"
    response = requests.get(url, auth=auth)

    if response.status_code == 200:
        vocabularies = response.json()['items']
        for vocab in vocabularies:
            if vocab['name'] == taxonomy_vocabulary_name:
                print(f"Vocabulário '{taxonomy_vocabulary_name}' já existe no Liferay. ID: {vocab['id']}")
                return vocab['id']
        print(f"Vocabulário '{taxonomy_vocabulary_name}' não encontrado. Criando...")
        return create_taxonomy_vocabulary()
    else:
        print(f"Erro ao acessar vocabulários no Liferay: {response}")
        print("Resposta da API:", response.text)  # Logando a resposta para diagnóstico
        return None

# Função para criar o vocabulário "Categorias" no Liferay
def create_taxonomy_vocabulary():
    url = f"{LIFERAY_API_BASE}/o/headless-admin-taxonomy/v1.0/sites/{LIFERAY_SITE_ID}/taxonomy-vocabularies"
    data = {"name": taxonomy_vocabulary_name}
    
    # Tentando criar o vocabulário
    response = requests.post(url, auth=auth, json=data)

    # Verificando a resposta
    if response.status_code == 200:
        print(f"Vocabulário '{taxonomy_vocabulary_name}' criado no Liferay.")
        print("Resposta da API após criação:", response.json())  # Logando a resposta para garantir que o vocabulário foi criado
        return response.json()['id']
    else:
        print(f"Erro ao criar vocabulário no Liferay: {response}")
        print("Resposta da API:", response.text)  # Imprimir o conteúdo da resposta para análise
        return None

# Função para obter todas as categorias do Liferay (paginado)
def get_liferay_categories(vocabulary_id):
    liferay_categories = []
    page = 1

    while True:
        url = f"{LIFERAY_API_BASE}/o/headless-admin-taxonomy/v1.0/taxonomy-vocabularies/{vocabulary_id}/taxonomy-categories"
        response = requests.get(url, params={"page": page, "pageSize": 100}, auth=auth)

        if response.status_code == 200:
            data = response.json()['items']
            liferay_categories.extend(data)

            print(f"Página {page}: {len(data)} categorias obtidas do Liferay.")  # Log para verificar a quantidade de categorias por página

            if len(data) == 0:
                break
            page += 1
        else:
            print(f"Erro ao acessar categorias do Liferay: {response.status_code}")
            break

    print(f"Total de categorias coletadas do Liferay: {len(liferay_categories)}")
    return {category['name'].strip().lower(): category['id'] for category in liferay_categories}

# Função para criar uma categoria no Liferay
def create_liferay_category(vocabulary_id, name):
    url = f"{LIFERAY_API_BASE}/o/headless-admin-taxonomy/v1.0/taxonomy-vocabularies/{vocabulary_id}/taxonomy-categories"
    data = {"name": name}
    response = requests.post(url, auth=auth, json=data)

    if response.status_code == 201:
        print(f"Categoria '{name}' criada no Liferay.")
        return response.json()['id']
    else:
        print(f"Erro ao criar categoria no Liferay: {response.status_code}")
        print("Resposta da API:", response.text)  # Logando o erro completo para análise
        return None

# Função para mapear as categorias do WordPress para o Liferay
def map_and_create_categories(wp_categories, vocabulary_id):
    # Obter categorias existentes do Liferay
    liferay_categories = get_liferay_categories(vocabulary_id)

    # Mapear as categorias
    category_mapping = []
    for wp_category in wp_categories:
        wp_name = wp_category["name"].strip().lower()  # Ajustando a comparação para ser insensível a espaços e maiúsculas/minúsculas
        wp_id = wp_category["id"]

        if wp_name in liferay_categories:
            print(f"A categoria '{wp_name}' já existe no Liferay.")
            category_mapping.append({
                "WordPress ID": wp_id,
                "WordPress Name": wp_category["name"],
                "Liferay ID": liferay_categories[wp_name],
                "Liferay Name": wp_category["name"]
            })
        else:
            print(f"A categoria '{wp_name}' não existe no Liferay. Criando...")
            liferay_category_id = create_liferay_category(vocabulary_id, wp_category["name"])
            if liferay_category_id:
                print(f"Categoria criada no Liferay: {wp_category['name']}")
                category_mapping.append({
                    "WordPress ID": wp_id,
                    "WordPress Name": wp_category["name"],
                    "Liferay ID": liferay_category_id,
                    "Liferay Name": wp_category["name"]
                })

    print(f"Total de categorias mapeadas: {len(category_mapping)}")
    return category_mapping

# Função para salvar o mapeamento em um JSON
def save_mapping_to_json(mapping, filename="category_mapping.json"):
    with open(filename, mode="w", encoding="utf-8") as file:
        json.dump(mapping, file, ensure_ascii=False, indent=4)

# Obter as categorias do WordPress
wordpress_categories = get_all_categories(wp_api_url)

# Obter ou criar o vocabulário 'Categorias' no Liferay
vocabulary_id = get_taxonomy_vocabulary()

if vocabulary_id:
    # Tentar acessar novamente após a criação (se necessário)
    print("Aguardando 20 segundos para garantir que o vocabulário foi registrado...")
    time.sleep(5) 
    vocabulary_id = get_taxonomy_vocabulary()  # Tentar acessar novamente

    if vocabulary_id:
        # Mapear e criar as categorias no Liferay
        category_mapping = map_and_create_categories(wordpress_categories, vocabulary_id)

        # Salvar o mapeamento
        save_mapping_to_json(category_mapping)
    else:
        print("Falha ao obter o vocabulário no Liferay após a criação.")
else:
    print("Falha ao obter ou criar o vocabulário no Liferay.")
