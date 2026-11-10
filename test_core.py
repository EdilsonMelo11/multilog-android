import os
import sys
import time

# Garante que importa os módulos de Projeto_Android
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import logic
import hardware_manager
import hardware_mock
import main
import diary_view


class DummyWindow:
    def __init__(self):
        self.width = 0
        self.height = 0
        self.min_width = 0
        self.min_height = 0


class DummyPage:
    def __init__(self):
        self.title = ""
        self.bgcolor = ""
        self.padding = 0
        self.controls = []
        self.dialog = None
        self.snack_bar = None
        self.window = DummyWindow()

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass

    def show_dialog(self, dlg):
        self.dialog = dlg

    def pop_dialog(self):
        self.dialog = None


def test_database_funcionarios_db_e_crachas_rfid():
    estantes = database.get_todas_estantes()
    assert len(estantes) >= 1

    # Verifica banco dedicado funcionarios.db sincronizado
    func_db_path = database._get_func_db_path()
    assert os.path.exists(func_db_path)

    # Verifica usuários iniciais com crachás RFID padrão
    admin = database.get_usuario("1000")
    operador = database.get_usuario("1001")
    assert admin is not None and admin["role"] == "ADMIN"
    assert operador is not None and operador["role"] == "OPERARIO"
    assert "Operário" not in operador["nome"]  # Padronizado para Operador

    # Verifica busca por Tag RFID do crachá
    adm_rfid = database.get_usuario_por_rfid("c4:ae:78:e5")
    op_rfid = database.get_usuario_por_rfid("47 09 9E A3")
    assert adm_rfid is not None and str(adm_rfid["id"]) == "1000"
    assert op_rfid is not None and str(op_rfid["id"]) == "1001"

    # Testa gravação e recuperação de foto_blob em funcionarios.db
    fake_blob = b"\x89PNG\r\n\x1a\nTESTIMAGE"
    database.upsert_usuario(
        "9999",
        "Carlos (Operador)",
        "OPERARIO",
        rfid_uid="AA BB CC DD",
        foto_path="",
        foto_blob=fake_blob,
        foto_nome="carlos.png",
    )
    u_carlos = database.get_usuario("9999")
    assert u_carlos is not None
    assert u_carlos["rfid_uid"] == "AA BB CC DD"
    assert u_carlos.get("foto_blob") == fake_blob
    database.remover_usuario("9999", current_user_id="1000")


def test_logic_validacao_peso_e_os():
    assert logic.validar_peso(227.0, 227.0, 1) is True
    assert logic.validar_peso(235.0, 227.0, 1) is True  # Dentro de 5%
    assert logic.validar_peso(180.0, 227.0, 1) is False # Fora de 5%

    item_os = {
        "id": 1,
        "peca_id": 101,
        "tipo_operacao": "REMOCAO",
        "quantidade": 3,
        "quantidade_atendida": 1,
        "quantidade_restante": 2,
    }
    ok, msg = logic.validar_operacao_os(item_os, "REMOCAO", 2, estoque_atual=5)
    assert ok is True
    assert msg == "OK"

    ok_excesso, _ = logic.validar_operacao_os(item_os, "REMOCAO", 3, estoque_atual=5)
    assert ok_excesso is False


def test_hardware_manager_debounce_lcd_e_buzzer():
    hw = hardware_manager.HardwareManager.get_instancia()
    hw.definir_host("http://192.168.4.1/")
    assert hw.host_ativo == "192.168.4.1"

    # Reseta janela de dedup para o teste
    hw._ultimo_rfid_notificado_tag = ""
    hw._ultimo_rfid_notificado_ts = 0.0

    tags_recebidas = []
    pesos_recebidos = []
    cb_rfid = lambda t: tags_recebidas.append(t)
    cb_peso = lambda p: pesos_recebidos.append(p)
    hw.registrar_callback_rfid(cb_rfid)
    hw.registrar_callback_peso(cb_peso)

    try:
        # Simula envio simultâneo pela Serial e pelo Wi-Fi (deve disparar apenas 1 vez dentro de 2s)
        hw._notificar_rfid_recebido("11 22 33 44", origem="SERIAL")
        hw._notificar_rfid_recebido("11 22 33 44", origem="WIFI")
        assert tags_recebidas.count("11 22 33 44") == 1

        hw.simular_peso(454.0)
        assert 454.0 in pesos_recebidos
        assert hw.ler_ultimo_peso() == 454.0

        # Testa resolução de nome para o LCD 16x2 e comando de buzzer D2
        nome_lcd, achou = hw.obter_nome_item_para_lcd("C4 AE 78 E5")
        assert achou is True
        assert len(nome_lcd) <= 16

        hw.ultimo_bip_buzzer_ts = 0.0
        hardware_mock.tocar_buzzer_bip()
        cmds_bip = hw.consumir_comando_wifi()
        assert "BUZZER:BIP" in cmds_bip

        hw.ultimo_erro_buzzer_ts = 0.0
        hardware_mock.tocar_buzzer_erro()
        cmds = hw.consumir_comando_wifi()
        assert "BUZZER:ERRO" in cmds
    finally:
        hw.desregistrar_callback_rfid(cb_rfid)
        hw.desregistrar_callback_peso(cb_peso)


def test_login_por_rfid_e_bloqueio_troca_sessao():
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app._ultimo_rfid_ui_tag = ""
    app._ultimo_rfid_ui_ts = 0.0

    # 1. Estando na tela de login, aproximar o crachá do Operador (47 09 9E A3) loga automaticamente em 'ordens'
    assert app.aba_atual == "login"
    app._on_rfid_recebido("47 09 9E A3")
    assert app.funcionario_id == "1001"
    assert app.usuario_role == "OPERARIO"
    assert app.aba_atual == "ordens"

    # 2. Estando já logado como Operador 1001, aproximar o crachá do Admin (C4 AE 78 E5) NÃO troca de usuário
    # e o resolvedor do LCD informa "Saia p/ Login"
    txt_lcd = app._resolver_nome_rfid_para_lcd("C4 AE 78 E5")
    assert txt_lcd == "Saia p/ Login"
    app._on_rfid_recebido("C4 AE 78 E5")
    assert app.funcionario_id == "1001"  # Permanece no Operador 1001!

    # 3. Após clicar em Sair (fazer_logout), aproximar o crachá do Admin loga como ADMIN
    app.fazer_logout()
    assert app.aba_atual == "login"
    app._ultimo_rfid_ui_tag = ""
    app._ultimo_rfid_ui_ts = 0.0
    app._on_rfid_recebido("C4 AE 78 E5")
    assert app.funcionario_id == "1000"
    assert app.usuario_role == "ADMIN"
    assert app.aba_atual == "admin"


def test_operador_estante_modo_os_passo1_rfid_e_piscando():
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app.funcionario_id = "1001"
    app.usuario_role = "OPERARIO"

    # Garante que a peça 101 existe na Estante 1 (L0, C0)
    peca_101 = database.get_peca(101)
    assert peca_101 is not None

    oid = database.criar_ordem_servico(
        "OS Teste Passo 1 RFID e Estante Piscando",
        [{"peca_id": 101, "tipo_operacao": "REMOCAO", "quantidade": 1}],
        operador_id="1001",
        estante_id=peca_101.get("estante_id", 1),
    )
    ordens = database.get_ordens_servico_abertas("1001")
    os_criada = next(o for o in ordens if o["id"] == oid)

    # Inicia a O.S.: Passo 1 (RFID) deve iniciar pendente (rfid_os_validado == False)
    app.iniciar_execucao_os(os_criada)
    assert app.os_ativa is not None
    assert app.item_os_selecionado is not None
    assert app.rfid_os_obrigatorio is True
    assert app.rfid_os_validado is False
    assert app.slot_ativo_os == (peca_101["posicao_linha"], peca_101["posicao_coluna"])

    # Simula leitura da tag RFID da peça ativa (Passo 1) -> libera Passo 2
    app.simular_leitura_rfid_item_os_ativo()
    assert app.rfid_os_validado is True

    # Navega para a aba Estante durante a O.S.
    app.navegar("estoque")
    assert app.esta_em_modo_os_estante() is True

    # Tentar clicar em outra gaveta que não pertence à O.S. (ex: L4, C4) deve ser bloqueado
    permitido = app.tentar_selecionar_gaveta_estante(4, 4)
    assert permitido is False
    assert app.slot_ativo_os == (peca_101["posicao_linha"], peca_101["posicao_coluna"])

    # Passo de pisca-pisca alterna o estado visual
    estado_antes = app.blink_state
    app._executar_passo_pisca()
    assert app.blink_state != estado_antes

    database.concluir_ordem_servico(oid)
    # Limpa a O.S. temporária do teste
    conn = database.sqlite3.connect(database.DB_PATH)
    conn.execute("DELETE FROM itens_ordem_servico WHERE ordem_id = ?", (oid,))
    conn.execute("DELETE FROM ordens_servico WHERE id = ?", (oid,))
    conn.commit()
    conn.close()


def test_ui_builders_flet_e_formato_vertical_samsung_galaxy_s22():
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)

    # Verifica proporção exata 19.5:9 do Samsung Galaxy S22 na vertical (1080x2340 nativo / 360x780 dp)
    assert dummy_page.window.width == 360
    assert dummy_page.window.height == 780
    assert round(dummy_page.window.height / dummy_page.window.width, 4) == round(19.5 / 9, 4)

    # Verifica todas as telas principais
    for tela in ["login", "estoque", "ordens", "admin", "usuarios", "diario"]:
        app.funcionario_id = "1000"
        app.usuario_role = "ADMIN"
        app.navegar(tela)
        assert app.container_principal.content is not None


test_ui_builders_flet_e_formato_vertical_20_por_9 = test_ui_builders_flet_e_formato_vertical_samsung_galaxy_s22


def test_ordenacao_e_agrupamento_os():
    amostra_ordens = [
        {"id": 1, "titulo": "B - Separação Parafusos", "data_criacao": "2026-11-01 08:00:00"},
        {"id": 2, "titulo": "A - Reposição Arruelas", "data_criacao": "2026-11-01 10:00:00"},
        {"id": 3, "titulo": "C - Kit Manutenção", "data_criacao": "2026-11-01 12:00:00"},
    ]

    rec = logic.ordenar_ordens_servico(amostra_ordens, "RECENTE")
    assert [o["id"] for o in rec] == [3, 2, 1]

    ant = logic.ordenar_ordens_servico(amostra_ordens, "ANTIGA")
    assert [o["id"] for o in ant] == [1, 2, 3]

    az = logic.ordenar_ordens_servico(amostra_ordens, "AZ")
    assert [o["titulo"][0] for o in az] == ["A", "B", "C"]

    za = logic.ordenar_ordens_servico(amostra_ordens, "ZA")
    assert [o["titulo"][0] for o in za] == ["C", "B", "A"]

    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app.funcionario_id = "1001"
    app.usuario_role = "OPERARIO"
    app.navegar("ordens")
    for crit in ["RECENTE", "ANTIGA", "AZ", "ZA"]:
        app.definir_ordenacao_os(crit)
        assert app.ordenacao_os == crit
        assert app.container_principal.content is not None


def test_selecionar_foto_perfil_do_celular():
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app.funcionario_id = "1000"
    app.usuario_role = "ADMIN"
    app.navegar("usuarios")

    assert app.callback_foto_dispositivo is not None

    class DummyPickedFile:
        def __init__(self):
            self.name = "foto_galeria_celular.jpg"
            self.path = ""
            self.bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF_FAKE_MOBILE_PHOTO"

    class DummyPickerEvent:
        def __init__(self):
            self.files = [DummyPickedFile()]

    app._on_file_picker_result(DummyPickerEvent())
    assert app.page.snack_bar is not None or app.page.dialog is not None


def test_admin_troca_estante_layout_dinamico():
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app.funcionario_id = "1000"
    app.usuario_role = "ADMIN"
    app.navegar("estoque")

    estantes = database.get_todas_estantes()
    temp_id = None
    if len(estantes) < 2:
        temp_id = database.criar_estante("Estante Auxiliar Teste", 3, 2, "Teste layout")
        estantes = database.get_todas_estantes()

    try:
        assert len(estantes) >= 2
        for est in estantes:
            app.selecionar_estante(est["id"])
            assert app.estante_ativa_id == est["id"]
            col_tela = app.container_principal.content
            card_matriz = col_tela.controls[1]
            matriz_col = card_matriz.content.controls[1]
            assert len(matriz_col.controls) == int(est["linhas"])
            assert len(matriz_col.controls[0].controls) == int(est["colunas"])
    finally:
        if temp_id:
            database.excluir_estante(temp_id)


def test_confirmacao_exclusao_estante_fecha_popup():
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app.funcionario_id = "1000"
    app.usuario_role = "ADMIN"

    novo_id = database.criar_estante("Estante Temp Teste", 2, 2, "Teste exclusao")
    app.selecionar_estante(novo_id)

    # 1. Abre o popup de Configurar Estante
    app.abrir_modal_estante(editar=True)
    dlg_cfg = dummy_page.dialog
    assert dlg_cfg is not None
    assert "Configurar Estante" in dlg_cfg.title.value

    # 2. Clica em '🗑️ Excluir' -> deve fechar o popup de configuração e abrir o popup de confirmação
    btn_excluir = dlg_cfg.actions[1]
    btn_excluir.on_click(None)
    assert dlg_cfg.open is False
    dlg_conf = dummy_page.dialog
    assert dlg_conf is not None and dlg_conf is not dlg_cfg
    assert "Excluir Estante" in dlg_conf.title.value

    # 3. Clica em '🗑️ Confirmar' -> deve fechar o popup de confirmação e excluir a estante
    btn_confirmar = dlg_conf.actions[1]
    btn_confirmar.on_click(None)
    assert dlg_conf.open is False
    assert database.get_estante(novo_id) is None


def test_catalogo_pecas_adicao_remocao_e_alocacao_gavetas():
    """
    Testa a separação entre o catálogo mestre de peças e a alocação física nas estantes:
    1. Cadastrar nova peça no catálogo sem vínculo de gaveta
    2. Alocar a peça em uma gaveta física da estante
    3. Desocupar a gaveta (libera o slot na estante mantendo a peça no catálogo)
    4. Remover a peça definitivamente da lista do catálogo
    """
    # 1. Cadastra peça no catálogo
    p_id = database.cadastrar_peca_catalogo(
        nome="Sensor Ultrassônico HC-SR04",
        tipo="Eletrônica",
        peso_unitario_g=8.5,
        dimensoes="45x20mm",
        rfid_uid="11 22 33 44",
        descricao="Sensor de teste",
    )
    assert p_id > 0
    p = database.get_peca(p_id)
    assert p is not None
    assert p["nome"] == "Sensor Ultrassônico HC-SR04"
    assert p["posicao_linha"] == -1
    assert p["posicao_coluna"] == -1
    assert p["estante_id"] is None
    assert p["quantidade_estoque"] == 0

    # Verifica presença no catálogo geral e ausência na estante 1
    todas = database.get_todas_pecas()
    assert any(x["id"] == p_id for x in todas)
    pecas_estante1 = database.get_pecas_por_estante(1)
    assert not any(x["id"] == p_id for x in pecas_estante1)

    # 2. Aloca a peça na gaveta L1·C1 (linha 0, coluna 0) da estante 1
    database.alocar_peca_na_estante(p_id, estante_id=1, posicao_linha=0, posicao_coluna=0, quantidade_inicial=25)
    p_alocada = database.get_peca(p_id)
    assert p_alocada["estante_id"] == 1
    assert p_alocada["posicao_linha"] == 0
    assert p_alocada["posicao_coluna"] == 0
    assert p_alocada["quantidade_estoque"] == 25
    pecas_estante1_apos = database.get_pecas_por_estante(1)
    assert any(x["id"] == p_id for x in pecas_estante1_apos)

    # 3. Desocupa a gaveta (a peça permanece no catálogo, mas sai da estante)
    ok_des, msg_des = database.desalocar_peca_da_estante(p_id)
    assert ok_des is True
    p_desalocada = database.get_peca(p_id)
    assert p_desalocada["estante_id"] is None
    assert p_desalocada["posicao_linha"] == -1
    assert p_desalocada["posicao_coluna"] == -1
    assert not any(x["id"] == p_id for x in database.get_pecas_por_estante(1))
    assert any(x["id"] == p_id for x in database.get_todas_pecas())

    # 4. Remove a peça definitivamente da lista do catálogo
    ok_del, msg_del = database.excluir_peca(p_id)
    assert ok_del is True
    assert database.get_peca(p_id) is None
    assert not any(x["id"] == p_id for x in database.get_todas_pecas())

    # Restaura peça 101 na gaveta (0, 0) para os próximos testes
    database.alocar_peca_na_estante(101, estante_id=1, posicao_linha=0, posicao_coluna=0, quantidade_inicial=50)


def test_ui_secao_catalogo_pecas_e_desocupar_gaveta():
    """
    Testa a interface Flet:
    - Seção 'Peças Cadastradas' visível na tela de estantes do Admin
    - Modal de adicionar peça do catálogo à gaveta vazia
    - Confirmação de desocupar gaveta sem remover do catálogo
    """
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app.funcionario_id = "1000"
    app.usuario_role = "ADMIN"
    app.navegar("estoque")

    # Verifica se a tela contém a seção de Peças Cadastradas (colapsada por padrão)
    col_tela = app.container_principal.content
    assert len(col_tela.controls) >= 4  # topo + matriz + painel gaveta + catálogo
    assert app.catalogo_expandido is False
    secao_cat = col_tela.controls[3]
    # Quando colapsado (padrão): secao_cat.content é o próprio header_row compacto
    header_row = secao_cat.content
    txt_titulo = header_row.controls[0].controls[0].value
    assert "Peças Cadastradas" in txt_titulo

    # Testa expansão sob demanda
    app.catalogo_expandido = True
    app.renderizar_tela_atual()
    col_tela_exp = app.container_principal.content
    secao_cat_exp = col_tela_exp.controls[3]
    assert isinstance(secao_cat_exp.content, main.ft.Column)
    assert len(secao_cat_exp.content.controls) == 4

    # Testa modal de adicionar peça à gaveta vazia
    app.abrir_modal_adicionar_peca_gaveta(0, 0)
    dlg_add = dummy_page.dialog
    assert dlg_add is not None
    assert "Adicionar Peça" in dlg_add.title.value
    app.fechar_dialogo(dlg_add)
    assert dlg_add.open is False

    # Testa modal de confirmação para desocupar gaveta
    peca_mock = {"id": 102, "nome": "Parafuso Teste", "posicao_linha": 0, "posicao_coluna": 1}
    app.confirmar_desocupar_gaveta(peca_mock)
    dlg_des = dummy_page.dialog
    assert dlg_des is not None
    assert "Desocupar Gaveta" in dlg_des.title.value
    app.fechar_dialogo(dlg_des)
    assert dlg_des.open is False


def test_rfid_unicidade_uma_peca_apenas():
    """
    Garante que cada RFID é linkado a apenas UMA peça:
    - Tentativa de cadastrar ou atualizar peça com RFID já em uso é rejeitada
    - Tentativa de vincular RFID de peça a um usuário (ou vice-versa) é rejeitada
    """
    tag_teste = "AA 11 22 33"
    p1_id = database.cadastrar_peca_catalogo(
        nome="Peça Exclusiva A",
        tipo="Fixador",
        peso_unitario_g=10.0,
        rfid_uid=tag_teste,
    )
    assert p1_id > 0

    # 1. Tentativa de cadastrar segunda peça com a mesma tag deve falhar
    disp, msg = database.verificar_disponibilidade_rfid_peca(tag_teste)
    assert disp is False
    assert "já está vinculada à peça 'Peça Exclusiva A'" in msg

    try:
        database.cadastrar_peca_catalogo(
            nome="Peça Infratora B",
            tipo="Fixador",
            peso_unitario_g=12.0,
            rfid_uid=tag_teste,
        )
        assert False, "Deveria ter lançado ValueError por RFID duplicado"
    except ValueError as ex:
        assert "já está vinculada à peça" in str(ex)

    # 2. Tentativa de vincular a tag a crachá de funcionário também deve falhar
    disp_u, msg_u = database.verificar_disponibilidade_rfid_usuario(tag_teste)
    assert disp_u is False
    assert "já está vinculada à peça" in msg_u

    # Limpeza
    database.excluir_peca(p1_id)


def test_rfid_aviso_erro_quando_nao_for_peca_correspondente():
    """
    Valida a emissão de alerta/erro caso a tag lida não seja a da peça correspondente:
    1. Durante O.S.: tag incorreta toca buzzer de erro, não valida etapa 1 e exibe mensagem
    2. Na estante: gaveta selecionada rejeita tag de outra peça
    3. No LCD 16x2: exibe 'Tag Incorreta!' quando o RFID não corresponde
    """
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app.funcionario_id = "1001"
    app.usuario_role = "OPERARIO"

    # Cria duas peças com tags distintas
    tag_p1 = "E1 E1 E1 E1"
    tag_p2 = "E2 E2 E2 E2"
    database.vincular_rfid_peca(101, tag_p1)
    database.vincular_rfid_peca(102, tag_p2)

    # Cria e inicia O.S. para a peça 101
    oid = database.criar_ordem_servico(
        "OS Teste Validacao RFID",
        [{"peca_id": 101, "tipo_operacao": "REMOCAO", "quantidade": 2}],
        operador_id="1001",
        estante_id=1,
    )
    ordens = database.get_ordens_servico_abertas("1001")
    os_obj = next(o for o in ordens if o["id"] == oid)
    app.iniciar_execucao_os(os_obj)

    assert app.rfid_os_validado is False
    assert app.item_os_selecionado["peca_id"] == 101

    # 1. Lê a tag da peça 102 (NÃO é a correspondente da etapa ativa)
    peca_102 = database.get_peca(102)
    sucesso = app._validar_rfid_na_os(tag_p2, peca_102)
    assert sucesso is False
    assert app.rfid_os_validado is False
    # Display LCD deve resolver para 'Tag Incorreta!'
    txt_lcd = app._resolver_nome_rfid_para_lcd(tag_p2)
    assert txt_lcd == "Tag Incorreta!"

    # 2. Lê a tag correta correspondente (peça 101)
    peca_101 = database.get_peca(101)
    sucesso_correto = app._validar_rfid_na_os(tag_p1, peca_101)
    assert sucesso_correto is True
    assert app.rfid_os_validado is True
    txt_lcd_correto = app._resolver_nome_rfid_para_lcd(tag_p1)
    assert txt_lcd_correto == peca_101["nome"]

    # 3. Na estante com gaveta selecionada (modo livre / Administrador):
    database.alocar_peca_na_estante(101, estante_id=1, posicao_linha=0, posicao_coluna=0, quantidade_inicial=10)
    database.alocar_peca_na_estante(102, estante_id=1, posicao_linha=0, posicao_coluna=1, quantidade_inicial=10)
    app.os_ativa = None
    app.usuario_role = "ADMIN"
    app.aba_atual = "estoque"
    app.estante_ativa_id = 1
    app.slot_selecionado = (0, 0)

    # Teste de Deseleção Manual: clicar na mesma gaveta selecionada deve deselecionar!
    app.tentar_selecionar_gaveta_estante(0, 0)
    assert app.slot_selecionado is None

    # Seleciona novamente e testa o método deselecionar_gaveta()
    app.tentar_selecionar_gaveta_estante(0, 0)
    assert app.slot_selecionado == (0, 0)
    app.deselecionar_gaveta()
    assert app.slot_selecionado is None

    # Seleciona a gaveta (0, 0) da peça 101
    app.tentar_selecionar_gaveta_estante(0, 0)
    assert app.slot_selecionado == (0, 0)

    # No modo livre/admin: aproximar tag de outra peça (peça 102) DEVE resolver para o nome da peça 102 no LCD
    txt_lcd_outra = app._resolver_nome_rfid_para_lcd(tag_p2)
    assert txt_lcd_outra == peca_102["nome"]

    app._ultimo_rfid_ui_tag = ""
    app._ultimo_rfid_ui_ts = 0.0
    # Ao passar a tag da peça 102 no modo livre, a seleção migra automaticamente para a gaveta da peça 102 (0, 1)!
    app._on_rfid_recebido(tag_p2)
    assert app.slot_selecionado == (0, 1)

    # Conclui e limpa a OS de teste
    database.concluir_ordem_servico(oid)
    # Limpa a O.S. temporária do teste
    conn = database.sqlite3.connect(database.DB_PATH)
    conn.execute("DELETE FROM itens_ordem_servico WHERE ordem_id = ?", (oid,))
    conn.execute("DELETE FROM ordens_servico WHERE id = ?", (oid,))
    conn.commit()
    conn.close()


def test_modo_operador_os_bloqueia_deselecao_e_rejeita_outra_tag():
    """
    Garante que no perfil OPERADOR ou durante execução de O.S.:
    - A deseleção manual NÃO é permitida
    - Leitura de tag de outra peça continua emitindo erro e 'Tag Incorreta!' no LCD
    """
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app.funcionario_id = "1001"
    app.usuario_role = "OPERARIO"

    # Aloca peça 101 na posição (0, 0)
    database.alocar_peca_na_estante(101, estante_id=1, posicao_linha=0, posicao_coluna=0, quantidade_inicial=10)
    tag_p1 = "E1 E1 E1 E1"
    tag_p2 = "E2 E2 E2 E2"
    database.vincular_rfid_peca(101, tag_p1)
    database.vincular_rfid_peca(102, tag_p2)

    oid = database.criar_ordem_servico(
        "OS Operador Bloqueio",
        [{"peca_id": 101, "tipo_operacao": "REMOCAO", "quantidade": 1}],
        operador_id="1001",
        estante_id=1,
    )
    ordens = database.get_ordens_servico_abertas("1001")
    os_obj = next(o for o in ordens if o["id"] == oid)
    app.iniciar_execucao_os(os_obj)

    # Verifica que está em modo O.S. estante
    assert app.esta_em_modo_os_estante() is True
    assert app.slot_ativo_os == (0, 0)

    # Tenta deselecionar gaveta no modo operador/O.S. -> Deve ser ignorado
    app.deselecionar_gaveta()
    assert app.slot_ativo_os == (0, 0)

    # Tenta ler tag de outra peça (peça 102) -> Deve resultar em 'Tag Incorreta!' no LCD
    assert app._resolver_nome_rfid_para_lcd(tag_p2) == "Tag Incorreta!"

    # Limpeza
    database.concluir_ordem_servico(oid)
    conn = database.sqlite3.connect(database.DB_PATH)
    conn.execute("DELETE FROM itens_ordem_servico WHERE ordem_id = ?", (oid,))
    conn.execute("DELETE FROM ordens_servico WHERE id = ?", (oid,))
    conn.commit()
    conn.close()


def test_exportacoes_planilhas_csv():
    """
    Testa a geração de planilhas CSV para:
    1. Histórico de Movimentações (exportar_diario_csv)
    2. Auditoria de Ordens de Serviço (exportar_auditoria_os_csv)
    3. Extrato diário por Gaveta (exportar_extrato_gavetas_csv)
    4. Relatório Completo consolidado (exportar_relatorio_completo_csv)
    5. Integração com a UI do Diário (abertura do modal de exportação)
    """
    temp_files = []
    try:
        # 1. Movimentações
        p1 = database.exportar_diario_csv()
        temp_files.append(p1)
        assert os.path.exists(p1)
        with open(p1, "r", encoding="utf-8-sig") as f:
            content = f.read()
            assert "Data/Hora;ID Mov.;Tipo" in content
            assert ";" in content

        # 2. Auditoria OS
        p2 = database.exportar_auditoria_os_csv()
        temp_files.append(p2)
        assert os.path.exists(p2)
        with open(p2, "r", encoding="utf-8-sig") as f:
            content = f.read()
            assert "ID O.S.;Título;Status" in content

        # 3. Extrato Gavetas
        p3 = database.exportar_extrato_gavetas_csv(estante_id=1)
        temp_files.append(p3)
        assert os.path.exists(p3)
        with open(p3, "r", encoding="utf-8-sig") as f:
            content = f.read()
            assert "Data;Estante ID;Posição Linha;Posição Coluna" in content
            assert "Saldo Líquido" in content

        # 4. Relatório Completo
        p4 = database.exportar_relatorio_completo_csv()
        temp_files.append(p4)
        assert os.path.exists(p4)
        with open(p4, "r", encoding="utf-8-sig") as f:
            content = f.read()
            assert "=== RELATÓRIO GERAL MULTILOG - ESTOQUE ATUAL ===" in content
            assert "=== AUDITORIA DE ORDENS DE SERVIÇO ===" in content
            assert "=== HISTÓRICO DE MOVIMENTAÇÕES ===" in content

        # 5. Teste de salvamento em armazenamento do celular (Downloads mock)
        pasta_celular_mock = os.path.join(os.path.dirname(p1), "mock_celular_download")
        os.makedirs(pasta_celular_mock, exist_ok=True)
        try:
            ok_cel, cam_cel = database.salvar_em_armazenamento_celular(p1, pastas_customizadas=[pasta_celular_mock])
            assert ok_cel is True
            assert cam_cel is not None and os.path.exists(cam_cel)
        finally:
            if os.path.exists(pasta_celular_mock):
                import shutil
                shutil.rmtree(pasta_celular_mock, ignore_errors=True)

        # 6. UI Integration & Disparo de exportação via modal
        mensagens_snackbar = []
        def dummy_snackbar(msg, erro=False):
            mensagens_snackbar.append(msg)

        dummy_page = DummyPage()
        tela = diary_view.construir_tela_diario(dummy_page, dummy_snackbar)
        assert tela is not None
        # O topo da coluna deve conter o header_row com o botão de exportar
        header_row = tela.controls[0]
        btn_exp = header_row.controls[1]
        assert "Exportar" in (getattr(btn_exp.content, "value", "") or getattr(btn_exp, "text", ""))

        # Clica no botão exportar e verifica se o diálogo abre
        btn_exp.on_click(None)
        assert dummy_page.dialog is not None
        # Verifica se o diálogo tem opções
        modal_content = dummy_page.dialog.content.content
        assert len(modal_content.controls) >= 5  # Texto introdutório + 4 cards

        # Executa o clique na opção de Movimentações
        card_movs = modal_content.controls[1]
        card_movs.on_click(None)
        assert len(mensagens_snackbar) > 0
        assert "sucesso" in mensagens_snackbar[-1]
    finally:
        for f in temp_files:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        pasta_exp = database.obter_diretorio_exportacoes()
        if os.path.exists(pasta_exp):
            for arq in os.listdir(pasta_exp):
                if arq.endswith(".csv"):
                    try:
                        os.remove(os.path.join(pasta_exp, arq))
                    except Exception:
                        pass


def test_safe_area_evita_sobreposicao_barra_notificacoes():
    """
    Garante que:
    1. O header superior usa SafeArea(avoid_intrusions_top=True) para nunca ficar
       embaixo do relógio, bateria, câmera frontal ou ícones de notificação do Android.
    2. A barra de navegação inferior usa SafeArea(avoid_intrusions_bottom=True) para
       não sobrepor os botões de navegação e barra de gestos do sistema Android.
    3. O layout raiz protege toda a aplicação contra invasões de tela cheia.
    """
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)

    assert len(dummy_page.controls) >= 1
    root_ctrl = dummy_page.controls[0]
    assert isinstance(root_ctrl, main.ft.SafeArea)

    col_raiz = root_ctrl.content
    assert isinstance(col_raiz, main.ft.Column)
    header = col_raiz.controls[0]

    assert hasattr(header, "content")
    assert isinstance(header.content, main.ft.SafeArea)
    assert header.content.avoid_intrusions_top is True

    nav_wrapper = app.wrapper_navegacao
    assert hasattr(nav_wrapper, "content")
    assert isinstance(nav_wrapper.content, main.ft.SafeArea)
    assert nav_wrapper.content.avoid_intrusions_bottom is True


def test_estante_ampla_com_side_bar_horizontal():
    """
    Garante que:
    1. Para estantes com mais de 3 colunas (estante ampla), a matriz de gavetas
       é envolvida em um container de rolagem horizontal (scroll=ALWAYS).
    2. Uma side bar inferior de rolagem com botões ◀ e ▶ e indicador de colunas é exibida.
    3. Cada gaveta possui largura fixa (115dp) evitando que o texto fique espremido.
    4. Estantes padrão (<= 3 colunas) mantêm expand=True sem barra de rolagem horizontal.
    """
    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app.funcionario_id = "1000"
    app.usuario_role = "ADMIN"

    # Cria uma estante de teste ampla (3 linhas x 6 colunas)
    temp_id = database.criar_estante("Estante Ampla 3x6", 3, 6, "Teste Scroll Lateral")
    try:
        app.selecionar_estante(temp_id)
        app.navegar("estoque")

        col_tela = app.container_principal.content
        card_matriz = col_tela.controls[1]
        controls_matriz = card_matriz.content.controls

        # Deve conter título, matriz scroll e barra de rolagem lateral inferior (3 controles)
        assert len(controls_matriz) == 3
        matriz_scroll = controls_matriz[1]
        barra_inferior = controls_matriz[2]

        # Verifica container de rolagem horizontal
        assert isinstance(matriz_scroll, main.ft.Row)
        assert matriz_scroll.scroll == main.ft.ScrollMode.ALWAYS

        # Verifica que os botões de navegação lateral ◀ e ▶ estão presentes na side bar inferior
        row_botoes = barra_inferior.content
        btn_esq = row_botoes.controls[0]
        lbl_info = row_botoes.controls[1]
        btn_dir = row_botoes.controls[2]
        assert "6 Colunas" in lbl_info.controls[1].value

        # Testa o acionamento dos botões de scroll
        btn_dir.on_click(None)
        btn_esq.on_click(None)

        # Verifica que as gavetas possuem largura fixa de 115dp (não espremidas)
        matriz_col = matriz_scroll.controls[0]
        primeiro_card = matriz_col.controls[0].controls[0]
        assert primeiro_card.width == 115
        assert primeiro_card.expand is False

        # Volta para estante padrão (<= 3 colunas) e verifica retorno ao layout normal
        app.selecionar_estante(1)
        app.navegar("estoque")
        col_padrao = app.container_principal.content
        card_padrao = col_padrao.controls[1]
        # Estante padrão possui apenas Título e Matriz direta (2 controles)
        assert len(card_padrao.content.controls) == 2
        primeiro_card_padrao = card_padrao.content.controls[1].controls[0].controls[0]
        assert primeiro_card_padrao.expand is True
    finally:
        database.excluir_estante(temp_id)


def test_buzzer_bip_leitura_e_bip_duplo_erro():
    """
    Testa a regra de negócio do Buzzer:
    1. A cada passagem de tag RFID: emite 1 bip simples de confirmação de leitura.
    2. Quando a tag for errada (não cadastrada ou não correspondente na O.S.): emite bip duplo de erro.
    3. Quando o peso for incorreto/divergente: emite bip duplo de erro.
    """
    bips_simples = 0
    bips_duplos = 0

    orig_bip = hardware_mock.tocar_buzzer_bip
    orig_erro = hardware_mock.tocar_buzzer_erro

    def _spy_bip():
        nonlocal bips_simples
        bips_simples += 1
        orig_bip()

    def _spy_erro():
        nonlocal bips_duplos
        bips_duplos += 1
        orig_erro()

    hardware_mock.tocar_buzzer_bip = _spy_bip
    hardware_mock.tocar_buzzer_erro = _spy_erro

    dummy_page = DummyPage()
    app = main.MultilogMobileApp(dummy_page)
    app.funcionario_id = "1001"
    app.usuario_role = "OPERARIO"

    try:
        # Prepara peças para teste
        tag_correta = "A1 B2 C3 D4"
        tag_errada = "F9 E8 D7 C6"
        database.vincular_rfid_peca(101, tag_correta)
        database.vincular_rfid_peca(102, tag_errada)

        # 1. Leitura de tag avulsa não cadastrada
        bips_simples = 0
        bips_duplos = 0
        app._ultimo_rfid_ui_tag = ""
        app._ultimo_rfid_ui_ts = 0.0
        app._on_rfid_recebido("99 99 99 99")
        # Deve emitir 1 bip simples de leitura + 1 bip duplo de erro (tag não cadastrada)
        assert bips_simples == 1
        assert bips_duplos == 1

        # 2. Inicia uma O.S. esperando a peça 101
        oid = database.criar_ordem_servico(
            "OS Teste Buzzer",
            [{"peca_id": 101, "tipo_operacao": "REMOCAO", "quantidade": 2}],
            operador_id="1001",
            estante_id=1,
        )
        ordens = database.get_ordens_servico_abertas("1001")
        os_obj = next(o for o in ordens if o["id"] == oid)
        app.iniciar_execucao_os(os_obj)

        # 2a. Operador passa a tag ERRADA (peça 102) durante a O.S.
        bips_simples = 0
        bips_duplos = 0
        app._ultimo_rfid_ui_tag = ""
        app._ultimo_rfid_ui_ts = 0.0
        app._on_rfid_recebido(tag_errada)
        assert bips_simples == 1
        assert bips_duplos == 1
        assert app.rfid_os_validado is False

        # 2b. Operador passa a tag CORRETA (peça 101) durante a O.S.
        bips_simples = 0
        bips_duplos = 0
        app._ultimo_rfid_ui_tag = ""
        app._ultimo_rfid_ui_ts = 0.0
        app._on_rfid_recebido(tag_correta)
        assert bips_simples == 1
        assert bips_duplos == 0
        assert app.rfid_os_validado is True

        # 3. Teste de PESO INCORRETO na O.S. e na movimentação
        peca_101 = database.get_peca(101)
        peso_unit = float(peca_101["peso_unitario_g"])
        peso_errado = (peso_unit * 2) * 0.5  # 50% divergente (fora da tolerância de ±5%)

        # Renderiza modal de execução da O.S.
        app.renderizar_tela_atual()
        assert not logic.validar_peso(peso_errado, peso_unit, 2)

        # Valida que logic.processar_operacao emite o bip duplo ao detectar erro de peso
        dados_op = {
            "id": 101,
            "nome": peca_101["nome"],
            "tipo": peca_101.get("tipo", "Fixação"),
            "peso_unitario_g": peso_unit,
            "quantidade": 2,
            "posicao_linha": peca_101["posicao_linha"],
            "posicao_coluna": peca_101["posicao_coluna"],
        }
        bips_duplos = 0
        sucesso_peso, msg_peso, _ = logic.processar_operacao("1001", dados_op, "REMOCAO", peso_informado=peso_errado)
        assert sucesso_peso is False
        assert "Erro de peso" in msg_peso
        assert bips_duplos == 1

    finally:
        hardware_mock.tocar_buzzer_bip = orig_bip
        hardware_mock.tocar_buzzer_erro = orig_erro
        app.os_ativa = None










