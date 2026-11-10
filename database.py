import sqlite3
import os
import csv
import shutil
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta


def _resolver_caminho_db() -> str:
    """
    Resolve o caminho gravável para o banco SQLite tanto no Android (Flet)
    quanto no Desktop durante o desenvolvimento/testes.
    """
    storage_dir = os.environ.get("FLET_APP_STORAGE_DATA")
    if storage_dir:
        os.makedirs(storage_dir, exist_ok=True)
        destino = os.path.join(storage_dir, "estoque.db")
        origem_local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estoque.db")
        if not os.path.exists(destino) and os.path.exists(origem_local):
            try:
                shutil.copy2(origem_local, destino)
            except Exception:
                pass
        # Copia também funcionarios.db e fotos_funcionarios para o storage do Android na primeira inicialização
        destino_func = os.path.join(storage_dir, "funcionarios.db")
        origem_func = os.path.join(os.path.dirname(os.path.abspath(__file__)), "funcionarios.db")
        if not os.path.exists(destino_func) and os.path.exists(origem_func):
            try:
                shutil.copy2(origem_func, destino_func)
            except Exception:
                pass
        destino_fotos = os.path.join(storage_dir, "fotos_funcionarios")
        origem_fotos = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fotos_funcionarios")
        if not os.path.exists(destino_fotos) and os.path.exists(origem_fotos):
            try:
                shutil.copytree(origem_fotos, destino_fotos)
            except Exception:
                pass
        return destino
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "estoque.db")


DB_PATH = _resolver_caminho_db()
FUNC_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "funcionarios.db")


def get_db_path() -> str:
    return DB_PATH


def _get_func_db_path() -> str:
    """Retorna o caminho do banco de dados dedicado de funcionários (sempre na mesma pasta de DB_PATH)."""
    return os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "funcionarios.db")


def _init_and_sync_funcionarios_db(conn_estoque: Optional[sqlite3.Connection] = None) -> None:
    """
    Inicializa o banco dedicado 'funcionarios.db' (com suporte a foto_blob e foto_path)
    e garante sincronização bidirecional com a tabela 'usuarios' de estoque.db.
    """
    func_db = _get_func_db_path()
    conn_f = sqlite3.connect(func_db)
    conn_f.row_factory = sqlite3.Row
    cur_f = conn_f.cursor()
    try:
        cur_f.execute("PRAGMA journal_mode=WAL;")
        cur_f.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    cur_f.execute('''
    CREATE TABLE IF NOT EXISTS funcionarios (
        id TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        role TEXT NOT NULL,
        rfid_uid TEXT DEFAULT '',
        foto_path TEXT DEFAULT '',
        foto_nome TEXT DEFAULT '',
        foto_blob BLOB,
        atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    cur_f.execute("PRAGMA table_info(funcionarios)")
    cols_f = [c[1] for c in cur_f.fetchall()]
    if "rfid_uid" not in cols_f:
        cur_f.execute("ALTER TABLE funcionarios ADD COLUMN rfid_uid TEXT DEFAULT ''")
    if "foto_path" not in cols_f:
        cur_f.execute("ALTER TABLE funcionarios ADD COLUMN foto_path TEXT DEFAULT ''")
    if "foto_nome" not in cols_f:
        cur_f.execute("ALTER TABLE funcionarios ADD COLUMN foto_nome TEXT DEFAULT ''")
    if "foto_blob" not in cols_f:
        cur_f.execute("ALTER TABLE funcionarios ADD COLUMN foto_blob BLOB")

    close_est = False
    if conn_estoque is None:
        conn_estoque = sqlite3.connect(DB_PATH)
        close_est = True
    conn_estoque.row_factory = sqlite3.Row
    cur_e = conn_estoque.cursor()

    cur_e.execute("SELECT * FROM usuarios")
    rows_e = [dict(r) for r in cur_e.fetchall()]

    cur_f.execute("SELECT * FROM funcionarios")
    rows_f = {str(r["id"]): dict(r) for r in cur_f.fetchall()}

    for u in rows_e:
        uid = str(u["id"])
        nome_u = u.get("nome", "")
        if "Operário" in nome_u:
            nome_u = nome_u.replace("Operário", "Operador")
            cur_e.execute("UPDATE usuarios SET nome = ? WHERE id = ?", (nome_u, uid))

        rfid_u = (u.get("rfid_uid") or "").strip()
        foto_p = (u.get("foto_path") or "").strip()
        foto_blob = None
        foto_nome = ""
        if foto_p and os.path.isfile(foto_p):
            try:
                with open(foto_p, "rb") as f:
                    foto_blob = f.read()
                foto_nome = os.path.basename(foto_p)
            except Exception:
                pass

        if uid not in rows_f:
            cur_f.execute(
                '''
                INSERT INTO funcionarios (id, nome, role, rfid_uid, foto_path, foto_nome, foto_blob, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''',
                (uid, nome_u, u.get("role", "OPERARIO"), rfid_u, foto_p, foto_nome, foto_blob),
            )
        else:
            f_row = rows_f[uid]
            novo_blob = f_row.get("foto_blob") if f_row.get("foto_blob") else foto_blob
            novo_path = f_row.get("foto_path") or foto_p
            novo_nome = f_row.get("foto_nome") or foto_nome
            novo_rfid = f_row.get("rfid_uid") or rfid_u
            cur_f.execute(
                '''
                UPDATE funcionarios
                SET nome = ?, role = ?, rfid_uid = ?, foto_path = ?, foto_nome = ?, foto_blob = ?
                WHERE id = ?
                ''',
                (nome_u, u.get("role", "OPERARIO"), novo_rfid, novo_path, novo_nome, novo_blob, uid),
            )
            if novo_path != foto_p or novo_rfid != rfid_u:
                cur_e.execute(
                    "UPDATE usuarios SET rfid_uid = ?, foto_path = ? WHERE id = ?",
                    (novo_rfid, novo_path, uid),
                )

    conn_f.commit()
    conn_f.close()
    if close_est:
        conn_estoque.commit()
        conn_estoque.close()


def init_db() -> None:
    """Inicializa o banco de dados e cria as tabelas se não existirem."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    
    # Tabela de Estantes Físicas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS estantes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE,
        linhas INTEGER NOT NULL DEFAULT 5,
        colunas INTEGER NOT NULL DEFAULT 5,
        descricao TEXT DEFAULT '',
        data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Tabela de Peças (Adicionado campo 'quantidade_estoque' e 'estante_id')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pecas (
        id INTEGER PRIMARY KEY,
        nome TEXT NOT NULL,
        tipo TEXT NOT NULL,
        posicao_linha INTEGER NOT NULL,
        posicao_coluna INTEGER NOT NULL,
        peso_unitario_g REAL NOT NULL,
        dimensoes TEXT NOT NULL,
        quantidade_estoque INTEGER NOT NULL DEFAULT 0,
        estante_id INTEGER DEFAULT 1 REFERENCES estantes (id),
        descricao TEXT DEFAULT ''
    )
    ''')
    
    # Tabela de Histórico (com ordem_id e qtd_planejada para rastreabilidade do diário)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS historico_operacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        funcionario_id TEXT NOT NULL,
        peca_id INTEGER NOT NULL,
        tipo_operacao TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        data_hora DATETIME NOT NULL,
        ordem_id INTEGER REFERENCES ordens_servico(id),
        qtd_planejada INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (peca_id) REFERENCES pecas (id)
    )
    ''')
    
    # Tabela de Usuários (perfis: 'ADMIN', 'OPERARIO' e 'rfid_uid' opcional para login por crachá)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        role TEXT NOT NULL,
        rfid_uid TEXT DEFAULT '',
        foto_path TEXT DEFAULT ''
    )
    ''')
    
    # Tabela de Ordens de Serviço (Criadas pelo Admin para o Operador)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ordens_servico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ABERTA', -- 'ABERTA', 'CUMPRIDA', 'INCOMPLETA', 'NAO_CUMPRIDA', 'CONCLUIDA'
        operador_id TEXT,
        estante_id INTEGER DEFAULT 1 REFERENCES estantes (id),
        data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
        prazo_limite DATETIME,
        data_conclusao DATETIME
    )
    ''')
    
    # Tabela de Itens da Ordem de Serviço
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS itens_ordem_servico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ordem_id INTEGER NOT NULL,
        peca_id INTEGER NOT NULL,
        tipo_operacao TEXT NOT NULL, -- 'ADICAO' ou 'REMOCAO'
        quantidade INTEGER NOT NULL,
        quantidade_atendida INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (ordem_id) REFERENCES ordens_servico (id),
        FOREIGN KEY (peca_id) REFERENCES pecas (id)
    )
    ''')
    
    # Migração: garante que a Estante Principal (2x3) exista como estante padrão (id=1)
    cursor.execute("SELECT COUNT(*) FROM estantes")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
        INSERT INTO estantes (id, nome, linhas, colunas, descricao)
        VALUES (1, 'Estante Principal (2x3)', 2, 3, 'Estante Física Principal (2x3)')
        ''')

    # Migração: garante que a coluna quantidade_estoque exista em bancos antigos
    cursor.execute("PRAGMA table_info(pecas)")
    colunas = [col[1] for col in cursor.fetchall()]
    if 'quantidade_estoque' not in colunas:
        cursor.execute("ALTER TABLE pecas ADD COLUMN quantidade_estoque INTEGER NOT NULL DEFAULT 10")
    if 'descricao' not in colunas:
        cursor.execute("ALTER TABLE pecas ADD COLUMN descricao TEXT DEFAULT ''")
    if 'estante_id' not in colunas:
        cursor.execute("ALTER TABLE pecas ADD COLUMN estante_id INTEGER DEFAULT 1 REFERENCES estantes(id)")
    if 'rfid_uid' not in colunas:
        cursor.execute("ALTER TABLE pecas ADD COLUMN rfid_uid TEXT DEFAULT ''")
        
    # Migração: garante que colunas de rastreabilidade existam em ordens_servico
    cursor.execute("PRAGMA table_info(ordens_servico)")
    colunas_os = [col[1] for col in cursor.fetchall()]
    if 'operador_id' not in colunas_os:
        cursor.execute("ALTER TABLE ordens_servico ADD COLUMN operador_id TEXT")
    if 'prazo_limite' not in colunas_os:
        cursor.execute("ALTER TABLE ordens_servico ADD COLUMN prazo_limite DATETIME")
    if 'data_conclusao' not in colunas_os:
        cursor.execute("ALTER TABLE ordens_servico ADD COLUMN data_conclusao DATETIME")
    if 'estante_id' not in colunas_os:
        cursor.execute("ALTER TABLE ordens_servico ADD COLUMN estante_id INTEGER DEFAULT 1 REFERENCES estantes(id)")

    # Migração: garante que a coluna quantidade_atendida exista em itens_ordem_servico
    cursor.execute("PRAGMA table_info(itens_ordem_servico)")
    colunas_ios = [col[1] for col in cursor.fetchall()]
    if 'quantidade_atendida' not in colunas_ios:
        cursor.execute("ALTER TABLE itens_ordem_servico ADD COLUMN quantidade_atendida INTEGER NOT NULL DEFAULT 0")
        cursor.execute('''
        UPDATE itens_ordem_servico 
        SET quantidade_atendida = quantidade 
        WHERE ordem_id IN (SELECT id FROM ordens_servico WHERE status IN ('CONCLUIDA', 'CUMPRIDA'))
        ''')

    # Migração: garante que colunas ordem_id e qtd_planejada existam em historico_operacoes
    cursor.execute("PRAGMA table_info(historico_operacoes)")
    colunas_hist = [col[1] for col in cursor.fetchall()]
    if 'ordem_id' not in colunas_hist:
        cursor.execute("ALTER TABLE historico_operacoes ADD COLUMN ordem_id INTEGER REFERENCES ordens_servico(id)")
    if 'qtd_planejada' not in colunas_hist:
        cursor.execute("ALTER TABLE historico_operacoes ADD COLUMN qtd_planejada INTEGER NOT NULL DEFAULT 0")

    # Migração: garante que as colunas rfid_uid e foto_path existam em usuarios
    cursor.execute("PRAGMA table_info(usuarios)")
    colunas_usr = [col[1] for col in cursor.fetchall()]
    if 'rfid_uid' not in colunas_usr:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN rfid_uid TEXT DEFAULT ''")
    if 'foto_path' not in colunas_usr:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN foto_path TEXT DEFAULT ''")

    # Remove as peças de teste antigas (Celular 901 e Chave de Fenda 902) para usar suas tags RFID como crachás de login
    cursor.execute("DELETE FROM itens_ordem_servico WHERE peca_id IN (901, 902)")
    cursor.execute("DELETE FROM pecas WHERE id IN (901, 902) OR UPPER(TRIM(rfid_uid)) IN ('C4 AE 78 E5', '47 09 9E A3')")

    # Padronização de nomenclatura: substitui 'Operário' por 'Operador' nos nomes de usuários já cadastrados
    cursor.execute("UPDATE usuarios SET nome = REPLACE(nome, 'Operário', 'Operador') WHERE nome LIKE '%Operário%'")

    # Garante que as 2 tags físicas padrão estejam atribuídas ao ADM (1000) e ao Operador (1001) caso estejam vazias
    cursor.execute("SELECT rfid_uid FROM usuarios WHERE id = '1000'")
    row_adm = cursor.fetchone()
    if row_adm and not (row_adm[0] or '').strip():
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE UPPER(TRIM(rfid_uid)) = 'C4 AE 78 E5'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("UPDATE usuarios SET rfid_uid = 'C4 AE 78 E5' WHERE id = '1000'")

    cursor.execute("SELECT rfid_uid FROM usuarios WHERE id = '1001'")
    row_op = cursor.fetchone()
    if row_op and not (row_op[0] or '').strip():
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE UPPER(TRIM(rfid_uid)) = '47 09 9E A3'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("UPDATE usuarios SET rfid_uid = '47 09 9E A3' WHERE id = '1001'")

    # Garante que todas as ordens existentes possuam prazo_limite preenchido
    cursor.execute("SELECT id, data_criacao FROM ordens_servico WHERE prazo_limite IS NULL")
    for os_id, dt_criacao in cursor.fetchall():
        try:
            dt_base = datetime.strptime(dt_criacao, "%Y-%m-%d %H:%M:%S")
        except Exception:
            dt_base = datetime.now()
        prazo = (dt_base + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE ordens_servico SET prazo_limite = ? WHERE id = ?", (prazo, os_id))

    conn.commit()
    _init_and_sync_funcionarios_db(conn)
    conn.close()

def popular_dados_teste() -> None:
    """Insere peças, usuários e ordens de serviço de exemplo caso o banco esteja vazio."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Popular Peças
    cursor.execute("SELECT COUNT(*) FROM pecas")
    if cursor.fetchone()[0] == 0:
        pecas_iniciais = [
            # Linha 0 - Parafusos
            (101, "Parafuso Sextavado M6", "Fixador", 0, 0, 8.5, "M6x20mm", 50),
            (102, "Parafuso Sextavado M8", "Fixador", 0, 1, 15.0, "M8x30mm", 40),
            (103, "Parafuso Sextavado M10", "Fixador", 0, 2, 28.0, "M10x40mm", 30),
            (104, "Parafuso Allen M5", "Fixador", 0, 3, 5.5, "M5x15mm", 80),
            (105, "Parafuso Philips M4", "Fixador", 0, 4, 3.2, "M4x10mm", 100),
            
            # Linha 1 - Porcas e Arruelas
            (201, "Porca Sextavada M6", "Fixador", 1, 0, 3.0, "M6", 120),
            (202, "Porca Sextavada M8", "Fixador", 1, 1, 5.2, "M8", 90),
            (203, "Porca Autotravante M10", "Fixador", 1, 2, 11.0, "M10", 45),
            (204, "Arruela Lisa M8", "Fixador", 1, 3, 2.0, "M8x16mm", 200),
            (205, "Arruela de Pressão M10", "Fixador", 1, 4, 3.5, "M10", 150),
            
            # Linha 2 - Componentes Elétricos
            (301, "Conector Sindal 2 Vias", "Elétrica", 2, 0, 12.0, "10mm2", 35),
            (302, "Terminal Ilhós Tubular", "Elétrica", 2, 1, 1.5, "2.5mm2", 300),
            (303, "Relé Auxiliar 24V", "Elétrica", 2, 2, 35.0, "5 Pinos", 20),
            (304, "Fusível Lâmina 15A", "Elétrica", 2, 3, 2.5, "15A Azul", 60),
            (305, "Disjuntor Mini DIN 10A", "Elétrica", 2, 4, 95.0, "Monopolar", 15),
            
            # Linha 3 - Componentes Mecânicos / Rolamentos
            (401, "Rolamento Rígido 608ZZ", "Mecânica", 3, 0, 12.5, "8x22x7mm", 40),
            (402, "Rolamento Esferas 6201", "Mecânica", 3, 1, 37.0, "12x32x10mm", 25),
            (403, "Bucha de Bronze", "Mecânica", 3, 2, 22.0, "10x14x20mm", 30),
            (404, "Anel Elástico Interno", "Mecânica", 3, 3, 4.0, "25mm", 75),
            (405, "Mola Helicoidal Compressão", "Mecânica", 3, 4, 8.0, "15x40mm", 50),
            
            # Linha 4 - Pneumática e Hidráulica
            (501, "Engate Rápido Pneumático", "Pneumática", 4, 0, 18.0, "6mm x 1/8", 40),
            (502, "União Reta Push-In", "Pneumática", 4, 1, 14.0, "8mm", 35),
            (503, "Anel O-Ring Vedação", "Hidráulica", 4, 2, 1.8, "20x3mm", 180),
            (504, "Silenciador Pneumático Bronze", "Pneumática", 4, 3, 24.0, "1/4 BSP", 25),
            (505, "Válvula Reguladora Fluxo", "Pneumática", 4, 4, 42.0, "6mm", 18),
        ]
        cursor.executemany('''
        INSERT INTO pecas (id, nome, tipo, posicao_linha, posicao_coluna, peso_unitario_g, dimensoes, quantidade_estoque)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', pecas_iniciais)
        
    # Popular Usuários com Crachás RFID padrão
    # Tag 1 (C4 AE 78 E5) -> Supervisor (ADMIN)
    # Tag 2 (47 09 9E A3) -> Operador (OPERARIO)
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        usuarios_iniciais = [
            ("1000", "Supervisor (Admin)", "ADMIN", "C4 AE 78 E5"),
            ("1001", "João (Operador)", "OPERARIO", "47 09 9E A3"),
            ("1002", "Maria (Operador)", "OPERARIO", "")
        ]
        cursor.executemany("INSERT INTO usuarios (id, nome, role, rfid_uid) VALUES (?, ?, ?, ?)", usuarios_iniciais)
        
    # Popular Ordens de Serviço de Exemplo
    cursor.execute("SELECT COUNT(*) FROM ordens_servico")
    if cursor.fetchone()[0] == 0:
        agora = datetime.now()
        prazo_padrao = (agora + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO ordens_servico (titulo, status, operador_id, prazo_limite) VALUES (?, ?, ?, ?)",
            ("Kit Montagem Painel Elétrico A", "ABERTA", "1001", prazo_padrao)
        )
        os_id = cursor.lastrowid
        itens_os = [
            (os_id, 101, "REMOCAO", 5),  # Retirar 5 Parafusos M6
            (os_id, 201, "REMOCAO", 5),  # Retirar 5 Porcas M6
            (os_id, 303, "REMOCAO", 2),  # Retirar 2 Relés 24V
            (os_id, 305, "REMOCAO", 1),  # Retirar 1 Disjuntor
        ]
        cursor.executemany('''
        INSERT INTO itens_ordem_servico (ordem_id, peca_id, tipo_operacao, quantidade)
        VALUES (?, ?, ?, ?)
        ''', itens_os)

    conn.commit()
    _init_and_sync_funcionarios_db(conn)
    conn.close()

def get_peca(peca_id: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pecas WHERE id = ?", (peca_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_peca_por_rfid(rfid_uid: str) -> Optional[Dict[str, Any]]:
    """Busca uma peça pelo UID da tag RFID (ignorando espaços extras e caixa)."""
    uid_limpo = " ".join(rfid_uid.strip().upper().split())
    if not uid_limpo:
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pecas WHERE UPPER(TRIM(rfid_uid)) = ?", (uid_limpo,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def verificar_disponibilidade_rfid_peca(rfid_uid: str, ignorar_peca_id: Optional[int] = None) -> Tuple[bool, str]:
    """
    Verifica se a tag RFID pode ser associada a uma peça:
    Cada RFID só pode estar linkado a exatamente uma única peça (e não pode pertencer a crachá de funcionário).
    """
    uid_limpo = formatar_rfid_uid(rfid_uid)
    if not uid_limpo:
        return True, ""

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if ignorar_peca_id is not None:
        cursor.execute(
            "SELECT id, nome FROM pecas WHERE UPPER(TRIM(rfid_uid)) = ? AND id != ?",
            (uid_limpo, ignorar_peca_id),
        )
    else:
        cursor.execute(
            "SELECT id, nome FROM pecas WHERE UPPER(TRIM(rfid_uid)) = ?",
            (uid_limpo,),
        )
    row_p = cursor.fetchone()
    if row_p:
        conn.close()
        return False, f"Tag RFID '{uid_limpo}' já está vinculada à peça '{row_p['nome']}' (#{row_p['id']})! Cada RFID só pode ser linkado a uma única peça."

    cursor.execute(
        "SELECT id, nome FROM usuarios WHERE UPPER(TRIM(rfid_uid)) = ?",
        (uid_limpo,),
    )
    row_u = cursor.fetchone()
    conn.close()
    if row_u:
        return False, f"Tag RFID '{uid_limpo}' já está vinculada ao crachá do colaborador '{row_u['nome']}' (ID #{row_u['id']})!"

    return True, ""


def verificar_disponibilidade_rfid_usuario(rfid_uid: str, ignorar_user_id: Optional[str] = None) -> Tuple[bool, str]:
    """Verifica se a tag RFID pode ser associada a um crachá de funcionário."""
    uid_limpo = formatar_rfid_uid(rfid_uid)
    if not uid_limpo:
        return True, ""

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if ignorar_user_id is not None:
        cursor.execute(
            "SELECT id, nome FROM usuarios WHERE UPPER(TRIM(rfid_uid)) = ? AND id != ?",
            (uid_limpo, str(ignorar_user_id)),
        )
    else:
        cursor.execute(
            "SELECT id, nome FROM usuarios WHERE UPPER(TRIM(rfid_uid)) = ?",
            (uid_limpo,),
        )
    row_u = cursor.fetchone()
    if row_u:
        conn.close()
        return False, f"Tag RFID '{uid_limpo}' já está vinculada ao crachá de '{row_u['nome']}' (ID #{row_u['id']})!"

    cursor.execute(
        "SELECT id, nome FROM pecas WHERE UPPER(TRIM(rfid_uid)) = ?",
        (uid_limpo,),
    )
    row_p = cursor.fetchone()
    conn.close()
    if row_p:
        return False, f"Tag RFID '{uid_limpo}' já está vinculada à peça '{row_p['nome']}' (#{row_p['id']})! Cada RFID é exclusivo."

    return True, ""


def vincular_rfid_peca(peca_id: int, rfid_uid: str) -> Tuple[bool, str]:
    """Vincula ou atualiza o UID RFID de uma peça existente, garantindo que seja exclusivo."""
    uid_limpo = formatar_rfid_uid(rfid_uid)
    if uid_limpo:
        disponivel, msg = verificar_disponibilidade_rfid_peca(uid_limpo, ignorar_peca_id=peca_id)
        if not disponivel:
            return False, msg

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE pecas SET rfid_uid = ? WHERE id = ?", (uid_limpo, peca_id))
    conn.commit()
    conn.close()
    return True, "Tag RFID vinculada com sucesso."

def get_todas_pecas() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, e.nome AS estante_nome
        FROM pecas p
        LEFT JOIN estantes e ON p.estante_id = e.id
        ORDER BY p.nome ASC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def cadastrar_peca_catalogo(
    nome: str,
    tipo: str,
    peso_unitario_g: float,
    dimensoes: str = "Padrão",
    rfid_uid: str = "",
    descricao: str = "",
) -> int:
    """Cadastra uma nova peça na lista/catálogo mestre de peças (sem vínculo obrigatório com gaveta)."""
    nome_limpo = (nome or "").strip()
    if not nome_limpo:
        raise ValueError("O nome da peça não pode ser vazio.")
    if peso_unitario_g <= 0:
        raise ValueError("O peso unitário deve ser maior que zero.")

    uid_limpo = formatar_rfid_uid(rfid_uid)
    if uid_limpo:
        disponivel, msg = verificar_disponibilidade_rfid_peca(uid_limpo)
        if not disponivel:
            raise ValueError(msg)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(id) FROM pecas")
    max_id = cursor.fetchone()[0] or 100
    novo_id = max(max_id + 1, 101)

    cursor.execute('''
        INSERT INTO pecas (id, nome, tipo, posicao_linha, posicao_coluna, peso_unitario_g, dimensoes, descricao, quantidade_estoque, estante_id, rfid_uid)
        VALUES (?, ?, ?, -1, -1, ?, ?, ?, 0, NULL, ?)
    ''', (novo_id, nome_limpo, tipo, peso_unitario_g, dimensoes or "Padrão", descricao or "", uid_limpo))
    conn.commit()
    conn.close()
    return novo_id

def alocar_peca_na_estante(
    peca_id: int,
    estante_id: int,
    posicao_linha: int,
    posicao_coluna: int,
    quantidade_inicial: int = 10,
) -> None:
    """Vincula uma peça cadastrada do catálogo a uma gaveta específica de uma estante."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Se outra peça estiver nesta mesma gaveta desta estante, desaloca ela para liberar o slot
    cursor.execute('''
        UPDATE pecas
        SET estante_id = NULL, posicao_linha = -1, posicao_coluna = -1
        WHERE estante_id = ? AND posicao_linha = ? AND posicao_coluna = ? AND id != ?
    ''', (estante_id, posicao_linha, posicao_coluna, peca_id))

    cursor.execute('''
        UPDATE pecas
        SET estante_id = ?, posicao_linha = ?, posicao_coluna = ?, quantidade_estoque = ?
        WHERE id = ?
    ''', (estante_id, posicao_linha, posicao_coluna, max(0, quantidade_inicial), peca_id))
    conn.commit()
    conn.close()

def desalocar_peca_da_estante(peca_id: int) -> Tuple[bool, str]:
    """
    Remove a peça da gaveta física da estante (liberando a gaveta),
    mas mantém o cadastro da peça no catálogo geral do sistema.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM itens_ordem_servico ios
        JOIN ordens_servico os ON ios.ordem_id = os.id
        WHERE ios.peca_id = ? AND os.status = 'ABERTA'
    ''', (peca_id,))
    em_os_aberta = cursor.fetchone()[0]
    if em_os_aberta > 0:
        conn.close()
        return False, "Esta peça está vinculada a uma Ordem de Serviço aberta e a gaveta não pode ser desocupada agora."

    cursor.execute('''
        UPDATE pecas
        SET estante_id = NULL, posicao_linha = -1, posicao_coluna = -1, quantidade_estoque = 0
        WHERE id = ?
    ''', (peca_id,))
    conn.commit()
    conn.close()
    return True, "Gaveta desocupada com sucesso! A peça permanece cadastrada no catálogo."

def upsert_peca(peca_data: Dict[str, Any]) -> None:
    peca_id = peca_data['id']
    descricao = peca_data.get('descricao', '')
    estante_id = peca_data.get('estante_id')
    rfid_uid = formatar_rfid_uid(peca_data.get('rfid_uid', ''))

    if rfid_uid:
        disponivel, msg = verificar_disponibilidade_rfid_peca(rfid_uid, ignorar_peca_id=peca_id)
        if not disponivel:
            raise ValueError(msg)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM pecas WHERE id = ?", (peca_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute('''
        UPDATE pecas SET
            nome = ?,
            tipo = ?,
            posicao_linha = ?,
            posicao_coluna = ?,
            peso_unitario_g = ?,
            dimensoes = ?,
            descricao = ?,
            estante_id = ?,
            rfid_uid = ?
        WHERE id = ?
        ''', (
            peca_data.get('nome', 'Desconhecido'),
            peca_data.get('tipo', 'Outro'),
            peca_data.get('posicao_linha', -1),
            peca_data.get('posicao_coluna', -1),
            peca_data['peso_unitario_g'],
            peca_data.get('dimensoes', 'Padrão'),
            descricao,
            estante_id,
            rfid_uid,
            peca_data['id']
        ))
    else:
        cursor.execute('''
        INSERT INTO pecas (id, nome, tipo, posicao_linha, posicao_coluna, peso_unitario_g, dimensoes, descricao, quantidade_estoque, estante_id, rfid_uid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        ''', (
            peca_data['id'],
            peca_data.get('nome', 'Desconhecido'),
            peca_data.get('tipo', 'Outro'),
            peca_data.get('posicao_linha', -1),
            peca_data.get('posicao_coluna', -1),
            peca_data['peso_unitario_g'],
            peca_data.get('dimensoes', 'Padrão'),
            descricao,
            estante_id,
            rfid_uid
        ))
    conn.commit()
    conn.close()


def excluir_peca(peca_id: int) -> Tuple[bool, str]:
    """Remove uma peça do estoque caso não esteja vinculada a uma O.S. aberta."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM itens_ordem_servico ios
        JOIN ordens_servico os ON ios.ordem_id = os.id
        WHERE ios.peca_id = ? AND os.status = 'ABERTA'
    ''', (peca_id,))
    em_os_aberta = cursor.fetchone()[0]
    if em_os_aberta > 0:
        conn.close()
        return False, "Esta peça está vinculada a uma Ordem de Serviço aberta e não pode ser excluída agora."
    cursor.execute("DELETE FROM pecas WHERE id = ?", (peca_id,))
    conn.commit()
    conn.close()
    return True, "Peça removida com sucesso."


def update_estoque(peca_id: int, quantidade_alteracao: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT quantidade_estoque FROM pecas WHERE id = ?", (peca_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        raise ValueError(f"Peça com ID {peca_id} não encontrada.")
        
    nova_qtd = result[0] + quantidade_alteracao
    if nova_qtd < 0:
        conn.close()
        raise ValueError("Quantidade em estoque não pode ser negativa.")
        
    cursor.execute("UPDATE pecas SET quantidade_estoque = ? WHERE id = ?", (nova_qtd, peca_id))
    conn.commit()
    conn.close()
    return nova_qtd

def registrar_operacao(
    funcionario_id: str,
    peca_id: int,
    tipo_operacao: str,
    quantidade: int,
    ordem_id: Optional[int] = None,
    qtd_planejada: int = 0
) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    data_hora_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
    INSERT INTO historico_operacoes (funcionario_id, peca_id, tipo_operacao, quantidade, data_hora, ordem_id, qtd_planejada)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (funcionario_id, peca_id, tipo_operacao, quantidade, data_hora_atual, ordem_id, qtd_planejada))
    conn.commit()
    conn.close()

def formatar_rfid_uid(rfid_uid: str) -> str:
    """Normaliza o formato da tag RFID para HEX maiúsculo separado por espaços (Ex: 'C4 AE 78 E5')."""
    if not rfid_uid:
        return ""
    limpo = "".join(ch for ch in rfid_uid.upper() if ch in "0123456789ABCDEF")
    if len(limpo) >= 4 and len(limpo) % 2 == 0:
        return " ".join(limpo[i:i+2] for i in range(0, len(limpo), 2))
    return " ".join(rfid_uid.strip().upper().split())

def _enriquecer_usuario_com_banco_funcionarios(u_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Busca foto_blob, foto_path, foto_nome e rfid_uid no banco dedicado funcionarios.db."""
    uid = str(u_dict.get("id", "")).strip()
    if not uid:
        return u_dict
    func_db = _get_func_db_path()
    if not os.path.exists(func_db):
        return u_dict
    try:
        conn_f = sqlite3.connect(func_db)
        conn_f.row_factory = sqlite3.Row
        cur_f = conn_f.cursor()
        cur_f.execute("SELECT * FROM funcionarios WHERE id = ?", (uid,))
        f_row = cur_f.fetchone()
        conn_f.close()
        if f_row:
            f_dict = dict(f_row)
            if f_dict.get("foto_blob"):
                u_dict["foto_blob"] = f_dict["foto_blob"]
            if f_dict.get("foto_path"):
                u_dict["foto_path"] = f_dict["foto_path"]
            if f_dict.get("foto_nome"):
                u_dict["foto_nome"] = f_dict["foto_nome"]
            if f_dict.get("rfid_uid") and not u_dict.get("rfid_uid"):
                u_dict["rfid_uid"] = f_dict["rfid_uid"]
    except Exception:
        pass
    return u_dict


def get_usuario(user_id: str) -> Optional[Dict[str, Any]]:
    """Busca um usuário pelo ID ou pela Tag RFID (permite digitar ou passar o crachá no login)."""
    termo = str(user_id or "").strip()
    if not termo:
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (termo,))
    row = cursor.fetchone()
    if not row:
        uid_fmt = formatar_rfid_uid(termo)
        if uid_fmt:
            cursor.execute("SELECT * FROM usuarios WHERE UPPER(TRIM(rfid_uid)) = ?", (uid_fmt,))
            row = cursor.fetchone()
    conn.close()
    if row:
        return _enriquecer_usuario_com_banco_funcionarios(dict(row))
    return None

def get_usuario_por_rfid(rfid_uid: str) -> Optional[Dict[str, Any]]:
    """Busca um usuário (ADMIN ou OPERARIO) vinculado ao UID da tag RFID."""
    uid_fmt = formatar_rfid_uid(rfid_uid)
    if not uid_fmt:
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE UPPER(TRIM(rfid_uid)) = ?", (uid_fmt,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return _enriquecer_usuario_com_banco_funcionarios(dict(row))
    return None

def upsert_usuario(
    user_id: str,
    nome: str,
    role: str,
    rfid_uid: Optional[str] = None,
    foto_path: Optional[str] = None,
    foto_blob: Optional[bytes] = None,
    foto_nome: Optional[str] = None,
) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    uid_limpo = formatar_rfid_uid(rfid_uid) if rfid_uid is not None else None
    if uid_limpo:
        disponivel, msg = verificar_disponibilidade_rfid_usuario(uid_limpo, ignorar_user_id=user_id)
        if not disponivel:
            conn.close()
            raise ValueError(msg)

    cursor.execute("SELECT id, rfid_uid, foto_path FROM usuarios WHERE id = ?", (user_id,))
    existente = cursor.fetchone()
    if existente:
        uid_final = uid_limpo if uid_limpo is not None else (existente[1] or "")
        foto_final = foto_path.strip() if foto_path is not None else (existente[2] or "")
        cursor.execute(
            "UPDATE usuarios SET nome = ?, role = ?, rfid_uid = ?, foto_path = ? WHERE id = ?",
            (nome, role, uid_final, foto_final, user_id)
        )
    else:
        uid_final = uid_limpo or ""
        foto_final = (foto_path or "").strip()
        cursor.execute(
            "INSERT INTO usuarios (id, nome, role, rfid_uid, foto_path) VALUES (?, ?, ?, ?, ?)",
            (user_id, nome, role, uid_final, foto_final)
        )
    conn.commit()
    conn.close()

    # Grava também no banco de dados dedicado de funcionários (funcionarios.db) com os bytes da imagem (foto_blob)
    try:
        _init_and_sync_funcionarios_db()
        func_db = _get_func_db_path()
        conn_f = sqlite3.connect(func_db)
        conn_f.row_factory = sqlite3.Row
        cur_f = conn_f.cursor()

        if uid_limpo:
            cur_f.execute(
                "UPDATE funcionarios SET rfid_uid = '' WHERE UPPER(TRIM(rfid_uid)) = ? AND id != ?",
                (uid_limpo, user_id),
            )

        blob_final = foto_blob
        nome_arq_final = foto_nome or ""
        if blob_final is None and foto_final and os.path.isfile(foto_final):
            try:
                with open(foto_final, "rb") as f:
                    blob_final = f.read()
                if not nome_arq_final:
                    nome_arq_final = os.path.basename(foto_final)
            except Exception:
                pass

        cur_f.execute("SELECT * FROM funcionarios WHERE id = ?", (user_id,))
        f_exist = cur_f.fetchone()
        if f_exist:
            if foto_path is not None and foto_path.strip() == "" and foto_blob is None:
                # Foto explicitamente removida
                blob_db = None
                nome_db = ""
            else:
                blob_db = blob_final if blob_final is not None else f_exist["foto_blob"]
                nome_db = nome_arq_final if nome_arq_final else (f_exist["foto_nome"] or "")
            cur_f.execute(
                '''
                UPDATE funcionarios
                SET nome = ?, role = ?, rfid_uid = ?, foto_path = ?, foto_nome = ?, foto_blob = ?, atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (nome, role, uid_final, foto_final, nome_db, blob_db, user_id),
            )
        else:
            cur_f.execute(
                '''
                INSERT INTO funcionarios (id, nome, role, rfid_uid, foto_path, foto_nome, foto_blob, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''',
                (user_id, nome, role, uid_final, foto_final, nome_arq_final, blob_final),
            )
        conn_f.commit()
        conn_f.close()
    except Exception as e:
        print(f"[DB] Aviso ao sincronizar funcionarios.db: {e}")

def criar_ordem_servico(
    titulo: str,
    itens: List[Dict[str, Any]],
    operador_id: Optional[str] = None,
    estante_id: int = 1,
    prazo_limite: Optional[str] = None
) -> int:
    """Cria uma nova ordem de serviço e seus itens na estante selecionada, retornando o ID da ordem."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    agora = datetime.now()
    data_criacao = agora.strftime("%Y-%m-%d %H:%M:%S")
    if not prazo_limite:
        prazo_limite = (agora + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        
    cursor.execute('''
    INSERT INTO ordens_servico (titulo, status, operador_id, estante_id, data_criacao, prazo_limite)
    VALUES (?, 'ABERTA', ?, ?, ?, ?)
    ''', (titulo, operador_id, estante_id, data_criacao, prazo_limite))
    ordem_id = cursor.lastrowid
    
    for item in itens:
        cursor.execute('''
        INSERT INTO itens_ordem_servico (ordem_id, peca_id, tipo_operacao, quantidade, quantidade_atendida)
        VALUES (?, ?, ?, ?, 0)
        ''', (ordem_id, item['peca_id'], item['tipo_operacao'], item['quantidade']))
        
    conn.commit()
    conn.close()
    return ordem_id

def get_ordens_servico_abertas(operador_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if operador_id:
        cursor.execute("SELECT * FROM ordens_servico WHERE status = 'ABERTA' AND (operador_id = ? OR operador_id IS NULL)", (operador_id,))
    else:
        cursor.execute("SELECT * FROM ordens_servico WHERE status = 'ABERTA'")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_todas_ordens_servico() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ordens_servico ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_itens_ordem_servico(ordem_id: int) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM itens_ordem_servico WHERE ordem_id = ?", (ordem_id,))
    rows = cursor.fetchall()
    conn.close()
    itens = []
    for row in rows:
        d = dict(row)
        d['quantidade_atendida'] = d.get('quantidade_atendida', 0)
        d['quantidade_restante'] = max(0, d['quantidade'] - d['quantidade_atendida'])
        itens.append(d)
    return itens

def atualizar_progresso_item_os(item_id: int, quantidade_feita: int) -> None:
    """Incrementa a quantidade já atendida de um item específico de uma Ordem de Serviço."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE itens_ordem_servico 
    SET quantidade_atendida = quantidade_atendida + ? 
    WHERE id = ?
    ''', (quantidade_feita, item_id))
    conn.commit()
    conn.close()

def calcular_status_os(ordem: Dict[str, Any], itens: List[Dict[str, Any]]) -> str:
    """
    Calcula o status auditado de uma Ordem de Serviço com base no progresso real dos itens e prazo.
    Retorna: 'CUMPRIDA', 'CUMPRIDA_ATRASO', 'INCOMPLETA', 'NAO_CUMPRIDA', 'EM_ANDAMENTO', 'ATRASADA' ou 'ABERTA'.
    """
    status_db = ordem.get('status', 'ABERTA')
    prazo_str = ordem.get('prazo_limite')
    prazo = None
    if prazo_str:
        try:
            prazo = datetime.strptime(prazo_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            prazo = None

    conclusao_str = ordem.get('data_conclusao')
    data_conclusao = None
    if conclusao_str:
        try:
            data_conclusao = datetime.strptime(conclusao_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            data_conclusao = None

    total_planejado = sum(i['quantidade'] for i in itens)
    total_atendido = sum(i.get('quantidade_atendida', 0) for i in itens)

    if status_db in ['CUMPRIDA', 'INCOMPLETA', 'NAO_CUMPRIDA', 'CONCLUIDA']:
        atrasou = (prazo and data_conclusao and data_conclusao > prazo)
        if total_atendido >= total_planejado and total_planejado > 0:
            return 'CUMPRIDA_ATRASO' if atrasou else 'CUMPRIDA'
        elif total_atendido > 0:
            return 'INCOMPLETA'
        else:
            return 'NAO_CUMPRIDA'

    agora = datetime.now()
    vencida = (prazo and agora > prazo)
    if total_atendido >= total_planejado and total_planejado > 0:
        return 'CUMPRIDA'
    if vencida:
        return 'INCOMPLETA' if total_atendido > 0 else 'NAO_CUMPRIDA'
    if total_atendido > 0:
        return 'EM_ANDAMENTO'
    return 'ABERTA'

def concluir_ordem_servico(ordem_id: int) -> str:
    """
    Finaliza a Ordem de Serviço calculando automaticamente se foi CUMPRIDA, INCOMPLETA ou NAO_CUMPRIDA.
    Retorna o status final gravado.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM itens_ordem_servico WHERE ordem_id = ?", (ordem_id,))
    itens = [dict(r) for r in cursor.fetchall()]
    
    total_planejado = sum(i['quantidade'] for i in itens)
    total_atendido = sum(i.get('quantidade_atendida', 0) for i in itens)
    
    if total_planejado > 0 and total_atendido >= total_planejado:
        novo_status = 'CONCLUIDA'
    elif total_atendido > 0:
        novo_status = 'INCOMPLETA'
    else:
        novo_status = 'NAO_CUMPRIDA'
        
    data_conclusao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
    UPDATE ordens_servico 
    SET status = ?, data_conclusao = ? 
    WHERE id = ?
    ''', (novo_status, data_conclusao, ordem_id))
    
    conn.commit()
    conn.close()
    return novo_status

def reiniciar_ordem_servico(ordem_id: int) -> None:
    """Reseta o progresso de uma ordem de serviço para permitir novos testes."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE itens_ordem_servico SET quantidade_atendida = 0 WHERE ordem_id = ?", (ordem_id,))
    cursor.execute("UPDATE ordens_servico SET status = 'ABERTA' WHERE id = ?", (ordem_id,))
    conn.commit()
    conn.close()

def get_kpis() -> Dict[str, int]:
    """Retorna indicadores-chave do armazém para o painel de supervisão."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE role = 'OPERARIO'")
    total_operadores = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pecas")
    total_pecas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM ordens_servico WHERE status = 'ABERTA'")
    ordens_abertas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM ordens_servico WHERE status IN ('CONCLUIDA', 'CUMPRIDA', 'INCOMPLETA', 'NAO_CUMPRIDA')")
    ordens_concluidas = cursor.fetchone()[0]
    
    conn.close()
    return {
        'total_operadores': total_operadores,
        'total_pecas': total_pecas,
        'ordens_abertas': ordens_abertas,
        'ordens_concluidas': ordens_concluidas
    }

def get_diario_movimentacoes(filtros: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = '''
    SELECT 
        h.id, h.data_hora, h.tipo_operacao, h.quantidade, h.qtd_planejada,
        h.funcionario_id, u.nome AS funcionario_nome,
        h.peca_id, p.nome AS peca_nome, p.tipo AS peca_tipo,
        h.ordem_id, os.titulo AS ordem_titulo, os.status AS ordem_status,
        os.prazo_limite AS ordem_prazo
    FROM historico_operacoes h
    LEFT JOIN usuarios u ON h.funcionario_id = u.id
    LEFT JOIN pecas p ON h.peca_id = p.id
    LEFT JOIN ordens_servico os ON h.ordem_id = os.id
    WHERE 1=1
    '''
    params = []
    if filtros:
        if filtros.get('funcionario_id') and filtros['funcionario_id'] != 'TODOS':
            query += " AND h.funcionario_id = ?"
            params.append(filtros['funcionario_id'])
        if filtros.get('tipo_operacao') and filtros['tipo_operacao'] != 'TODAS':
            query += " AND h.tipo_operacao = ?"
            params.append(filtros['tipo_operacao'])
        if filtros.get('ordem_id'):
            query += " AND h.ordem_id = ?"
            params.append(filtros['ordem_id'])
        if filtros.get('busca'):
            termo = f"%{filtros['busca']}%"
            query += " AND (p.nome LIKE ? OR os.titulo LIKE ? OR u.nome LIKE ? OR CAST(h.peca_id AS TEXT) LIKE ?)"
            params.extend([termo, termo, termo, termo])
            
    query += " ORDER BY h.data_hora DESC, h.id DESC"
    cursor.execute(query, tuple(params))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_auditoria_ordens_servico(filtros: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    ordens = get_todas_ordens_servico()
    resultado = []
    for o in ordens:
        itens = get_itens_ordem_servico(o['id'])
        status_calc = calcular_status_os(o, itens)
        o_dict = dict(o)
        o_dict['status_calculado'] = status_calc
        o_dict['itens'] = itens
        o_dict['total_itens'] = len(itens)
        o_dict['total_planejado'] = sum(i['quantidade'] for i in itens)
        o_dict['total_atendido'] = sum(i.get('quantidade_atendida', 0) for i in itens)
        
        if filtros:
            if filtros.get('status') and filtros['status'] != 'TODOS':
                st_filtro = filtros['status'].upper()
                if st_filtro not in status_calc.upper():
                    continue
            if filtros.get('operador_id') and filtros['operador_id'] != 'TODOS':
                if str(o.get('operador_id')) != str(filtros['operador_id']):
                    continue
            if filtros.get('busca'):
                termo = filtros['busca'].lower()
                tit = (o.get('titulo') or '').lower()
                if termo not in tit and str(o['id']) != termo:
                    continue
                
        resultado.append(o_dict)
    return resultado

def get_detalhes_conciliacao_os(ordem_id: int) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ordens_servico WHERE id = ?", (ordem_id,))
    ordem_row = cursor.fetchone()
    if not ordem_row:
        conn.close()
        raise ValueError(f"O.S. {ordem_id} não encontrada.")
    ordem = dict(ordem_row)
    conn.close()
    
    itens = get_itens_ordem_servico(ordem_id)
    ordem['status_calculado'] = calcular_status_os(ordem, itens)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT h.*, u.nome AS operador_nome, p.nome AS peca_nome, p.posicao_linha, p.posicao_coluna
    FROM historico_operacoes h
    LEFT JOIN usuarios u ON h.funcionario_id = u.id
    LEFT JOIN pecas p ON h.peca_id = p.id
    WHERE h.ordem_id = ?
    ORDER BY h.data_hora ASC
    ''', (ordem_id,))
    movimentacoes = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    return {
        'ordem': ordem,
        'itens_planejados': itens,
        'movimentacoes_realizadas': movimentacoes
    }

def obter_diretorio_exportacoes() -> str:
    """Retorna e garante a existência da pasta de exportações de planilhas."""
    pasta_base = os.path.dirname(os.path.abspath(DB_PATH))
    pasta_export = os.path.join(pasta_base, "exportacoes")
    os.makedirs(pasta_export, exist_ok=True)
    return pasta_export

def salvar_em_armazenamento_celular(caminho_arquivo: str, pastas_customizadas: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
    """
    Tenta copiar o arquivo exportado para o armazenamento público acessível do celular Android
    (ex: pasta /storage/emulated/0/Download ou /sdcard/Download) para que apareça diretamente
    no aplicativo 'Meus Arquivos' ou 'Downloads' do smartphone.
    Retorna (True, caminho_destino) se copiado com sucesso, ou (False, None).
    """
    if not caminho_arquivo or not os.path.exists(caminho_arquivo):
        return False, None

    nome_arq = os.path.basename(caminho_arquivo)
    pastas_candidatas = pastas_customizadas or [
        "/storage/emulated/0/Download",
        "/sdcard/Download",
        "/storage/emulated/0/Documents",
        "/sdcard/Documents",
        "/storage/self/primary/Download",
    ]

    for pasta in pastas_candidatas:
        try:
            if os.path.exists(pasta) and os.path.isdir(pasta):
                destino = os.path.join(pasta, nome_arq)
                if os.path.abspath(destino) == os.path.abspath(caminho_arquivo):
                    return True, destino
                shutil.copy2(caminho_arquivo, destino)
                return True, destino
        except Exception:
            continue

    return False, None

def exportar_diario_csv(caminho_arquivo: Optional[str] = None, filtros: Optional[Dict[str, Any]] = None) -> str:
    if not caminho_arquivo:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_arquivo = os.path.join(obter_diretorio_exportacoes(), f"multilog_movimentacoes_{ts}.csv")
    diario = get_diario_movimentacoes(filtros)
    cabecalho = [
        "Data/Hora", "ID Mov.", "Tipo", "Qtd. Movimentada", "Qtd. Planejada O.S.",
        "ID Peça", "Nome Peça", "Tipo Peça",
        "ID Operador", "Nome Operador",
        "ID O.S.", "Título O.S.", "Status O.S.", "Prazo Limite O.S."
    ]
    with open(caminho_arquivo, mode='w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(cabecalho)
        for d in diario:
            writer.writerow([
                d.get('data_hora', ''),
                d.get('id', ''),
                d.get('tipo_operacao', ''),
                d.get('quantidade', ''),
                d.get('qtd_planejada', ''),
                d.get('peca_id', ''),
                d.get('peca_nome', '') or 'Peça Desconhecida',
                d.get('peca_tipo', '') or '-',
                d.get('funcionario_id', ''),
                d.get('funcionario_nome', '') or f"Operador {d.get('funcionario_id', '')}",
                d.get('ordem_id', '') or '',
                d.get('ordem_titulo', '') or '',
                d.get('ordem_status', '') or '',
                d.get('ordem_prazo', '') or ''
            ])
    salvar_em_armazenamento_celular(caminho_arquivo)
    return caminho_arquivo

def exportar_auditoria_os_csv(caminho_arquivo: Optional[str] = None, filtros: Optional[Dict[str, Any]] = None) -> str:
    if not caminho_arquivo:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_arquivo = os.path.join(obter_diretorio_exportacoes(), f"multilog_auditoria_os_{ts}.csv")
    ordens = get_auditoria_ordens_servico(filtros)
    cabecalho = [
        "ID O.S.", "Título", "Status", "Operador ID", "Nome Operador",
        "Estante ID", "Data Criação", "Prazo Limite", "Data Conclusão",
        "Total Itens Planejados", "Total Itens Atendidos"
    ]
    with open(caminho_arquivo, mode='w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(cabecalho)
        for o in ordens:
            writer.writerow([
                o.get('id', ''),
                o.get('titulo', ''),
                o.get('status_calculado', ''),
                o.get('operador_id', ''),
                o.get('operador_nome', '') or f"Operador {o.get('operador_id', '')}",
                o.get('estante_id', ''),
                o.get('data_criacao', ''),
                o.get('prazo_limite', '') or '-',
                o.get('data_conclusao', '') or '-',
                o.get('total_planejado', 0),
                o.get('total_atendido', 0)
            ])
    salvar_em_armazenamento_celular(caminho_arquivo)
    return caminho_arquivo

def exportar_extrato_gavetas_csv(caminho_arquivo: Optional[str] = None, data_str: Optional[str] = None, estante_id: int = 1) -> str:
    if not caminho_arquivo:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_arquivo = os.path.join(obter_diretorio_exportacoes(), f"multilog_extrato_gavetas_{ts}.csv")
    if not data_str:
        datas = get_datas_com_movimentacoes()
        data_str = datas[0] if datas else datetime.now().strftime("%Y-%m-%d")
    extrato = get_extrato_caixas_por_dia(data_str, estante_id=estante_id, incluir_vazias=True)
    cabecalho = [
        "Data", "Estante ID", "Posição Linha", "Posição Coluna", "Identificador Gaveta",
        "ID Peça", "Nome Peça", "Tipo Peça",
        "Entradas (+)", "Saídas (-)", "Saldo Líquido", "Total Movimentações"
    ]
    with open(caminho_arquivo, mode='w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(cabecalho)
        for e in extrato:
            writer.writerow([
                data_str,
                e.get('estante_id', estante_id),
                e.get('posicao_linha', 0) + 1,
                e.get('posicao_coluna', 0) + 1,
                e.get('identificador_gaveta', ''),
                e.get('peca_id', '') or '-',
                e.get('peca_nome', '') or 'Vazia',
                e.get('peca_tipo', '') or '-',
                e.get('total_entradas', 0),
                e.get('total_saidas', 0),
                e.get('saldo_liquido', 0),
                e.get('total_movimentacoes', 0)
            ])
    salvar_em_armazenamento_celular(caminho_arquivo)
    return caminho_arquivo

def exportar_relatorio_completo_csv(caminho_arquivo: Optional[str] = None) -> str:
    if not caminho_arquivo:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_arquivo = os.path.join(obter_diretorio_exportacoes(), f"multilog_relatorio_completo_{ts}.csv")
    with open(caminho_arquivo, mode='w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        
        # --- SEÇÃO 1: ESTOQUE ATUAL ---
        writer.writerow(["=== RELATÓRIO GERAL MULTILOG - ESTOQUE ATUAL ==="])
        writer.writerow(["Data Geração:", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow([])
        writer.writerow(["ID Peça", "Nome Peça", "Categoria", "Estante", "Posição (L·C)", "Estoque Atual (un)", "Peso Unit (g)", "RFID"])
        pecas = get_todas_pecas()
        for p in pecas:
            pos = f"L{p.get('posicao_linha', 0)+1}·C{p.get('posicao_coluna', 0)+1}" if p.get('posicao_linha', -1) >= 0 else "Fora de estante"
            writer.writerow([
                p.get('id', ''),
                p.get('nome', ''),
                p.get('tipo', ''),
                p.get('estante_nome', 'Estante'),
                pos,
                p.get('quantidade_estoque', 0),
                p.get('peso_unitario_g', 0.0),
                p.get('rfid_uid', '') or 'Sem Tag'
            ])
        writer.writerow([])
        writer.writerow([])
        
        # --- SEÇÃO 2: AUDITORIA DE ORDENS DE SERVIÇO ---
        writer.writerow(["=== AUDITORIA DE ORDENS DE SERVIÇO ==="])
        writer.writerow(["ID O.S.", "Título", "Status", "Operador", "Data Criação", "Prazo Limite", "Data Conclusão", "Itens Planejados", "Itens Atendidos"])
        ordens = get_auditoria_ordens_servico()
        for o in ordens:
            writer.writerow([
                o.get('id', ''),
                o.get('titulo', ''),
                o.get('status_calculado', ''),
                o.get('operador_nome', '') or o.get('operador_id', ''),
                o.get('data_criacao', ''),
                o.get('prazo_limite', '') or '-',
                o.get('data_conclusao', '') or '-',
                o.get('total_planejado', 0),
                o.get('total_atendido', 0)
            ])
        writer.writerow([])
        writer.writerow([])
        
        # --- SEÇÃO 3: HISTÓRICO COMPLETO DE MOVIMENTAÇÕES ---
        writer.writerow(["=== HISTÓRICO DE MOVIMENTAÇÕES ==="])
        writer.writerow(["Data/Hora", "ID Mov.", "Tipo", "Quantidade", "ID Peça", "Nome Peça", "Operador", "ID O.S.", "Título O.S."])
        diario = get_diario_movimentacoes()
        for d in diario:
            writer.writerow([
                d.get('data_hora', ''),
                d.get('id', ''),
                d.get('tipo_operacao', ''),
                d.get('quantidade', ''),
                d.get('peca_id', ''),
                d.get('peca_nome', '') or 'Peça Desconhecida',
                d.get('funcionario_nome', '') or d.get('funcionario_id', ''),
                d.get('ordem_id', '') or '',
                d.get('ordem_titulo', '') or ''
            ])
    salvar_em_armazenamento_celular(caminho_arquivo)
    return caminho_arquivo

def get_datas_com_movimentacoes() -> List[str]:
    """Retorna lista com todas as datas (YYYY-MM-DD) com operações registradas, ordenadas de forma decrescente."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT DATE(data_hora) FROM historico_operacoes ORDER BY DATE(data_hora) DESC")
    rows = cursor.fetchall()
    conn.close()
    datas = [r[0] for r in rows if r[0]]
    hoje = datetime.now().strftime("%Y-%m-%d")
    if hoje not in datas:
        datas.insert(0, hoje)
    return datas

def get_extrato_caixas_por_dia(data_str: str, estante_id: int = 1, incluir_vazias: bool = False) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT linhas, colunas, nome FROM estantes WHERE id = ?", (estante_id,))
    estante_row = cursor.fetchone()
    num_linhas = estante_row['linhas'] if estante_row else 5
    num_colunas = estante_row['colunas'] if estante_row else 5
    
    cursor.execute("SELECT * FROM pecas WHERE estante_id = ? AND posicao_linha >= 0 AND posicao_coluna >= 0", (estante_id,))
    pecas_rows = cursor.fetchall()
    mapa_pecas = {(p['posicao_linha'], p['posicao_coluna']): dict(p) for p in pecas_rows}
    
    cursor.execute('''
    SELECT 
        h.id, h.data_hora, h.tipo_operacao, h.quantidade, h.qtd_planejada,
        h.funcionario_id, u.nome AS funcionario_nome,
        h.peca_id, p.nome AS peca_nome, p.tipo AS peca_tipo,
        p.posicao_linha, p.posicao_coluna, p.estante_id,
        h.ordem_id, os.titulo AS ordem_titulo
    FROM historico_operacoes h
    JOIN pecas p ON h.peca_id = p.id
    LEFT JOIN usuarios u ON h.funcionario_id = u.id
    LEFT JOIN ordens_servico os ON h.ordem_id = os.id
    WHERE DATE(h.data_hora) = ? AND p.estante_id = ?
    ORDER BY h.data_hora ASC
    ''', (data_str, estante_id))
    
    movs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    mapa_movs: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for m in movs:
        coord = (m['posicao_linha'], m['posicao_coluna'])
        mapa_movs.setdefault(coord, []).append(m)
        
    resultado = []
    
    if incluir_vazias:
        coords_para_iterar = [(r, c) for r in range(num_linhas) for c in range(num_colunas)]
    else:
        coords_para_iterar = sorted(mapa_movs.keys())
        
    for r, c in coords_para_iterar:
        eventos = mapa_movs.get((r, c), [])
        peca = mapa_pecas.get((r, c))
        
        tot_entradas = sum(e['quantidade'] for e in eventos if e['tipo_operacao'] == 'ADICAO')
        tot_saidas = sum(e['quantidade'] for e in eventos if e['tipo_operacao'] == 'REMOCAO')
        saldo = tot_entradas - tot_saidas
        
        resultado.append({
            'estante_id': estante_id,
            'posicao_linha': r,
            'posicao_coluna': c,
            'identificador_gaveta': f"Gaveta L{r+1}-C{c+1}",
            'peca_id': peca['id'] if peca else (eventos[0]['peca_id'] if eventos else None),
            'peca_nome': peca['nome'] if peca else (eventos[0]['peca_nome'] if eventos else 'Gaveta Vazia'),
            'peca_tipo': peca['tipo'] if peca else (eventos[0].get('peca_tipo') if eventos else '-'),
            'total_entradas': tot_entradas,
            'total_saidas': tot_saidas,
            'saldo_liquido': saldo,
            'total_movimentacoes': len(eventos),
            'eventos': eventos
        })
        
    return resultado


def get_usuarios_operarios() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE role = 'OPERARIO' ORDER BY nome ASC")
    rows = cursor.fetchall()
    conn.close()
    return [_enriquecer_usuario_com_banco_funcionarios(dict(r)) for r in rows]

def get_todos_usuarios() -> List[Dict[str, Any]]:
    """Retorna todos os usuários cadastrados ordenados por role (ADMIN primeiro) e nome."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios ORDER BY role ASC, nome ASC")
    rows = cursor.fetchall()
    conn.close()
    return [_enriquecer_usuario_com_banco_funcionarios(dict(r)) for r in rows]

def remover_usuario(user_id: str, current_user_id: Optional[str] = None) -> Tuple[bool, str]:
    if current_user_id and str(user_id).strip() == str(current_user_id).strip():
        return False, "Você não pode remover seu próprio usuário enquanto estiver conectado."

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return False, f"Usuário com ID '{user_id}' não encontrado."

    if user['role'] == 'ADMIN':
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE role = 'ADMIN'")
        total_admins = cursor.fetchone()[0]
        if total_admins <= 1:
            conn.close()
            return False, "Não é possível remover o único administrador do sistema."

    cursor.execute("UPDATE ordens_servico SET operador_id = NULL WHERE operador_id = ? AND status = 'ABERTA'", (user_id,))
    cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    try:
        func_db = _get_func_db_path()
        if os.path.exists(func_db):
            conn_f = sqlite3.connect(func_db)
            conn_f.execute("DELETE FROM funcionarios WHERE id = ?", (user_id,))
            conn_f.commit()
            conn_f.close()
    except Exception:
        pass

    return True, f"Usuário '{user['nome']}' (ID {user_id}) removido com sucesso."


# ==============================================================================
# GESTÃO MULTI-ESTANTES (CRUD, CONSULTAS E VALIDAÇÕES)
# ==============================================================================

def get_todas_estantes() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM estantes ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_estante(estante_id: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM estantes WHERE id = ?", (estante_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def criar_estante(nome: str, linhas: int, colunas: int, descricao: str = "") -> int:
    nome_limpo = nome.strip()
    if not nome_limpo:
        raise ValueError("O nome da estante não pode ser vazio.")
    if linhas < 1 or colunas < 1:
        raise ValueError("Dimensões da estante devem ser maiores que zero.")
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO estantes (nome, linhas, colunas, descricao)
    VALUES (?, ?, ?, ?)
    ''', (nome_limpo, linhas, colunas, descricao.strip()))
    estante_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return estante_id

def atualizar_estante(estante_id: int, nome: str, linhas: int, colunas: int, descricao: str = "") -> None:
    nome_limpo = nome.strip()
    if not nome_limpo:
        raise ValueError("O nome da estante não pode ser vazio.")
    if linhas < 1 or colunas < 1:
        raise ValueError("Dimensões da estante devem ser maiores que zero.")
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE estantes
    SET nome = ?, linhas = ?, colunas = ?, descricao = ?
    WHERE id = ?
    ''', (nome_limpo, linhas, colunas, descricao.strip(), estante_id))
    conn.commit()
    conn.close()

def validar_redimensionamento_estante(estante_id: int, novas_linhas: int, novas_colunas: int) -> Tuple[bool, List[str]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT nome, posicao_linha, posicao_coluna FROM pecas
    WHERE estante_id = ? AND posicao_linha >= 0 AND posicao_coluna >= 0 AND (posicao_linha >= ? OR posicao_coluna >= ?)
    ''', (estante_id, novas_linhas, novas_colunas))
    rows = cursor.fetchall()
    conn.close()
    
    conflitos = [f"{r['nome']} (L{r['posicao_linha']+1}-C{r['posicao_coluna']+1})" for r in rows]
    return (len(conflitos) == 0, conflitos)

def excluir_estante(estante_id: int) -> Tuple[bool, str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM estantes")
    total_estantes = cursor.fetchone()[0]
    if total_estantes <= 1:
        conn.close()
        return False, "Não é possível excluir a única estante do armazém."
        
    cursor.execute("SELECT COUNT(*) FROM pecas WHERE estante_id = ? AND posicao_linha >= 0 AND posicao_coluna >= 0", (estante_id,))
    total_pecas = cursor.fetchone()[0]
    if total_pecas > 0:
        conn.close()
        return False, f"Não é possível excluir: existem {total_pecas} peça(s) alocadas nesta estante. Esvazie as gavetas antes de excluir."
        
    cursor.execute("SELECT COUNT(*) FROM ordens_servico WHERE estante_id = ? AND status = 'ABERTA'", (estante_id,))
    total_os = cursor.fetchone()[0]
    if total_os > 0:
        conn.close()
        return False, f"Não é possível excluir: existem {total_os} Ordem(ns) de Serviço pendente(s) vinculadas a esta estante."
        
    cursor.execute("DELETE FROM estantes WHERE id = ?", (estante_id,))
    conn.commit()
    conn.close()
    return True, "Estante excluída com sucesso."

def get_pecas_por_estante(estante_id: int) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pecas WHERE estante_id = ? AND posicao_linha >= 0 AND posicao_coluna >= 0", (estante_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Inicializa o banco ao importar
init_db()
popular_dados_teste()
