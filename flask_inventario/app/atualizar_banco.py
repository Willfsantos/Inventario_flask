import os
import sqlite3

print("Procurando o banco de dados...")

# Procura todos os arquivos .db na pasta atual e nas subpastas
bancos_encontrados = []
for root, dirs, files in os.walk('.'):
    for file in files:
        if file.endswith('.db') or file.endswith('.sqlite'):
            bancos_encontrados.append(os.path.join(root, file))

if not bancos_encontrados:
    print("Nenhum arquivo de banco de dados encontrado no projeto!")
else:
    for banco in bancos_encontrados:
        try:
            conexao = sqlite3.connect(banco)
            cursor = conexao.cursor()
            
            # Verifica se a tabela de inventário realmente existe dentro deste arquivo
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventario_item'")
            if cursor.fetchone():
                print(f"Banco correto encontrado: {banco}")
                # Injeta a coluna
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS chamado_suporte (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    funcionario_id INTEGER NOT NULL,
                    descricao TEXT NOT NULL,
                    status VARCHAR(20) DEFAULT 'Aberto',
                    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
                conexao.commit()
                print("✅ Sucesso! A coluna 'status' foi adicionada sem perder dados.")
            
            conexao.close()
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"⚠️ A coluna 'status' já existe no banco: {banco}")
            else:
                print(f"❌ Erro ao atualizar {banco}: {e}")