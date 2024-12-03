import create_folders  # Supondo que este seja o nome deste script
import create_news  # Outro script que cria notícias no Liferay

def main():
    print("Iniciando o processo de migração de imagens e criação de notícias...")

    print("\n=== Etapa 1: Migração de imagens ===")
    try:
        create_folders.process_posts()  # Função principal do script de migração de imagens
        print("Migração de imagens concluída com sucesso!")
    except Exception as e:
        print(f"Erro ao migrar imagens: {e}")
        return

    print("\n=== Etapa 2: Criação de notícias ===")
    try:
        create_news.main()  # Função principal do script de criação de notícias
        print("Criação de notícias concluída com sucesso!")
    except Exception as e:
        print(f"Erro ao criar notícias: {e}")

if __name__ == "__main__":
    main()
