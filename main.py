import os
import shutil
import threading
import time
import flet as ft
import database
import logic
import hardware_manager
import hardware_mock
from diary_view import construir_tela_diario
from typing import Optional, Dict, Any, List, Tuple

# --- Identidade Visual Oficial Multilog - Modo Pro Clean ---
MULTILOG_NAVY = "#003865"
MULTILOG_NAVY_DARK = "#002B4F"
MULTILOG_NAVY_HOVER = "#004B82"
MULTILOG_BLUE = "#0066CC"
MULTILOG_CYAN = "#0284C7"
MULTILOG_LIGHT_BLUE = "#DCEBFA"
MULTILOG_BORDER_BLUE = "#93C5FD"

BG_APP = "#F0F4F8"
BG_CARD = "#FFFFFF"
BG_ELEVATED = "#F8FAFC"
BORDER_SUBTLE = "#E2E8F0"
TEXT_MAIN = "#0F172A"
TEXT_MUTED = "#64748B"
TEXT_SUBTLE = "#94A3B8"

ACCENT_EMERALD = "#10B981"
ACCENT_AMBER = "#F59E0B"
ACCENT_ROSE = "#EF4444"

# Dimensões verticais em proporção exata 20:9 (9:20 retrato smartphone Android)
VIEWPORT_WIDTH_20_9 = 378
VIEWPORT_HEIGHT_20_9 = 840


def _pasta_fotos_funcionarios() -> str:
    base_dir = os.path.dirname(os.path.abspath(database.get_db_path()))
    pasta = os.path.join(base_dir, "fotos_funcionarios")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _extrair_bytes_foto(foto_path: Optional[str] = None, foto_blob: Optional[bytes] = None) -> Optional[bytes]:
    if foto_blob and len(foto_blob) > 0:
        return bytes(foto_blob)
    caminho = (foto_path or "").strip()
    if caminho and os.path.isfile(caminho):
        try:
            with open(caminho, "rb") as f:
                return f.read()
        except Exception:
            pass
    if caminho:
        # Tenta localizar pelo basename dentro de fotos_funcionarios local
        candidato = os.path.join(_pasta_fotos_funcionarios(), os.path.basename(caminho))
        if os.path.isfile(candidato):
            try:
                with open(candidato, "rb") as f:
                    return f.read()
            except Exception:
                pass
    return None


def _criar_avatar_widget(
    foto_path: Optional[str] = None,
    foto_blob: Optional[bytes] = None,
    size: int = 44,
    is_admin: bool = False,
    border_radius: int = 8,
) -> ft.Container:
    raw_bytes = _extrair_bytes_foto(foto_path=foto_path, foto_blob=foto_blob)
    cor_borda = "#FCD34D" if is_admin else "#38BDF8"
    cor_fundo = "#FEF3C7" if is_admin else "#DCEBFA"
    icone = "⚡" if is_admin else "👤"
    cor_icone = "#D97706" if is_admin else MULTILOG_BLUE

    if raw_bytes:
        try:
            fit_cover = getattr(getattr(ft, "BoxFit", None), "COVER", None) or getattr(getattr(ft, "ImageFit", None), "COVER", None)
            kwargs_img: Dict[str, Any] = {
                "src": raw_bytes,
                "width": size - 4,
                "height": size - 4,
                "border_radius": max(4, border_radius - 2),
            }
            if fit_cover is not None:
                kwargs_img["fit"] = fit_cover
            img_ctrl = ft.Image(**kwargs_img)
            return ft.Container(
                width=size,
                height=size,
                bgcolor=cor_fundo,
                border=_border_all(2, cor_borda),
                border_radius=border_radius,
                alignment=_align_center(),
                content=img_ctrl,
            )
        except Exception:
            pass

    return ft.Container(
        width=size,
        height=size,
        bgcolor=cor_fundo,
        border=_border_all(2, cor_borda),
        border_radius=border_radius,
        alignment=_align_center(),
        content=ft.Text(icone, size=max(14, int(size * 0.42)), color=cor_icone),
    )


def _opt(key: str, text: str):
    if hasattr(ft, "DropdownOption"):
        return ft.DropdownOption(key=key, text=text)
    return ft.dropdown.Option(key, text)


def _border_all(width: float, color: str):
    if hasattr(ft, "Border") and hasattr(ft.Border, "all"):
        return ft.Border.all(width, color)
    return ft.border.all(width, color)


def _pad_sym(h: float = 0, v: float = 0):
    if hasattr(ft, "Padding") and hasattr(ft.Padding, "symmetric"):
        return ft.Padding.symmetric(horizontal=h, vertical=v)
    return ft.padding.symmetric(horizontal=h, vertical=v)


def _align_center():
    if hasattr(ft, "Alignment") and hasattr(ft.Alignment, "CENTER"):
        return ft.Alignment.CENTER
    return ft.alignment.center


def _btn(
    text: str,
    on_click=None,
    bgcolor: str = MULTILOG_NAVY,
    color: str = "#FFFFFF",
    expand: bool = False,
    width: Optional[int] = None,
    height: Optional[int] = 36,
    font_size: int = 12,
):
    cls = getattr(ft, "Button", None) or getattr(ft, "ElevatedButton")
    txt_ctrl = ft.Text(
        text,
        size=font_size,
        weight=ft.FontWeight.BOLD,
        color=color,
        no_wrap=True,
        text_align=ft.TextAlign.CENTER,
    )
    kwargs: Dict[str, Any] = {
        "content": txt_ctrl,
        "on_click": on_click,
        "bgcolor": bgcolor,
        "color": color,
        "expand": expand,
        "width": width,
        "height": height,
    }
    if hasattr(ft, "ButtonStyle"):
        style_kwargs: Dict[str, Any] = {
            "padding": _pad_sym(8, 0),
        }
        if hasattr(ft, "RoundedRectangleBorder"):
            style_kwargs["shape"] = ft.RoundedRectangleBorder(radius=10)
        kwargs["style"] = ft.ButtonStyle(**style_kwargs)
    return cls(**kwargs)


class MultilogMobileApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "MULTILOG · Android (20:9)"
        self.page.bgcolor = BG_APP
        self.page.padding = 0
        try:
            self.page.theme_mode = ft.ThemeMode.LIGHT
        except Exception:
            pass

        # Configura tela na vertical com aspecto 20:9 (378x840)
        try:
            if hasattr(self.page, "window") and self.page.window is not None:
                self.page.window.width = VIEWPORT_WIDTH_20_9
                self.page.window.height = VIEWPORT_HEIGHT_20_9
                self.page.window.min_width = 340
                self.page.window.min_height = 680
            else:
                self.page.window_width = VIEWPORT_WIDTH_20_9
                self.page.window_height = VIEWPORT_HEIGHT_20_9
        except Exception:
            pass

        # Estado da sessão
        self.funcionario_id: str = ""
        self.usuario_nome: str = ""
        self.usuario_role: str = ""
        self.usuario_foto_path: str = ""
        self.usuario_foto_blob: Optional[bytes] = None
        self.aba_atual: str = "login"

        # Proteção UI de debounce RFID (2.0 segundos)
        self._ultimo_rfid_ui_tag: str = ""
        self._ultimo_rfid_ui_ts: float = 0.0

        # Estado da Estante ativa
        estantes = database.get_todas_estantes()
        estante_esp = next((e for e in estantes if e["linhas"] == 2 and e["colunas"] == 3), None)
        self.estante_ativa_id: int = estante_esp["id"] if estante_esp else (estantes[0]["id"] if estantes else 1)
        self.slot_selecionado: Optional[Tuple[int, int]] = None  # (r, c) no modo livre (Admin)

        # Estado de Ordem de Serviço em execução (Modo Guiado Pick-to-Light + Passo 1 RFID -> Passo 2 Balança)
        self.os_ativa: Optional[Dict[str, Any]] = None
        self.item_os_selecionado: Optional[Dict[str, Any]] = None
        self.slot_ativo_os: Optional[Tuple[int, int]] = None
        self.rfid_os_obrigatorio: bool = True
        self.rfid_os_validado: bool = False

        # Pisca-pisca (500ms) da posição ativa na Estante durante O.S.
        self.blink_state: bool = False
        self._blink_rodando: bool = True
        self._slot_ativo_container: Optional[ft.Container] = None
        self._slot_ativo_dot_lbl: Optional[ft.Text] = None

        # Referência opcional a campos abertos em modais/painéis
        self.campo_rfid_modal_ativo: Optional[ft.TextField] = None
        self.campo_nome_modal_ativo: Optional[ft.TextField] = None
        self.campo_peso_modal_ativo: Optional[ft.TextField] = None
        self.callback_rfid_tela_usuarios: Optional[Any] = None

        # Inicializa Hardware Wi-Fi/Serial (ESP32 - RFID, Balança, Buzzer e Display LCD 16x2)
        self.hw = hardware_manager.HardwareManager.get_instancia()
        self.hw.resolver_nome_custom = self._resolver_nome_rfid_para_lcd
        self.hw.registrar_callback_rfid(self._on_rfid_recebido)
        self.hw.registrar_callback_peso(self._on_peso_recebido)
        self.hw.iniciar_monitoramento_background()

        # Inicia thread leve de pisca-pisca para a gaveta ativa da O.S.
        self._thread_pisca = threading.Thread(target=self._loop_pisca_estante, daemon=True)
        self._thread_pisca.start()

        # Widgets globais de status no topo (compactos para largura 20:9)
        self.txt_peso_topo = ft.Text("⚖️ 0.0g", size=11, weight=ft.FontWeight.BOLD, color="#FFFFFF")
        self.txt_hw_topo = ft.Text("📡 ESP32", size=10, weight=ft.FontWeight.BOLD, color="#BFDBFE")
        self.badge_usuario_header = ft.Row(spacing=6, visible=False)
        self.container_principal = ft.Container(expand=True, padding=_pad_sym(10, 8))
        self.barra_navegacao = ft.Row(spacing=4)
        self.wrapper_navegacao = ft.Container(
            bgcolor=BG_CARD,
            border=_border_all(1, BORDER_SUBTLE),
            padding=_pad_sym(6, 5),
            visible=False,
            content=self.barra_navegacao,
        )

        self._montar_layout_base()
        self.navegar("login")

    # =========================================================================
    # Resolução de Texto para o Display LCD 16x2 do ESP32
    # =========================================================================
    def _resolver_nome_rfid_para_lcd(self, tag: str) -> Optional[str]:
        """
        Retorna texto personalizado para a 2ª linha do LCD 16x2 do ESP32 conforme a tela/modal aberto:
        - Modal de cadastro de peça: nome digitado ou 'Tag Lida (Novo)'
        - Tela de gestão de usuários: 'ID:<nome>' ou 'Cracha Lido'
        - Sessão já ativa fora da tela de login e tag de colaborador: 'Saia p/ Login'
        """
        try:
            if self.campo_rfid_modal_ativo is not None:
                if self.campo_nome_modal_ativo is not None and (self.campo_nome_modal_ativo.value or "").strip():
                    return self.campo_nome_modal_ativo.value.strip()
                peca_db = database.get_peca_por_rfid(tag)
                if peca_db and peca_db.get("nome"):
                    return peca_db["nome"]
                return "Tag Lida (Novo)"

            if self.aba_atual == "usuarios":
                if self.campo_nome_modal_ativo is not None and (self.campo_nome_modal_ativo.value or "").strip():
                    return f"ID:{self.campo_nome_modal_ativo.value.strip()[:13]}"
                return "Cracha Lido"

            if self.aba_atual != "login" and self.funcionario_id:
                usr = database.get_usuario_por_rfid(tag)
                if usr and not database.get_peca_por_rfid(tag):
                    return "Saia p/ Login"
        except Exception:
            pass
        return None

    # =========================================================================
    # Atualização do Badge de Funcionário no Cabeçalho (Foto + Nome + ID/Perfil)
    # =========================================================================
    def _atualizar_badge_header(self):
        if not self.funcionario_id:
            self.badge_usuario_header.visible = False
            self.lbl_usuario_topo.value = "Desconectado"
            self.lbl_usuario_topo.visible = True
            self.btn_sair_topo.visible = False
            return

        u_db = database.get_usuario(self.funcionario_id)
        if u_db:
            self.usuario_nome = u_db.get("nome") or self.usuario_nome
            self.usuario_role = u_db.get("role") or self.usuario_role
            self.usuario_foto_path = (u_db.get("foto_path") or "").strip()
            self.usuario_foto_blob = u_db.get("foto_blob")

        eh_admin = (self.usuario_role == "ADMIN")
        perfil_txt = "ADMIN" if eh_admin else "OPERADOR"
        avatar = _criar_avatar_widget(
            foto_path=self.usuario_foto_path,
            foto_blob=self.usuario_foto_blob,
            size=34,
            is_admin=eh_admin,
            border_radius=8,
        )
        self.badge_usuario_header.controls = [
            avatar,
            ft.Column(
                spacing=0,
                controls=[
                    ft.Text(self.usuario_nome, size=11, weight=ft.FontWeight.BOLD, color="#FFFFFF", no_wrap=True),
                    ft.Text(f"ID: {self.funcionario_id} · {perfil_txt}", size=9, weight=ft.FontWeight.BOLD, color="#93C5FD", no_wrap=True),
                ],
            ),
        ]
        self.badge_usuario_header.visible = True
        self.lbl_usuario_topo.visible = False
        self.btn_sair_topo.visible = True

    def _autenticar_usuario(self, user: Dict[str, Any]):
        self.funcionario_id = str(user["id"])
        self.usuario_nome = user["nome"]
        self.usuario_role = user["role"]
        self.usuario_foto_path = (user.get("foto_path") or "").strip()
        self.usuario_foto_blob = user.get("foto_blob")
        self._atualizar_badge_header()

        if self.usuario_role == "ADMIN":
            self.navegar("admin")
        else:
            self.navegar("ordens")

    # =========================================================================
    # Pisca-Pisca da Posição Ativa na Estante (500ms igual ao PC)
    # =========================================================================
    def esta_em_modo_os_estante(self) -> bool:
        """Retorna True se há uma O.S. ativa sendo cumprida ou se o usuário é Operador."""
        return self.os_ativa is not None or self.usuario_role == "OPERARIO"

    def _executar_passo_pisca(self):
        """Alterna o estado visual de pisca-pisca da gaveta ativa da O.S. (chamado a cada 500ms)."""
        self.blink_state = not self.blink_state
        if self._slot_ativo_container is not None and self._slot_ativo_dot_lbl is not None:
            if self.blink_state:
                self._slot_ativo_container.border = _border_all(3, "#22C55E")
                self._slot_ativo_container.bgcolor = "#DCFCE7"
                self._slot_ativo_dot_lbl.value = "●ATIVO"
                self._slot_ativo_dot_lbl.color = "#15803D"
            else:
                self._slot_ativo_container.border = _border_all(2, "#059669")
                self._slot_ativo_container.bgcolor = "#E0F2FE"
                self._slot_ativo_dot_lbl.value = "○LED"
                self._slot_ativo_dot_lbl.color = "#0284C7"

    def _loop_pisca_estante(self):
        while self._blink_rodando:
            time.sleep(0.5)
            try:
                if (
                    self.aba_atual == "estoque"
                    and self.os_ativa is not None
                    and self.slot_ativo_os is not None
                    and self._slot_ativo_container is not None
                ):
                    self._executar_passo_pisca()
                    self.page.update()
            except Exception:
                pass

    # =========================================================================
    # Controle de Execução de O.S. e Seleção de Item / Gaveta
    # =========================================================================
    def iniciar_execucao_os(self, ordem: Dict[str, Any]):
        """Inicia ou retoma uma O.S., travando a estante da O.S. e ativando o primeiro item pendente."""
        self.os_ativa = ordem
        self.estante_ativa_id = ordem.get("estante_id") or 1
        itens = database.get_itens_ordem_servico(ordem["id"])
        prox_item = next(
            (i for i in itens if i.get("quantidade_restante", i["quantidade"] - i.get("quantidade_atendida", 0)) > 0),
            None,
        )
        self.selecionar_item_os(prox_item, atualizar_tela=False)
        self.navegar("executar_os")

    def selecionar_item_os(self, item: Optional[Dict[str, Any]], atualizar_tela: bool = True, rfid_ja_validado: bool = False):
        """
        Define o item ativo da O.S., exige primeiramente a leitura da Tag RFID (Passo 1)
        para liberar a pesagem na balança (Passo 2), e acende o LED físico no ESP32.
        """
        self.item_os_selecionado = item
        self.rfid_os_obrigatorio = True
        self.rfid_os_validado = rfid_ja_validado

        if not item:
            self.slot_ativo_os = None
            hardware_mock.apagar_led()
        else:
            peca = database.get_peca(item["peca_id"])
            if peca:
                self.estante_ativa_id = peca.get("estante_id") or self.estante_ativa_id
                self.slot_ativo_os = (peca["posicao_linha"], peca["posicao_coluna"])
                hardware_mock.acender_led(peca["posicao_linha"], peca["posicao_coluna"])
                try:
                    self.hw.enviar_nome_lcd(peca["nome"])
                except Exception:
                    pass
            else:
                self.slot_ativo_os = None
        if atualizar_tela:
            self.renderizar_tela_atual()

    def simular_leitura_rfid_item_os_ativo(self):
        """Simula a leitura da tag RFID do item ativo da O.S. (Passo 1) para testes em bancada/simulador."""
        if not self.item_os_selecionado:
            return
        peca_id = self.item_os_selecionado["peca_id"]
        peca_ativa = database.get_peca(peca_id)
        if not peca_ativa:
            peca_ativa = {"id": peca_id, "nome": f"Peça #{peca_id}", "rfid_uid": ""}
        tag_sim = (peca_ativa.get("rfid_uid") or "").strip()
        if not tag_sim:
            tag_sim = f"FA CE {peca_id // 256:02X} {peca_id % 256:02X}"
        self._validar_rfid_na_os(tag_sim, peca_ativa)

    def _validar_rfid_na_os(self, tag: str, peca_lida: Optional[Dict[str, Any]]) -> bool:
        """
        Executa a validação Poka-Yoke da etapa 1 (RFID) na O.S. ativa:
        1. Se a tag pertence ao item ativo: libera Passo 2 (Pesagem).
        2. Se o item ativo ainda não tinha rfid_uid cadastrado e a tag não pertence a outro item: vincula e libera Passo 2.
        3. Se a tag pertence a outro item pendente da O.S.: seleciona esse item e já libera Passo 2.
        4. Caso contrário: aciona o buzzer de erro (D2) e exibe alerta.
        """
        if not self.os_ativa:
            return False

        itens = database.get_itens_ordem_servico(self.os_ativa["id"])
        peca_ativa = database.get_peca(self.item_os_selecionado["peca_id"]) if self.item_os_selecionado else None

        # 1. Tag pertence ao item ativo
        if self.item_os_selecionado and peca_lida and self.item_os_selecionado["peca_id"] == peca_lida["id"]:
            self.rfid_os_validado = True
            try:
                self.hw.enviar_nome_lcd(peca_lida["nome"])
            except Exception:
                pass
            self.mostrar_snackbar(f"✓ Passo 1 concluído! Tag RFID de '{peca_lida['nome']}' validada. Execute a pesagem (Passo 2).")
            self.renderizar_tela_atual()
            return True

        # 2. Item ativo sem rfid_uid cadastrado ainda: vincula automaticamente e valida Passo 1
        if self.item_os_selecionado and peca_ativa and not (peca_ativa.get("rfid_uid") or "").strip():
            pertence_a_outro = bool(peca_lida and any(i["peca_id"] == peca_lida["id"] for i in itens))
            if not pertence_a_outro:
                database.vincular_rfid_peca(peca_ativa["id"], tag)
                self.rfid_os_validado = True
                try:
                    self.hw.enviar_nome_lcd(peca_ativa["nome"])
                except Exception:
                    pass
                self.mostrar_snackbar(f"✓ Tag {tag} vinculada e validada para '{peca_ativa['nome']}'! Execute a pesagem (Passo 2).")
                self.renderizar_tela_atual()
                return True

        if not peca_lida:
            hardware_mock.tocar_buzzer_erro()
            esp_str = f" (Esperado: {peca_ativa['rfid_uid']})" if (peca_ativa and peca_ativa.get("rfid_uid")) else ""
            self.mostrar_snackbar(f"⚠️ Tag não reconhecida: {tag}{esp_str}", erro=True)
            return False

        # 3. Tag pertence a outro item pendente da O.S.
        outro_item = next(
            (i for i in itens if i["peca_id"] == peca_lida["id"] and i.get("quantidade_restante", i["quantidade"] - i.get("quantidade_atendida", 0)) > 0),
            None,
        )
        if outro_item:
            self.selecionar_item_os(outro_item, atualizar_tela=True, rfid_ja_validado=True)
            self.mostrar_snackbar(
                f"✓ Tag '{peca_lida['nome']}' validada! Gaveta L{peca_lida['posicao_linha']+1}·C{peca_lida['posicao_coluna']+1} piscando — execute a pesagem."
            )
            return True

        # 4. Peça já concluída ou fora da O.S.
        hardware_mock.tocar_buzzer_erro()
        item_concluido = next((i for i in itens if i["peca_id"] == peca_lida["id"]), None)
        if item_concluido:
            self.mostrar_snackbar(f"ℹ️ '{peca_lida['nome']}' já foi 100% atendida nesta O.S.", erro=True)
        else:
            self.mostrar_snackbar(f"⚠️ Divergência: '{peca_lida['nome']}' não faz parte desta O.S.!", erro=True)
        return False

    def tentar_selecionar_gaveta_estante(self, r: int, c: int) -> bool:
        """
        Trata o clique em uma gaveta na tela Estante:
        - Se estiver cumprindo uma O.S. (ou for Operador): NÃO permite modificar outras posições.
          Apenas permite selecionar se aquela gaveta contiver um item pendente da O.S. ativa.
        - Se for ADMIN sem O.S. ativa: permite selecionar qualquer gaveta livremente.
        """
        if self.esta_em_modo_os_estante():
            if not self.os_ativa:
                self.mostrar_snackbar(
                    "🔒 Modo Operador: Selecione uma O.S. em 'Minhas O.S.' para operar a estante.",
                    erro=True,
                )
                return False

            pecas = database.get_pecas_por_estante(self.estante_ativa_id)
            peca_clicada = next((p for p in pecas if p["posicao_linha"] == r and p["posicao_coluna"] == c), None)
            if not peca_clicada:
                self.mostrar_snackbar(
                    f"🔒 Posição L{r+1}·C{c+1} bloqueada! Opere apenas a gaveta que está piscando.",
                    erro=True,
                )
                return False

            itens_os = database.get_itens_ordem_servico(self.os_ativa["id"])
            item_corresp = next(
                (
                    i
                    for i in itens_os
                    if i["peca_id"] == peca_clicada["id"]
                    and i.get("quantidade_restante", i["quantidade"] - i.get("quantidade_atendida", 0)) > 0
                ),
                None,
            )
            if not item_corresp:
                self.mostrar_snackbar(
                    f"🔒 '{peca_clicada['nome']}' (L{r+1}·C{c+1}) não possui operação pendente nesta O.S.!",
                    erro=True,
                )
                return False

            self.selecionar_item_os(item_corresp, atualizar_tela=True)
            return True

        # Modo livre (Admin sem O.S. em execução)
        self.slot_selecionado = (r, c)
        hardware_mock.acender_led(r, c)
        self.renderizar_tela_atual()
        return True

    # =========================================================================
    # Utilitários de UI (Dialog / Snackbar)
    # =========================================================================
    def mostrar_snackbar(self, mensagem: str, erro: bool = False):
        cor = ACCENT_ROSE if erro else ACCENT_EMERALD
        sb = ft.SnackBar(
            content=ft.Text(mensagem, color="#FFFFFF", weight=ft.FontWeight.BOLD, size=12),
            bgcolor=cor,
        )
        try:
            self.page.show_dialog(sb)
        except Exception:
            try:
                self.page.open(sb)
            except Exception:
                self.page.snack_bar = sb
                sb.open = True
                self.page.update()

    def abrir_dialogo(self, dlg: ft.AlertDialog):
        try:
            self.page.show_dialog(dlg)
        except Exception:
            try:
                self.page.open(dlg)
            except Exception:
                self.page.dialog = dlg
                dlg.open = True
                self.page.update()

    def fechar_dialogo(self, dlg: ft.AlertDialog):
        self.campo_rfid_modal_ativo = None
        self.campo_nome_modal_ativo = None
        self.campo_peso_modal_ativo = None
        try:
            self.page.pop_dialog()
        except Exception:
            try:
                self.page.close(dlg)
            except Exception:
                dlg.open = False
                self.page.update()

    # =========================================================================
    # Callbacks de Hardware (ESP32 Wi-Fi / Simulador)
    # =========================================================================
    def _on_peso_recebido(self, peso: float):
        try:
            self.txt_peso_topo.value = f"⚖️ {peso:.1f}g"
            self.txt_hw_topo.value = "🟢ESP32" if self.hw.esta_conectado() else "🟡Simul."
            if self.campo_peso_modal_ativo is not None and peso >= 0:
                self.campo_peso_modal_ativo.value = f"{peso:.1f}"
            self.page.update()
        except Exception:
            pass

    def _on_rfid_recebido(self, tag: str):
        try:
            tag_fmt = database.formatar_rfid_uid(tag)
            if not tag_fmt:
                return

            # Proteção de debounce (2.0s) na camada de UI contra disparos duplos (Wi-Fi + Serial)
            agora = time.time()
            if tag_fmt == self._ultimo_rfid_ui_tag and (agora - self._ultimo_rfid_ui_ts) < 2.0:
                print(f"[UI] Ignorando evento RFID duplicado na UI: '{tag_fmt}'")
                return
            self._ultimo_rfid_ui_tag = tag_fmt
            self._ultimo_rfid_ui_ts = agora

            # 1. Se houver modal de cadastro de peça aberto, preenche o campo de RFID e não abre outro modal
            if self.campo_rfid_modal_ativo is not None and self.aba_atual != "usuarios":
                self.campo_rfid_modal_ativo.value = tag_fmt
                self.mostrar_snackbar(f"Tag RFID capturada no cadastro: {tag_fmt}")
                self.page.update()
                return

            # 2. Se estiver na tela de Gestão de Usuários (Admin), preenche o crachá RFID do funcionário
            if self.aba_atual == "usuarios" and self.callback_rfid_tela_usuarios is not None:
                self.callback_rfid_tela_usuarios(tag_fmt)
                return

            # 3. Se estiver na tela de Login, realiza Login Instantâneo por Crachá RFID
            usuario_rfid = database.get_usuario_por_rfid(tag_fmt)
            if self.aba_atual == "login" or not self.funcionario_id:
                if usuario_rfid:
                    prefixo = "ADM " if usuario_rfid.get("role") == "ADMIN" else "OP "
                    try:
                        self.hw.enviar_nome_lcd(f"{prefixo}{usuario_rfid['nome']}")
                    except Exception:
                        pass
                    perfil_lbl = "ADMIN" if usuario_rfid.get("role") == "ADMIN" else "OPERADOR"
                    self.mostrar_snackbar(f"✅ Crachá {tag_fmt} reconhecido: {usuario_rfid['nome']} ({perfil_lbl})")
                    self._autenticar_usuario(usuario_rfid)
                    return
                else:
                    hardware_mock.tocar_buzzer_erro()
                    self.mostrar_snackbar(f"❌ Tag RFID '{tag_fmt}' não vinculada a nenhum funcionário!", erro=True)
                    return

            # 4. Busca se a tag pertence a alguma peça do catálogo
            peca = database.get_peca_por_rfid(tag_fmt)
            if peca and peca.get("nome"):
                try:
                    self.hw.enviar_nome_lcd(peca["nome"])
                except Exception:
                    pass
            elif usuario_rfid and not self.os_ativa:
                # Bloqueio de troca indevida de perfil fora da tela de Login!
                try:
                    self.hw.enviar_nome_lcd("Saia p/ Login")
                except Exception:
                    pass
                hardware_mock.tocar_buzzer_erro()
                self.mostrar_snackbar(
                    "🔒 Sessão em andamento! Clique em 'Sair' antes de aproximar o crachá de outro colaborador.",
                    erro=True,
                )
                return

            # 5. Se estiver cumprindo uma Ordem de Serviço (em Minhas O.S. ou na Estante): valida Passo 1 (RFID)
            if self.os_ativa:
                if usuario_rfid and not peca:
                    try:
                        self.hw.enviar_nome_lcd("Saia p/ Login")
                    except Exception:
                        pass
                    hardware_mock.tocar_buzzer_erro()
                    self.mostrar_snackbar(
                        "🔒 Crachá de colaborador ignorado durante O.S.! Aproxime a tag da PEÇA ou clique em 'Sair'.",
                        erro=True,
                    )
                    return
                self._validar_rfid_na_os(tag_fmt, peca)
                return

            if not peca:
                hardware_mock.tocar_buzzer_erro()
                self.mostrar_snackbar(f"Tag RFID '{tag_fmt}' não cadastrada para nenhum produto.", erro=True)
                return

            if self.usuario_role == "OPERARIO":
                self.mostrar_snackbar("Inicie uma Ordem de Serviço em 'Minhas O.S.' antes de operar peças.", erro=True)
                return

            self.estante_ativa_id = peca.get("estante_id", 1)
            self.slot_selecionado = (peca["posicao_linha"], peca["posicao_coluna"])
            hardware_mock.acender_led(peca["posicao_linha"], peca["posicao_coluna"])
            self.mostrar_snackbar(f"Peça localizada: {peca['nome']} (L{peca['posicao_linha']+1}·C{peca['posicao_coluna']+1})")
            self.navegar("estoque")
        except Exception as ex:
            print(f"[UI] Erro ao processar RFID: {ex}")

    # =========================================================================
    # Layout Base e Barra Superior / Inferior (Otimizado para Vertical 20:9)
    # =========================================================================
    def _montar_layout_base(self):
        self.lbl_usuario_topo = ft.Text("Desconectado", size=10, color="#BFDBFE", no_wrap=True)
        self.btn_sair_topo = ft.TextButton(
            "Sair",
            on_click=lambda e: self.fazer_logout(),
            visible=False,
        )

        header = ft.Container(
            bgcolor=MULTILOG_NAVY,
            padding=_pad_sym(10, 7),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row(
                        spacing=8,
                        expand=True,
                        controls=[
                            self.badge_usuario_header,
                            ft.Column(
                                spacing=1,
                                controls=[
                                    ft.Text("MULTILOG", size=14, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                                    self.lbl_usuario_topo,
                                ],
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=4,
                        controls=[
                            ft.Container(
                                bgcolor=MULTILOG_NAVY_DARK,
                                border_radius=8,
                                padding=_pad_sym(7, 4),
                                on_click=lambda e: self.abrir_modal_hardware(),
                                content=ft.Row(
                                    spacing=4,
                                    controls=[self.txt_hw_topo, self.txt_peso_topo],
                                ),
                            ),
                            self.btn_sair_topo,
                        ],
                    ),
                ],
            ),
        )

        self.page.add(
            ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    header,
                    self.container_principal,
                    self.wrapper_navegacao,
                ],
            )
        )

    def _ir_para_aba_ordens(self):
        if self.os_ativa is not None:
            self.navegar("executar_os")
        else:
            self.navegar("ordens")

    def _atualizar_barra_navegacao(self):
        if not self.funcionario_id:
            self.wrapper_navegacao.visible = False
            return

        self.wrapper_navegacao.visible = True
        self.barra_navegacao.controls.clear()

        if self.usuario_role == "ADMIN":
            destinos = [
                ("admin", "📊", lambda e: self.navegar("admin")),
                ("estoque", "🗄️", lambda e: self.navegar("estoque")),
                ("ordens", "📋", lambda e: self._ir_para_aba_ordens()),
                ("usuarios", "👥", lambda e: self.navegar("usuarios")),
                ("diario", "📜", lambda e: self.navegar("diario")),
            ]
        else:
            lbl_os = f"📋 O.S. (#{self.os_ativa['id']})" if self.os_ativa else "📋 Minhas O.S."
            lbl_est = "🗄️ Estante 🟢" if (self.os_ativa and self.slot_ativo_os) else "🗄️ Estante"
            destinos = [
                ("ordens", lbl_os, lambda e: self._ir_para_aba_ordens()),
                ("estoque", lbl_est, lambda e: self.navegar("estoque")),
            ]

        for chave, rotulo, acao in destinos:
            ativo = (self.aba_atual == chave) or (chave == "ordens" and self.aba_atual == "executar_os")
            self.barra_navegacao.controls.append(
                _btn(
                    rotulo,
                    on_click=acao,
                    bgcolor=MULTILOG_NAVY if ativo else "#E2E8F0",
                    color="#FFFFFF" if ativo else TEXT_MAIN,
                    expand=True,
                    height=38,
                    font_size=14 if self.usuario_role == "ADMIN" else 12,
                )
            )

    def navegar(self, destino: str):
        self.aba_atual = destino
        if destino != "usuarios":
            self.callback_rfid_tela_usuarios = None
        self._atualizar_barra_navegacao()
        self.renderizar_tela_atual()

    def renderizar_tela_atual(self):
        self._slot_ativo_container = None
        self._slot_ativo_dot_lbl = None
        self._atualizar_barra_navegacao()

        if self.aba_atual == "login":
            self.container_principal.content = self._construir_tela_login()
        elif self.aba_atual == "estoque":
            self.container_principal.content = self._construir_tela_estoque()
        elif self.aba_atual == "ordens":
            self.container_principal.content = self._construir_tela_ordens()
        elif self.aba_atual == "executar_os":
            self.container_principal.content = self._construir_tela_executar_os()
        elif self.aba_atual == "admin":
            self.container_principal.content = self._construir_tela_admin()
        elif self.aba_atual == "usuarios":
            self.container_principal.content = self._construir_tela_usuarios()
        elif self.aba_atual == "diario":
            self.container_principal.content = construir_tela_diario(self.page, self.mostrar_snackbar)
        self.page.update()

    # =========================================================================
    # Modal de Configuração Wi-Fi do ESP32 + Simulador Integrado
    # =========================================================================
    def abrir_modal_hardware(self):
        tf_ip = ft.TextField(
            label="IP do ESP32 (Wi-Fi)",
            value=self.hw.host_ativo,
            hint_text="Ex: 192.168.1.50 ou 192.168.4.1",
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            expand=True,
        )
        tf_sim_peso = ft.TextField(
            label="Simular Peso (g)",
            value=f"{self.hw.ler_ultimo_peso():.1f}",
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            expand=True,
        )
        tf_sim_rfid = ft.TextField(
            label="Simular Tag RFID",
            value="C4 AE 78 E5",
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            expand=True,
        )
        lbl_status_conexao = ft.Text(self.hw.mensagem_status, size=11, weight=ft.FontWeight.BOLD, color=MULTILOG_NAVY)

        def conectar_ip(e):
            ok = self.hw.conectar(tf_ip.value.strip())
            lbl_status_conexao.value = self.hw.mensagem_status
            self.txt_hw_topo.value = "🟢ESP32" if ok else "🟡Simul."
            self.mostrar_snackbar(
                f"Conectado ao ESP32 ({self.hw.host_ativo})!" if ok else f"Sem resposta de {self.hw.host_ativo}. Modo Simulador.",
                erro=not ok,
            )
            self.page.update()

        def aplicar_peso_simulado(e):
            try:
                val = float(tf_sim_peso.value.replace(",", ".").strip())
                self.hw.simular_peso(val)
                self.mostrar_snackbar(f"Peso simulado: {val:.1f}g")
            except ValueError:
                self.mostrar_snackbar("Digite um peso numérico válido.", erro=True)

        def disparar_rfid_simulado(tag_val: Optional[str] = None):
            tag = (tag_val or tf_sim_rfid.value or "").strip()
            if tag:
                fechar()
                self.hw.simular_leitura_rfid(tag)

        def fechar(e=None):
            self.fechar_dialogo(dlg)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("📡 ESP32 Wi-Fi, LCD 16x2 & Buzzer", size=14, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=310,
                content=ft.Column(
                    tight=True,
                    spacing=7,
                    controls=[
                        lbl_status_conexao,
                        ft.Text(
                            f"IP Local do App: {self.hw.obter_ip_local()}:{self.hw.http_port} (Descoberta automática ativa)",
                            size=10,
                            color=TEXT_MUTED,
                        ),
                        ft.Row(controls=[tf_ip]),
                        ft.Row(
                            spacing=6,
                            controls=[
                                _btn("Conectar", on_click=conectar_ip, expand=True, height=34),
                                _btn("⚖️ Tara", on_click=lambda e: (self.hw.tarar_balanca(), self.mostrar_snackbar("TARA enviada!")), bgcolor=MULTILOG_CYAN, expand=True, height=34),
                            ],
                        ),
                        ft.Row(
                            spacing=6,
                            controls=[
                                _btn(
                                    "💡 Apagar LEDs",
                                    on_click=lambda e: (hardware_mock.apagar_led(), self.mostrar_snackbar("LEDs apagados.")),
                                    bgcolor="#475569",
                                    expand=True,
                                    height=32,
                                ),
                                _btn(
                                    "🔊 Buzzer D2",
                                    on_click=lambda e: (hardware_mock.tocar_buzzer_erro(), self.mostrar_snackbar("Alerta sonoro enviado ao pino D2!")),
                                    bgcolor=ACCENT_ROSE,
                                    expand=True,
                                    height=32,
                                ),
                            ],
                        ),
                        ft.Divider(height=1),
                        ft.Text("Simulador (Testar sem bancada)", size=11, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                        ft.Row(
                            spacing=6,
                            controls=[
                                tf_sim_peso,
                                _btn("Peso", on_click=aplicar_peso_simulado, bgcolor=ACCENT_EMERALD, height=34),
                            ],
                        ),
                        ft.Row(
                            spacing=6,
                            controls=[
                                tf_sim_rfid,
                                _btn("Tag", on_click=lambda e: disparar_rfid_simulado(), bgcolor=MULTILOG_BLUE, height=34),
                            ],
                        ),
                        ft.Row(
                            spacing=4,
                            controls=[
                                _btn("🏷️ Crachá ADM", on_click=lambda e: disparar_rfid_simulado("C4 AE 78 E5"), bgcolor="#FEF3C7", color="#B45309", expand=True, height=34, font_size=11),
                                _btn("🏷️ Crachá OP", on_click=lambda e: disparar_rfid_simulado("47 09 9E A3"), bgcolor="#E0F2FE", color=MULTILOG_NAVY, expand=True, height=34, font_size=11),
                            ],
                        ),
                    ],
                ),
            ),
            actions=[ft.TextButton("Fechar", on_click=fechar)],
        )
        self.abrir_dialogo(dlg)

    # =========================================================================
    # Tela 1: Login Mobile (Vertical 20:9 + Login por Crachá RFID)
    # =========================================================================
    def _construir_tela_login(self) -> ft.Control:
        tf_id = ft.TextField(
            hint_text="Digite seu ID ou Tag RFID",
            text_align=ft.TextAlign.CENTER,
            text_size=15,
            dense=True,
            bgcolor=BG_ELEVATED,
            border_color="#CBD5E1",
            border_radius=10,
        )

        def add_digito(d: str):
            tf_id.value = (tf_id.value or "") + d
            self.page.update()

        def limpar():
            tf_id.value = ""
            self.page.update()

        def backspace():
            val = tf_id.value or ""
            tf_id.value = val[:-1]
            self.page.update()

        def preset(val: str):
            tf_id.value = val
            self.page.update()

        def confirmar_login(e=None):
            fid = (tf_id.value or "").strip()
            if not fid:
                self.mostrar_snackbar("Informe o ID do Operador ou aproxime o crachá RFID.", erro=True)
                return
            user = database.get_usuario(fid)
            if not user:
                hardware_mock.tocar_buzzer_erro()
                self.mostrar_snackbar(f"Matrícula ou Tag '{fid}' não cadastrada.", erro=True)
                return

            self._autenticar_usuario(user)

        linhas_teclado = [
            [("1", lambda e: add_digito("1")), ("2", lambda e: add_digito("2")), ("3", lambda e: add_digito("3"))],
            [("4", lambda e: add_digito("4")), ("5", lambda e: add_digito("5")), ("6", lambda e: add_digito("6"))],
            [("7", lambda e: add_digito("7")), ("8", lambda e: add_digito("8")), ("9", lambda e: add_digito("9"))],
            [("Limpar", lambda e: limpar()), ("0", lambda e: add_digito("0")), ("⌫", lambda e: backspace())],
        ]

        grid_teclado = ft.Column(spacing=5)
        for linha in linhas_teclado:
            row_ctrl = ft.Row(spacing=5)
            for texto, acao in linha:
                row_ctrl.controls.append(
                    _btn(
                        texto,
                        on_click=acao,
                        bgcolor="#FFFFFF",
                        color=TEXT_MAIN,
                        expand=True,
                        height=38,
                        font_size=13,
                    )
                )
            grid_teclado.controls.append(row_ctrl)

        card_login = ft.Container(
            width=342,
            bgcolor=BG_CARD,
            border=_border_all(1, "#CBD5E1"),
            border_radius=14,
            content=ft.Column(
                spacing=0,
                tight=True,
                controls=[
                    ft.Container(
                        bgcolor=MULTILOG_NAVY,
                        padding=12,
                        border_radius=ft.BorderRadius(top_left=13, top_right=13, bottom_left=0, bottom_right=0)
                        if hasattr(ft, "BorderRadius")
                        else 12,
                        alignment=_align_center(),
                        content=ft.Column(
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=2,
                            controls=[
                                ft.Text("💼 Identificação do Operador", size=16, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                                ft.Text("Aproxime o crachá RFID ou digite seu ID", size=11, color="#BFDBFE"),
                            ],
                        ),
                    ),
                    ft.Container(
                        padding=12,
                        content=ft.Column(
                            spacing=7,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                            controls=[
                                tf_id,
                                grid_teclado,
                                ft.Row(
                                    spacing=6,
                                    controls=[
                                        _btn("👤 Operador (1001)", on_click=lambda e: preset("1001"), bgcolor="#E0F2FE", color=MULTILOG_NAVY, expand=True, height=36, font_size=11),
                                        _btn("⚡ Admin (1000)", on_click=lambda e: preset("1000"), bgcolor="#FEF3C7", color="#B45309", expand=True, height=36, font_size=11),
                                    ],
                                ),
                                _btn("ACESSAR SISTEMA", on_click=confirmar_login, bgcolor=MULTILOG_NAVY, color="#FFFFFF", height=42, font_size=13),
                                ft.Container(
                                    bgcolor="#F0F9FF",
                                    border=_border_all(1, "#BAE6FD"),
                                    border_radius=8,
                                    padding=7,
                                    content=ft.Column(
                                        spacing=5,
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        controls=[
                                            ft.Text("📡 Login Instantâneo por Crachá RFID", size=10, weight=ft.FontWeight.BOLD, color="#0284C7"),
                                            ft.Row(
                                                spacing=6,
                                                controls=[
                                                    _btn("🏷️ Crachá OP", on_click=lambda e: self.hw.simular_leitura_rfid("47 09 9E A3"), bgcolor="#FFFFFF", color=MULTILOG_NAVY, expand=True, height=34, font_size=11),
                                                    _btn("🏷️ Crachá ADM", on_click=lambda e: self.hw.simular_leitura_rfid("C4 AE 78 E5"), bgcolor="#FFFFFF", color="#B45309", expand=True, height=34, font_size=11),
                                                ],
                                            ),
                                        ],
                                    ),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

        return ft.Container(
            expand=True,
            alignment=_align_center(),
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[card_login],
            ),
        )

    def fazer_logout(self):
        hardware_mock.apagar_led()
        self.funcionario_id = ""
        self.usuario_nome = ""
        self.usuario_role = ""
        self.usuario_foto_path = ""
        self.usuario_foto_blob = None
        self.os_ativa = None
        self.item_os_selecionado = None
        self.slot_ativo_os = None
        self.slot_selecionado = None
        self.rfid_os_validado = False
        self._atualizar_badge_header()
        self.navegar("login")

    # =========================================================================
    # Tela 2: Estante Pick-to-Light (Vertical 20:9 Responsiva)
    # =========================================================================
    def _construir_tela_estoque(self) -> ft.Control:
        modo_os = self.esta_em_modo_os_estante()

        mapa_pendentes_os: Dict[int, Dict[str, Any]] = {}
        if self.os_ativa:
            self.estante_ativa_id = self.os_ativa.get("estante_id") or self.estante_ativa_id
            itens_atuais = database.get_itens_ordem_servico(self.os_ativa["id"])
            for it in itens_atuais:
                rest = it.get("quantidade_restante", it["quantidade"] - it.get("quantidade_atendida", 0))
                if rest > 0:
                    mapa_pendentes_os[it["peca_id"]] = it

            if self.item_os_selecionado:
                it_refresh = next((i for i in itens_atuais if i["id"] == self.item_os_selecionado["id"]), None)
                if not it_refresh or it_refresh["quantidade_restante"] == 0:
                    prox = next((i for i in itens_atuais if i["quantidade_restante"] > 0), None)
                    self.selecionar_item_os(prox, atualizar_tela=False)
                else:
                    self.item_os_selecionado = it_refresh
            else:
                prox = next((i for i in itens_atuais if i["quantidade_restante"] > 0), None)
                if prox:
                    self.selecionar_item_os(prox, atualizar_tela=False)

        estantes = database.get_todas_estantes()
        estante_atual = database.get_estante(self.estante_ativa_id) or (
            estantes[0] if estantes else {"id": 1, "nome": "Estante A", "linhas": 2, "colunas": 3}
        )
        self.estante_ativa_id = estante_atual["id"]

        linhas = int(estante_atual["linhas"])
        colunas = int(estante_atual["colunas"])
        compacto = (colunas >= 4)  # Adapta células automaticamente se for 5x5 numa tela estreita 20:9
        pecas = database.get_pecas_por_estante(self.estante_ativa_id)
        mapa_pecas = {(p["posicao_linha"], p["posicao_coluna"]): p for p in pecas}

        if modo_os:
            if self.os_ativa:
                os_id = self.os_ativa["id"]
                os_tit = self.os_ativa["titulo"]
                barra_topo_estante = ft.Container(
                    bgcolor=MULTILOG_NAVY,
                    border_radius=10,
                    padding=10,
                    content=ft.Column(
                        spacing=2,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text(
                                        f"📋 O.S. #{os_id}: {os_tit}",
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                        color="#34D399",
                                        expand=True,
                                        no_wrap=True,
                                    ),
                                    ft.Text(
                                        f"📍 {estante_atual['nome']}",
                                        size=10,
                                        weight=ft.FontWeight.BOLD,
                                        color="#FFFFFF",
                                    ),
                                ],
                            ),
                            ft.Text(
                                "🔒 Siga a gaveta PISCANDO em verde · Outras posições bloqueadas",
                                size=10,
                                color="#BFDBFE",
                            ),
                        ],
                    ),
                )
            else:
                barra_topo_estante = ft.Container(
                    bgcolor="#FEF3C7",
                    border=_border_all(1, ACCENT_AMBER),
                    border_radius=10,
                    padding=10,
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            ft.Text(
                                "ℹ️ Inicie uma O.S. em 'Minhas O.S.' para operar a estante.",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color="#B45309",
                            ),
                            _btn("Ir para Minhas O.S.", on_click=lambda e: self.navegar("ordens"), bgcolor=MULTILOG_NAVY, height=32),
                        ],
                    ),
                )
        else:
            dd_estante = ft.Dropdown(
                label="Estante Ativa",
                value=str(self.estante_ativa_id),
                expand=True,
                dense=True,
                text_size=12,
                bgcolor=BG_CARD,
                options=[_opt(str(e["id"]), f"{e['nome']} ({e['linhas']}x{e['colunas']})") for e in estantes],
            )

            def ao_mudar_estante(e):
                if dd_estante.value:
                    self.estante_ativa_id = int(dd_estante.value)
                    self.slot_selecionado = None
                    hardware_mock.apagar_led()
                    self.renderizar_tela_atual()

            dd_estante.on_change = ao_mudar_estante
            barra_topo_estante = ft.Row(
                spacing=4,
                controls=[
                    dd_estante,
                    _btn("+ Nova", on_click=lambda e: self.abrir_modal_estante(editar=False), bgcolor=MULTILOG_NAVY, height=36),
                    _btn("⚙️", on_click=lambda e: self.abrir_modal_estante(editar=True), bgcolor="#475569", height=36),
                ],
            )

        # Constrói matriz de gavetas adaptada para largura 20:9
        matriz_col = ft.Column(spacing=4 if compacto else 6)
        for r in range(linhas):
            row_slots = ft.Row(spacing=4 if compacto else 6)
            for c in range(colunas):
                peca = mapa_pecas.get((r, c))
                eh_slot_ativo_os = modo_os and (self.slot_ativo_os == (r, c))
                item_pendente_gaveta = mapa_pendentes_os.get(peca["id"]) if (modo_os and peca) else None
                selecionado_livre = (not modo_os) and (self.slot_selecionado == (r, c))

                dot_lbl = ft.Text("●", size=8 if compacto else 9, weight=ft.FontWeight.BOLD)

                if peca:
                    qtd = peca["quantidade_estoque"]
                    baixo_estoque = qtd <= 5

                    if eh_slot_ativo_os:
                        bg = "#DCFCE7"
                        borda = _border_all(3, "#22C55E")
                        dot_lbl.value = "●ATIVO" if not compacto else "●"
                        dot_lbl.color = "#15803D"
                    elif item_pendente_gaveta:
                        bg = "#E0F2FE"
                        borda = _border_all(2, "#2563EB")
                        dot_lbl.value = "●O.S." if not compacto else "●"
                        dot_lbl.color = MULTILOG_CYAN
                    elif selecionado_livre:
                        bg = "#E0F2FE"
                        borda = _border_all(2, MULTILOG_CYAN)
                        dot_lbl.value = "●LED" if not compacto else "●"
                        dot_lbl.color = "#10B981"
                    elif baixo_estoque and not modo_os:
                        bg = "#FEF3C7"
                        borda = _border_all(1, ACCENT_AMBER)
                        dot_lbl.value = "●"
                        dot_lbl.color = "#D97706"
                    else:
                        bg = "#F8FAFC" if modo_os else MULTILOG_LIGHT_BLUE
                        borda = _border_all(1, BORDER_SUBTLE if modo_os else MULTILOG_BORDER_BLUE)
                        dot_lbl.value = "🔒" if modo_os else "●"
                        dot_lbl.color = TEXT_SUBTLE if modo_os else MULTILOG_BLUE

                    if item_pendente_gaveta:
                        qtd_rest_os = item_pendente_gaveta["quantidade_restante"]
                        txt_b = f"QTD:{qtd_rest_os}" if compacto else f"{'RET' if item_pendente_gaveta['tipo_operacao']=='REMOCAO' else 'ADD'}: {qtd_rest_os}"
                        badge_dir = ft.Container(
                            bgcolor="#15803D" if eh_slot_ativo_os else MULTILOG_NAVY,
                            border_radius=4,
                            padding=_pad_sym(4, 1),
                            content=ft.Text(txt_b, size=8 if compacto else 9, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                        )
                    else:
                        badge_dir = ft.Container(
                            bgcolor="#334155",
                            border_radius=4,
                            padding=_pad_sym(4, 1),
                            content=ft.Text(f"{qtd}u", size=8 if compacto else 9, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                        )

                    conteudo_card = ft.Column(
                        spacing=2,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text(f"L{r+1}C{c+1}", size=8 if compacto else 9, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                                    dot_lbl,
                                ],
                            ),
                            ft.Text(peca["nome"], size=10 if compacto else 12, weight=ft.FontWeight.BOLD, color=TEXT_MAIN, no_wrap=True),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    badge_dir,
                                ],
                            ),
                        ],
                    )
                else:
                    bg = "#E0F2FE" if selecionado_livre else BG_CARD
                    borda = _border_all(2 if selecionado_livre else 1, MULTILOG_CYAN if selecionado_livre else BORDER_SUBTLE)
                    dot_lbl.value = "🔒" if modo_os else "○"
                    dot_lbl.color = TEXT_SUBTLE
                    conteudo_card = ft.Column(
                        spacing=2,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text(f"L{r+1}C{c+1}", size=8 if compacto else 9, color=TEXT_SUBTLE),
                                    dot_lbl,
                                ],
                            ),
                            ft.Text("Vazio", size=9 if compacto else 11, weight=ft.FontWeight.BOLD, color=TEXT_MUTED, no_wrap=True),
                            ft.Text("🔒" if modo_os else "+", size=8 if compacto else 9, color=TEXT_SUBTLE),
                        ],
                    )

                card_slot = ft.Container(
                    expand=True,
                    bgcolor=bg,
                    border=borda,
                    border_radius=8,
                    padding=5 if compacto else 8,
                    on_click=lambda e, rr=r, cc=c: self.tentar_selecionar_gaveta_estante(rr, cc),
                    content=conteudo_card,
                )

                if eh_slot_ativo_os:
                    self._slot_ativo_container = card_slot
                    self._slot_ativo_dot_lbl = dot_lbl

                row_slots.controls.append(card_slot)
            matriz_col.controls.append(row_slots)

        if modo_os:
            painel_inferior = self._construir_painel_terminal_os_ativo()
        else:
            painel_inferior = self._construir_painel_gaveta_selecionada(mapa_pecas)

        legenda_texto = (
            "🟢 Piscando = Atual | 🔵 O.S. | 🔒 Bloqueada"
            if modo_os
            else "Toque na gaveta para acender o LED"
        )

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=8,
            controls=[
                barra_topo_estante,
                ft.Container(
                    bgcolor=BG_CARD,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=12,
                    padding=8,
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text(f"{estante_atual['nome']} ({linhas}×{colunas})", size=12, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                    ft.Text(legenda_texto, size=9, color=TEXT_MUTED),
                                ],
                            ),
                            matriz_col,
                        ],
                    ),
                ),
                painel_inferior,
            ],
        )

    def _construir_painel_terminal_os_ativo(self) -> ft.Control:
        """
        Terminal de Conferência e Balança compacto para tela vertical 20:9.
        Implementa o fluxo obrigatório de 2 etapas (igual ao PC):
          1º Ler e validar a Tag RFID da peça -> 2º Liberar e validar a pesagem na balança.
        """
        if not self.os_ativa:
            return ft.Container(
                bgcolor=BG_CARD,
                border=_border_all(1, BORDER_SUBTLE),
                border_radius=10,
                padding=12,
                content=ft.Text(
                    "🔒 Gavetas bloqueadas. Abra 'Minhas O.S.' na barra inferior para iniciar uma Ordem de Serviço.",
                    size=11,
                    color=TEXT_MUTED,
                ),
            )

        ordem_id = self.os_ativa["id"]
        itens = database.get_itens_ordem_servico(ordem_id)

        if not self.item_os_selecionado:
            return ft.Container(
                bgcolor="#ECFDF5",
                border=_border_all(2, ACCENT_EMERALD),
                border_radius=10,
                padding=12,
                content=ft.Column(
                    spacing=6,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("✓ O.S. 100% ATENDIDA!", size=14, weight=ft.FontWeight.BOLD, color="#065F46"),
                        ft.Text("Todas as posições foram validadas com RFID e balança.", size=11, color=TEXT_MUTED),
                        _btn("✓ Concluir O.S. ▶", on_click=lambda e: self._finalizar_os_ativa(), bgcolor=MULTILOG_NAVY, height=40),
                    ],
                ),
            )

        item_atual = next((x for x in itens if x["id"] == self.item_os_selecionado["id"]), self.item_os_selecionado)
        peca_sel = database.get_peca(item_atual["peca_id"])
        rest = item_atual.get("quantidade_restante", max(0, item_atual["quantidade"] - item_atual.get("quantidade_atendida", 0)))

        if not peca_sel or rest <= 0:
            return ft.Container()

        r = peca_sel["posicao_linha"]
        c = peca_sel["posicao_coluna"]
        eh_remocao = item_atual["tipo_operacao"] == "REMOCAO"
        acao_txt = f"↓ RETIRAR {rest} UN DE L{r+1}·C{c+1}" if eh_remocao else f"↑ ADICIONAR {rest} UN EM L{r+1}·C{c+1}"
        cor_banner_bg = "#FEE2E2" if eh_remocao else "#ECFDF5"
        cor_banner_txt = "#991B1B" if eh_remocao else "#065F46"

        peso_u = float(peca_sel["peso_unitario_g"])
        peso_esp_total = rest * peso_u
        tf_qtd_exec = ft.TextField(label="Qtd.", value=str(rest), dense=True, text_size=12, bgcolor=BG_ELEVATED, expand=True)
        peso_lido_ini = self.hw.ler_ultimo_peso() if self.hw.ler_ultimo_peso() > 0 else (peso_esp_total if self.rfid_os_validado else 0.0)
        tf_peso_exec = ft.TextField(
            label="Peso Balança (g)",
            value=f"{peso_lido_ini:.1f}",
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            expand=True,
            disabled=(self.rfid_os_obrigatorio and not self.rfid_os_validado),
        )
        self.campo_peso_modal_ativo = tf_peso_exec

        # Pílulas visuais das 2 etapas obrigatórias (1º RFID -> 2º Pesagem)
        step1_ok = not self.rfid_os_obrigatorio or self.rfid_os_validado
        pill_step1 = ft.Container(
            expand=True,
            bgcolor="#ECFDF5" if step1_ok else "#0F243A",
            border=_border_all(1, ACCENT_EMERALD if step1_ok else MULTILOG_CYAN),
            border_radius=8,
            padding=_pad_sym(6, 5),
            alignment=_align_center(),
            content=ft.Text(
                "1º ✓ RFID OK" if step1_ok else "1º 🏷️ LER RFID",
                size=10,
                weight=ft.FontWeight.BOLD,
                color="#059669" if step1_ok else "#38BDF8",
                no_wrap=True,
            ),
        )
        pill_step2 = ft.Container(
            expand=True,
            bgcolor="#0F243A" if step1_ok else "#F1F5F9",
            border=_border_all(1, MULTILOG_CYAN if step1_ok else "#CBD5E1"),
            border_radius=8,
            padding=_pad_sym(6, 5),
            alignment=_align_center(),
            content=ft.Text(
                "2º ⚖️ PESAR" if step1_ok else "2º 🔒 BALANÇA",
                size=10,
                weight=ft.FontWeight.BOLD,
                color="#38BDF8" if step1_ok else TEXT_MUTED,
                no_wrap=True,
            ),
        )

        def simular_peso_alvo(e):
            if self.rfid_os_obrigatorio and not self.rfid_os_validado:
                hardware_mock.tocar_buzzer_erro()
                self.mostrar_snackbar(
                    f"⚠️ Passo 1 Pendente: Leia primeiro a tag RFID de '{peca_sel['nome']}' antes de pesar!",
                    erro=True,
                )
                return
            tf_peso_exec.value = f"{peso_esp_total:.1f}"
            self.page.update()

        def registrar_item_os(e):
            if self.rfid_os_obrigatorio and not self.rfid_os_validado:
                hardware_mock.tocar_buzzer_erro()
                self.mostrar_snackbar(
                    f"⚠️ Passo 1 Obrigatório: Aproxime a tag RFID de '{peca_sel['nome']}' (ou toque em '1. Ler RFID') antes de confirmar!",
                    erro=True,
                )
                return

            try:
                q_mov = int(tf_qtd_exec.value.strip())
                p_lido = float(tf_peso_exec.value.replace(",", ".").strip())
            except ValueError:
                hardware_mock.tocar_buzzer_erro()
                self.mostrar_snackbar("Quantidade ou peso inválido.", erro=True)
                return

            ok_val, msg_val = logic.validar_operacao_os(
                item_atual,
                item_atual["tipo_operacao"],
                q_mov,
                peca_sel["quantidade_estoque"],
            )
            if not ok_val:
                hardware_mock.tocar_buzzer_erro()
                self.mostrar_snackbar(msg_val, erro=True)
                return

            if not logic.validar_peso(p_lido, peso_u, q_mov):
                hardware_mock.tocar_buzzer_erro()
                self.mostrar_snackbar(
                    f"Divergência! Esperado ~{q_mov * peso_u:.1f}g (±5%), lido {p_lido:.1f}g.",
                    erro=True,
                )
                return

            delta = q_mov if item_atual["tipo_operacao"] == "ADICAO" else -q_mov
            database.update_estoque(peca_sel["id"], delta)
            database.atualizar_progresso_item_os(item_atual["id"], q_mov)
            database.registrar_operacao(
                self.funcionario_id,
                peca_sel["id"],
                item_atual["tipo_operacao"],
                q_mov,
                ordem_id=ordem_id,
                qtd_planejada=item_atual["quantidade"],
            )
            hardware_mock.apagar_led()

            novos_itens = database.get_itens_ordem_servico(ordem_id)
            prox = next((i for i in novos_itens if i["quantidade_restante"] > 0), None)
            self.selecionar_item_os(prox, atualizar_tela=True)
            self.mostrar_snackbar(f"✓ L{r+1}·C{c+1} confirmada ({q_mov} un)!")

        return ft.Container(
            bgcolor=BG_CARD,
            border=_border_all(2, "#22C55E"),
            border_radius=12,
            padding=10,
            content=ft.Column(
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                f"📍 PISCANDO: L{r+1}·C{c+1} · {peca_sel['nome']}",
                                size=13,
                                weight=ft.FontWeight.BOLD,
                                color=MULTILOG_NAVY,
                                expand=True,
                            ),
                            ft.Text(f"#{peca_sel['id']}", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                        ],
                    ),
                    ft.Container(
                        bgcolor=cor_banner_bg,
                        border_radius=8,
                        padding=7,
                        alignment=_align_center(),
                        content=ft.Text(acao_txt, size=12, weight=ft.FontWeight.BOLD, color=cor_banner_txt),
                    ),
                    ft.Row(spacing=4, controls=[pill_step1, pill_step2]),
                    ft.Text(
                        f"Est: {peca_sel['quantidade_estoque']} un | Unit: {peso_u:.1f}g | Alvo: {peso_esp_total:.1f}g (±5%)",
                        size=10,
                        color=TEXT_MUTED,
                    ),
                    ft.Row(spacing=6, controls=[tf_qtd_exec, tf_peso_exec]),
                    ft.Row(
                        spacing=4,
                        controls=[
                            _btn(
                                "🏷️ 1. Ler RFID",
                                on_click=lambda e: self.simular_leitura_rfid_item_os_ativo(),
                                bgcolor="#E0F2FE",
                                color="#0369A1",
                                expand=True,
                                height=36,
                                font_size=11,
                            ),
                            _btn(
                                "⚖️ 2. Pesar",
                                on_click=simular_peso_alvo,
                                bgcolor="#DCFCE7" if step1_ok else "#E2E8F0",
                                color="#15803D" if step1_ok else TEXT_MUTED,
                                expand=True,
                                height=36,
                                font_size=11,
                            ),
                            _btn(
                                "Zero",
                                on_click=lambda e: (self.hw.tarar_balanca(), setattr(tf_peso_exec, "value", "0.0"), self.page.update()),
                                bgcolor="#F1F5F9",
                                color=TEXT_MAIN,
                                width=54,
                                height=36,
                                font_size=11,
                            ),
                        ],
                    ),
                    _btn(
                        "CONFIRMAR E AVANÇAR ▶",
                        on_click=registrar_item_os,
                        bgcolor=MULTILOG_NAVY if step1_ok else "#94A3B8",
                        height=40,
                        font_size=12,
                    ),
                ],
            ),
        )

    def _construir_painel_gaveta_selecionada(self, mapa_pecas: Dict[tuple, Dict[str, Any]]) -> ft.Control:
        if not self.slot_selecionado:
            return ft.Container(
                bgcolor=BG_CARD,
                border=_border_all(1, BORDER_SUBTLE),
                border_radius=10,
                padding=12,
                content=ft.Text("👆 Toque em uma gaveta acima (ou aproxime uma tag RFID) para operar.", size=11, color=TEXT_MUTED),
            )

        r, c = self.slot_selecionado
        peca = mapa_pecas.get((r, c))

        if not peca:
            return ft.Container(
                bgcolor=BG_CARD,
                border=_border_all(1, MULTILOG_BORDER_BLUE),
                border_radius=10,
                padding=12,
                content=ft.Column(
                    spacing=6,
                    controls=[
                        ft.Text(f"Gaveta L{r+1}·C{c+1} Vazia (LED Aceso)", size=13, weight=ft.FontWeight.BOLD, color=MULTILOG_NAVY),
                        _btn("➕ Cadastrar Peça aqui", on_click=lambda e: self.abrir_modal_cadastro_peca(r, c), bgcolor=MULTILOG_NAVY, height=36),
                    ],
                ),
            )

        return ft.Container(
            bgcolor=BG_CARD,
            border=_border_all(2, MULTILOG_CYAN),
            border_radius=10,
            padding=12,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=1,
                                expand=True,
                                controls=[
                                    ft.Text(f"L{r+1}·C{c+1} · {peca['nome']} (#{peca['id']})", size=13, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                    ft.Text(f"{peca['tipo']} | {peca['peso_unitario_g']}g | {peca['dimensoes']}", size=10, color=TEXT_MUTED),
                                    ft.Text(f"RFID: {peca.get('rfid_uid') or 'S/ Tag'}", size=10, color=MULTILOG_BLUE),
                                ],
                            ),
                            ft.Container(
                                bgcolor=MULTILOG_NAVY,
                                border_radius=8,
                                padding=_pad_sym(10, 6),
                                content=ft.Text(f"{peca['quantidade_estoque']} un", size=13, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=6,
                        controls=[
                            _btn("➕ Entrada", on_click=lambda e: self.abrir_modal_movimentacao_estoque(peca, "ADICAO"), bgcolor=ACCENT_EMERALD, expand=True, height=34),
                            _btn("➖ Retirada", on_click=lambda e: self.abrir_modal_movimentacao_estoque(peca, "REMOCAO"), bgcolor=MULTILOG_CYAN, expand=True, height=34),
                        ],
                    ),
                    ft.Row(
                        spacing=6,
                        controls=[
                            _btn("✏️ Editar", on_click=lambda e: self.abrir_modal_cadastro_peca(r, c, peca_existente=peca), bgcolor="#475569", expand=True, height=32),
                            _btn("🗑️ Excluir", on_click=lambda e: self.confirmar_exclusao_peca(peca), bgcolor=ACCENT_ROSE, expand=True, height=32),
                        ],
                    ),
                ],
            ),
        )

    def confirmar_exclusao_peca(self, peca: Dict[str, Any]):
        ok, msg = database.excluir_peca(peca["id"])
        self.mostrar_snackbar(msg, erro=not ok)
        if ok:
            hardware_mock.apagar_led()
            self.renderizar_tela_atual()

    def abrir_modal_movimentacao_estoque(self, peca: Dict[str, Any], tipo_op: str):
        titulo_op = "Entrada (+)" if tipo_op == "ADICAO" else "Retirada (-)"
        tf_qtd = ft.TextField(label="Quantidade (un)", value="1", dense=True, text_size=12, bgcolor=BG_ELEVATED)
        peso_unit = float(peca["peso_unitario_g"])
        peso_inicial = self.hw.ler_ultimo_peso() if self.hw.ler_ultimo_peso() > 0 else peso_unit
        tf_peso = ft.TextField(
            label="Peso na Balança (g)",
            value=f"{peso_inicial:.1f}",
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
        )
        self.campo_peso_modal_ativo = tf_peso
        lbl_esperado = ft.Text(f"Esperado (1 un): {peso_unit:.1f}g (±5%)", size=11, color=MULTILOG_NAVY, weight=ft.FontWeight.BOLD)

        def ao_mudar_qtd(e):
            try:
                q = max(1, int(tf_qtd.value or "1"))
                esp = q * peso_unit
                lbl_esperado.value = f"Esperado ({q} un): {esp:.1f}g (±5%)"
                if not self.hw.esta_conectado():
                    tf_peso.value = f"{esp:.1f}"
                self.page.update()
            except ValueError:
                pass

        tf_qtd.on_change = ao_mudar_qtd

        def confirmar(e):
            try:
                qtd = int(tf_qtd.value.strip())
                peso_lido = float(tf_peso.value.replace(",", ".").strip())
            except ValueError:
                hardware_mock.tocar_buzzer_erro()
                self.mostrar_snackbar("Informe quantidade e peso válidos.", erro=True)
                return

            dados_op = dict(peca)
            dados_op["quantidade"] = qtd
            sucesso, msg, _ = logic.processar_operacao(self.funcionario_id, dados_op, tipo_op, peso_informado=peso_lido)
            if not sucesso:
                hardware_mock.tocar_buzzer_erro()
            self.mostrar_snackbar(msg, erro=not sucesso)
            if sucesso:
                self.fechar_dialogo(dlg)
                self.renderizar_tela_atual()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{titulo_op} · {peca['nome']}", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=300,
                content=ft.Column(
                    tight=True,
                    spacing=8,
                    controls=[
                        ft.Text(f"Gaveta L{peca['posicao_linha']+1}·C{peca['posicao_coluna']+1} | Est: {peca['quantidade_estoque']} un", size=11, color=TEXT_MUTED),
                        tf_qtd,
                        lbl_esperado,
                        tf_peso,
                        _btn(
                            "🔄 Ler Balança ESP32",
                            on_click=lambda e: (setattr(tf_peso, "value", f"{self.hw.ler_ultimo_peso():.1f}"), self.page.update()),
                            bgcolor=MULTILOG_CYAN,
                            height=34,
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.fechar_dialogo(dlg)),
                _btn("Confirmar", on_click=confirmar, bgcolor=ACCENT_EMERALD if tipo_op == "ADICAO" else MULTILOG_NAVY, height=34),
            ],
        )
        self.abrir_dialogo(dlg)

    def abrir_modal_cadastro_peca(self, r: int, c: int, peca_existente: Optional[Dict[str, Any]] = None):
        editando = peca_existente is not None
        if editando:
            id_peca = peca_existente["id"]
        else:
            todas = database.get_todas_pecas()
            id_peca = max([p["id"] for p in todas], default=100) + 1

        tf_nome = ft.TextField(label="Nome da Peça *", value=peca_existente["nome"] if editando else "", dense=True, text_size=12, bgcolor=BG_ELEVATED)
        dd_tipo = ft.Dropdown(
            label="Categoria",
            value=peca_existente["tipo"] if editando else "Fixador",
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            options=[
                _opt("Fixador", "Fixador"),
                _opt("Parafuso", "Parafuso"),
                _opt("Porca", "Porca"),
                _opt("Arruela", "Arruela"),
                _opt("Elétrica", "Elétrica"),
                _opt("Mecânica", "Mecânica"),
                _opt("Pneumática", "Pneumática"),
                _opt("Hidráulica", "Hidráulica"),
                _opt("Outro", "Outro"),
            ],
        )
        tf_dim = ft.TextField(label="Dimensões", value=peca_existente["dimensoes"] if editando else "Padrão", dense=True, text_size=12, bgcolor=BG_ELEVATED)
        peso_sugerido = peca_existente["peso_unitario_g"] if editando else (self.hw.ler_ultimo_peso() if self.hw.ler_ultimo_peso() > 0 else 10.0)
        tf_peso_unit = ft.TextField(label="Peso Unit. (g) *", value=str(peso_sugerido), dense=True, text_size=12, bgcolor=BG_ELEVATED, expand=True)
        tf_rfid = ft.TextField(
            label="Tag RFID",
            value=peca_existente.get("rfid_uid", "") if editando else (self.hw.ultima_tag or ""),
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
        )
        tf_qtd_ini = ft.TextField(
            label="Qtd. Inicial",
            value=str(peca_existente["quantidade_estoque"]) if editando else "10",
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            disabled=editando,
        )

        self.campo_rfid_modal_ativo = tf_rfid
        self.campo_nome_modal_ativo = tf_nome
        self.campo_peso_modal_ativo = tf_peso_unit

        def salvar_peca(e):
            nome = (tf_nome.value or "").strip()
            if not nome:
                self.mostrar_snackbar("Informe o nome da peça.", erro=True)
                return
            try:
                peso_u = float((tf_peso_unit.value or "0").replace(",", ".").strip())
                qtd_i = int((tf_qtd_ini.value or "0").strip())
                if peso_u <= 0:
                    raise ValueError()
            except ValueError:
                self.mostrar_snackbar("Informe peso (> 0) e quantidade válidos.", erro=True)
                return

            dados = {
                "id": id_peca,
                "nome": nome,
                "tipo": dd_tipo.value or "Fixador",
                "posicao_linha": r,
                "posicao_coluna": c,
                "peso_unitario_g": peso_u,
                "dimensoes": (tf_dim.value or "Padrão").strip(),
                "estante_id": self.estante_ativa_id,
                "rfid_uid": database.formatar_rfid_uid(tf_rfid.value or ""),
                "descricao": "",
            }
            database.upsert_peca(dados)
            if not editando and qtd_i > 0:
                database.update_estoque(id_peca, qtd_i)
                database.registrar_operacao(self.funcionario_id, id_peca, "ADICAO", qtd_i)

            self.fechar_dialogo(dlg)
            self.mostrar_snackbar(f"Peça '{nome}' salva em L{r+1}·C{c+1}!")
            self.renderizar_tela_atual()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{'Editar' if editando else 'Nova Peça'} · L{r+1}·C{c+1}", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=300,
                content=ft.Column(
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                    spacing=6,
                    controls=[
                        tf_nome,
                        dd_tipo,
                        tf_dim,
                        ft.Row(
                            spacing=6,
                            controls=[
                                tf_peso_unit,
                                _btn("⚖️ Ler", on_click=lambda e: (setattr(tf_peso_unit, "value", f"{self.hw.ler_ultimo_peso():.1f}"), self.page.update()), bgcolor=MULTILOG_CYAN, height=34),
                            ],
                        ),
                        tf_rfid,
                        tf_qtd_ini,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.fechar_dialogo(dlg)),
                _btn("Salvar", on_click=salvar_peca, bgcolor=MULTILOG_NAVY, height=34),
            ],
        )
        self.abrir_dialogo(dlg)

    def abrir_modal_estante(self, editar: bool = False):
        estante_atual = database.get_estante(self.estante_ativa_id) if editar else None
        tf_nome = ft.TextField(label="Nome da Estante *", value=estante_atual["nome"] if estante_atual else "", dense=True, text_size=12, bgcolor=BG_ELEVATED)
        tf_linhas = ft.TextField(label="Linhas (1-10)", value=str(estante_atual["linhas"]) if estante_atual else "2", dense=True, text_size=12, bgcolor=BG_ELEVATED, expand=True)
        tf_colunas = ft.TextField(label="Colunas (1-10)", value=str(estante_atual["colunas"]) if estante_atual else "3", dense=True, text_size=12, bgcolor=BG_ELEVATED, expand=True)
        tf_desc = ft.TextField(label="Descrição", value=estante_atual.get("descricao", "") if estante_atual else "", dense=True, text_size=12, bgcolor=BG_ELEVATED)

        def salvar(e):
            nome = (tf_nome.value or "").strip()
            try:
                l = int(tf_linhas.value or "2")
                c = int(tf_colunas.value or "3")
            except ValueError:
                self.mostrar_snackbar("Dimensões inválidas.", erro=True)
                return

            try:
                if editar and estante_atual:
                    valido, conflitos = database.validar_redimensionamento_estante(estante_atual["id"], l, c)
                    if not valido:
                        self.mostrar_snackbar(f"Conflito: {', '.join(conflitos[:2])}", erro=True)
                        return
                    database.atualizar_estante(estante_atual["id"], nome, l, c, tf_desc.value or "")
                else:
                    novo_id = database.criar_estante(nome, l, c, tf_desc.value or "")
                    self.estante_ativa_id = novo_id
                self.fechar_dialogo(dlg)
                self.mostrar_snackbar("Estante salva!")
                self.renderizar_tela_atual()
            except Exception as ex:
                self.mostrar_snackbar(f"Erro: {ex}", erro=True)

        def excluir(e):
            if not estante_atual:
                return
            ok, msg = database.excluir_estante(estante_atual["id"])
            self.mostrar_snackbar(msg, erro=not ok)
            if ok:
                estantes_rest = database.get_todas_estantes()
                self.estante_ativa_id = estantes_rest[0]["id"] if estantes_rest else 1
                self.fechar_dialogo(dlg)
                self.renderizar_tela_atual()

        acoes = [ft.TextButton("Cancelar", on_click=lambda e: self.fechar_dialogo(dlg))]
        if editar:
            acoes.append(ft.TextButton("Excluir", on_click=excluir))
        acoes.append(_btn("Salvar", on_click=salvar, bgcolor=MULTILOG_NAVY, height=34))

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Configurar Estante" if editar else "Nova Estante", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=300,
                content=ft.Column(
                    tight=True,
                    spacing=8,
                    controls=[
                        tf_nome,
                        ft.Row(spacing=6, controls=[tf_linhas, tf_colunas]),
                        tf_desc,
                    ],
                ),
            ),
            actions=acoes,
        )
        self.abrir_dialogo(dlg)

    # =========================================================================
    # Tela 3: Lista de Ordens de Serviço e Execução Guiada (Vertical 20:9)
    # =========================================================================
    def _construir_tela_ordens(self) -> ft.Control:
        filtro_op = None if self.usuario_role == "ADMIN" else self.funcionario_id
        ordens = database.get_ordens_servico_abertas(filtro_op)

        lista = ft.Column(spacing=8)
        if not ordens:
            lista.controls.append(
                ft.Container(
                    bgcolor=BG_CARD,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=12,
                    padding=20,
                    alignment=_align_center(),
                    content=ft.Text("🎉 Nenhuma Ordem de Serviço pendente!", size=13, color=TEXT_MUTED),
                )
            )
        else:
            for o in ordens:
                itens = database.get_itens_ordem_servico(o["id"])
                tot_plan = sum(i["quantidade"] for i in itens)
                tot_atend = sum(i.get("quantidade_atendida", 0) for i in itens)
                estante = database.get_estante(o.get("estante_id", 1))
                nome_estante = estante["nome"] if estante else "Estante Padrão"

                lista.controls.append(
                    ft.Container(
                        bgcolor=BG_CARD,
                        border=_border_all(1, MULTILOG_BORDER_BLUE),
                        border_radius=12,
                        padding=12,
                        content=ft.Column(
                            spacing=6,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                            controls=[
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    controls=[
                                        ft.Text(f"O.S. #{o['id']} · {o['titulo']}", size=13, weight=ft.FontWeight.BOLD, color=TEXT_MAIN, expand=True),
                                        ft.Container(
                                            bgcolor="#DCEBFA",
                                            border_radius=6,
                                            padding=_pad_sym(7, 3),
                                            content=ft.Text(f"{tot_atend}/{tot_plan} un", size=10, weight=ft.FontWeight.BOLD, color=MULTILOG_NAVY),
                                        ),
                                    ],
                                ),
                                ft.Text(f"📍 {nome_estante} | ⏰ {o.get('prazo_limite') or '-'}", size=11, color=TEXT_MUTED),
                                _btn("▶️ Iniciar / Continuar O.S.", on_click=lambda e, x=o: self.iniciar_execucao_os(x), bgcolor=MULTILOG_NAVY, height=38, font_size=12),
                            ],
                        ),
                    )
                )

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=8,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text("Ordens de Serviço", size=16, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                        _btn("🔄 Atualizar", on_click=lambda e: self.renderizar_tela_atual(), bgcolor=MULTILOG_CYAN, height=32),
                    ],
                ),
                lista,
            ],
        )

    def _pausar_os_ativa(self):
        hardware_mock.apagar_led()
        self.os_ativa = None
        self.item_os_selecionado = None
        self.slot_ativo_os = None
        self.rfid_os_validado = False
        self.navegar("ordens")

    def _finalizar_os_ativa(self):
        if not self.os_ativa:
            return
        ordem_id = self.os_ativa["id"]
        status_final = database.concluir_ordem_servico(ordem_id)
        hardware_mock.apagar_led()
        self.mostrar_snackbar(f"O.S. #{ordem_id} encerrada: {status_final}")
        self.os_ativa = None
        self.item_os_selecionado = None
        self.slot_ativo_os = None
        self.rfid_os_validado = False
        self.navegar("ordens")

    def _construir_tela_executar_os(self) -> ft.Control:
        if not self.os_ativa:
            return self._construir_tela_ordens()

        ordem_id = self.os_ativa["id"]
        itens = database.get_itens_ordem_servico(ordem_id)
        tot_plan = sum(i["quantidade"] for i in itens)
        tot_atend = sum(i.get("quantidade_atendida", 0) for i in itens)

        cards_itens = ft.Column(spacing=6)
        for it in itens:
            peca = database.get_peca(it["peca_id"])
            nome_p = peca["nome"] if peca else f"Peça #{it['peca_id']}"
            pos_str = f"L{peca['posicao_linha']+1}·C{peca['posicao_coluna']+1}" if peca else "-"
            restante = it["quantidade_restante"]
            concluido = (restante == 0)
            selecionado = (self.item_os_selecionado and self.item_os_selecionado["id"] == it["id"])

            bg = "#DCFCE7" if concluido else ("#E0F2FE" if selecionado else BG_CARD)
            borda = _border_all(2 if selecionado else 1, ACCENT_EMERALD if concluido else (MULTILOG_CYAN if selecionado else BORDER_SUBTLE))

            cards_itens.controls.append(
                ft.Container(
                    bgcolor=bg,
                    border=borda,
                    border_radius=10,
                    padding=10,
                    on_click=lambda e, item_x=it: self.selecionar_item_os(item_x, atualizar_tela=True) if item_x["quantidade_restante"] > 0 else None,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=1,
                                expand=True,
                                controls=[
                                    ft.Text(f"{nome_p} ({pos_str})", size=12, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                    ft.Text(
                                        f"{it['tipo_operacao']} | RFID: {peca.get('rfid_uid') or 'S/ Tag'}" if peca else "",
                                        size=10,
                                        color=TEXT_MUTED,
                                    ),
                                ],
                            ),
                            ft.Container(
                                bgcolor=ACCENT_EMERALD if concluido else MULTILOG_NAVY,
                                border_radius=6,
                                padding=_pad_sym(8, 4),
                                content=ft.Text(
                                    "✓ FEITO" if concluido else f"Faltam {restante} ({it['quantidade_atendida']}/{it['quantidade']})",
                                    size=10,
                                    weight=ft.FontWeight.BOLD,
                                    color="#FFFFFF",
                                ),
                            ),
                        ],
                    ),
                )
            )

        painel_exec = self._construir_painel_terminal_os_ativo()

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=8,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        _btn("← Pausar", on_click=lambda e: self._pausar_os_ativa(), bgcolor="#475569", height=32),
                        ft.Text(f"O.S. #{ordem_id} ({tot_atend}/{tot_plan})", size=13, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                        _btn("Concluir ✓", on_click=lambda e: self._finalizar_os_ativa(), bgcolor=ACCENT_EMERALD, height=32),
                    ],
                ),
                ft.Container(
                    bgcolor="#E0F2FE",
                    border=_border_all(1, MULTILOG_BORDER_BLUE),
                    border_radius=10,
                    padding=8,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("💡 Ver posição piscando na estante:", size=11, weight=ft.FontWeight.BOLD, color=MULTILOG_NAVY, expand=True),
                            _btn("🗄️ Estante", on_click=lambda e: self.navegar("estoque"), bgcolor=MULTILOG_BLUE, height=30),
                        ],
                    ),
                ),
                painel_exec,
                ft.Text("Checklist da O.S.:", size=12, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                cards_itens,
            ],
        )

    # =========================================================================
    # Tela 4: Painel de Supervisão Admin (Grade 2x2 para Vertical 20:9)
    # =========================================================================
    def _construir_tela_admin(self) -> ft.Control:
        kpis = database.get_kpis()
        ordens = database.get_auditoria_ordens_servico()

        def card_kpi(titulo: str, valor: int, cor: str):
            return ft.Container(
                expand=True,
                bgcolor=BG_CARD,
                border=_border_all(1, BORDER_SUBTLE),
                border_radius=10,
                padding=10,
                content=ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text(titulo, size=10, color=TEXT_MUTED, weight=ft.FontWeight.BOLD),
                        ft.Text(str(valor), size=20, color=cor, weight=ft.FontWeight.BOLD),
                    ],
                ),
            )

        lista_os = ft.Column(spacing=6)
        for o in ordens[:25]:
            oid = o["id"]
            lista_os.controls.append(
                ft.Container(
                    bgcolor=BG_CARD,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=10,
                    padding=10,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                expand=True,
                                controls=[
                                    ft.Text(f"O.S. #{oid} · {o['titulo']}", size=13, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                    ft.Text(
                                        f"{o['status_calculado']} | {o['total_atendido']}/{o['total_planejado']} un | Op: {o.get('operador_id') or 'Todos'}",
                                        size=10,
                                        color=TEXT_MUTED,
                                    ),
                                ],
                            ),
                            ft.TextButton(
                                "Reiniciar",
                                on_click=lambda e, x=oid: (database.reiniciar_ordem_servico(x), self.mostrar_snackbar(f"O.S. #{x} reaberta!"), self.renderizar_tela_atual()),
                            ),
                        ],
                    ),
                )
            )

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=8,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text("Painel de Supervisão", size=16, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                        _btn("➕ Nova O.S.", on_click=lambda e: self.abrir_modal_nova_os(), bgcolor=MULTILOG_NAVY, height=34),
                    ],
                ),
                ft.Row(
                    spacing=6,
                    controls=[
                        card_kpi("PEÇAS CADASTRADAS", kpis["total_pecas"], MULTILOG_NAVY),
                        card_kpi("OPERADORES", kpis["total_operadores"], MULTILOG_CYAN),
                    ],
                ),
                ft.Row(
                    spacing=6,
                    controls=[
                        card_kpi("O.S. EM ABERTO", kpis["ordens_abertas"], ACCENT_AMBER),
                        card_kpi("O.S. CONCLUÍDAS", kpis["ordens_concluidas"], ACCENT_EMERALD),
                    ],
                ),
                ft.Text("Ordens de Serviço Recentes", size=14, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                lista_os,
            ],
        )

    def abrir_modal_nova_os(self):
        pecas = database.get_todas_pecas()
        if not pecas:
            self.mostrar_snackbar("Cadastre ao menos uma peça antes de criar uma O.S.", erro=True)
            return

        operadores = database.get_usuarios_operarios()
        estantes = database.get_todas_estantes()

        tf_titulo = ft.TextField(label="Título da O.S. *", hint_text="Ex: Separação Lote 04", dense=True, text_size=12, bgcolor=BG_ELEVATED)
        dd_operador = ft.Dropdown(
            label="Operador Responsável",
            value="TODOS",
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            options=[_opt("TODOS", "Qualquer Operador")] + [_opt(str(op["id"]), f"{op['nome']} ({op['id']})") for op in operadores],
        )
        dd_estante = ft.Dropdown(
            label="Estante",
            value=str(self.estante_ativa_id),
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            options=[_opt(str(e["id"]), e["nome"]) for e in estantes],
        )

        dd_peca = ft.Dropdown(
            label="Peça",
            value=str(pecas[0]["id"]),
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            expand=True,
            options=[_opt(str(p["id"]), f"{p['nome']} (Est: {p['quantidade_estoque']})") for p in pecas],
        )
        dd_op_item = ft.Dropdown(
            label="Tipo",
            value="REMOCAO",
            width=120,
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            options=[_opt("REMOCAO", "Retirada (-)"), _opt("ADICAO", "Entrada (+)")],
        )
        tf_qtd_item = ft.TextField(label="Qtd", value="2", width=65, dense=True, text_size=12, bgcolor=BG_ELEVATED)

        itens_rascunho: List[Dict[str, Any]] = []
        col_itens_rascunho = ft.Column(spacing=3)

        def atualizar_lista_rascunho():
            col_itens_rascunho.controls.clear()
            for it in itens_rascunho:
                col_itens_rascunho.controls.append(
                    ft.Text(f"• {it['nome']} — {it['tipo_operacao']} ({it['quantidade']} un)", size=11, color=TEXT_MAIN)
                )

        def adicionar_item(e):
            try:
                pid = int(dd_peca.value)
                qtd = int(tf_qtd_item.value.strip())
                if qtd <= 0:
                    raise ValueError()
            except ValueError:
                self.mostrar_snackbar("Quantidade inválida.", erro=True)
                return
            p_obj = database.get_peca(pid)
            itens_rascunho.append(
                {
                    "peca_id": pid,
                    "nome": p_obj["nome"] if p_obj else f"Peça #{pid}",
                    "tipo_operacao": dd_op_item.value or "REMOCAO",
                    "quantidade": qtd,
                }
            )
            atualizar_lista_rascunho()
            self.page.update()

        def salvar_os(e):
            titulo = (tf_titulo.value or "").strip()
            if not titulo:
                self.mostrar_snackbar("Informe o título da O.S.", erro=True)
                return
            if not itens_rascunho:
                adicionar_item(None)
            if not itens_rascunho:
                self.mostrar_snackbar("Adicione ao menos 1 item na O.S.", erro=True)
                return

            op_id = None if dd_operador.value == "TODOS" else dd_operador.value
            est_id = int(dd_estante.value or 1)
            oid = database.criar_ordem_servico(titulo, itens_rascunho, operador_id=op_id, estante_id=est_id)
            self.fechar_dialogo(dlg)
            self.mostrar_snackbar(f"O.S. #{oid} emitida!")
            self.renderizar_tela_atual()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Nova Ordem de Serviço", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=300,
                content=ft.Column(
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                    spacing=6,
                    controls=[
                        tf_titulo,
                        dd_operador,
                        dd_estante,
                        ft.Divider(height=1),
                        ft.Text("Itens da O.S.", size=11, weight=ft.FontWeight.BOLD, color=MULTILOG_NAVY),
                        dd_peca,
                        ft.Row(
                            spacing=6,
                            controls=[
                                dd_op_item,
                                tf_qtd_item,
                                _btn("+ Item", on_click=adicionar_item, bgcolor=MULTILOG_CYAN, expand=True, height=34),
                            ],
                        ),
                        col_itens_rascunho,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.fechar_dialogo(dlg)),
                _btn("Emitir O.S.", on_click=salvar_os, bgcolor=MULTILOG_NAVY, height=34),
            ],
        )
        self.abrir_dialogo(dlg)

    # =========================================================================
    # Tela 5: Gestão de Usuários, Crachás RFID e Fotos (funcionarios.db - 20:9)
    # =========================================================================
    def _construir_tela_usuarios(self) -> ft.Control:
        usuarios = database.get_todos_usuarios()

        estado_foto: Dict[str, Any] = {
            "path": "",
            "blob": None,
            "nome": "",
        }

        tf_id = ft.TextField(label="ID *", width=85, dense=True, text_size=12, bgcolor=BG_ELEVATED)
        tf_nome = ft.TextField(label="Nome Completo *", expand=True, dense=True, text_size=12, bgcolor=BG_ELEVATED)
        self.campo_nome_modal_ativo = tf_nome

        dd_role = ft.Dropdown(
            label="Perfil de Acesso",
            value="OPERARIO",
            expand=True,
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
            options=[
                _opt("OPERARIO", "OPERADOR (Operador de Bancada)"),
                _opt("ADMIN", "ADMIN (Supervisão Geral)"),
            ],
        )
        tf_rfid_user = ft.TextField(
            label="Tag RFID do Crachá",
            hint_text="Ex: C4 AE 78 E5",
            expand=True,
            dense=True,
            text_size=12,
            bgcolor=BG_ELEVATED,
        )
        lbl_rfid_status = ft.Text(
            "📡 Passe a tag no leitor RFID para preencher automaticamente",
            size=10,
            weight=ft.FontWeight.BOLD,
            color=MULTILOG_CYAN,
        )

        # Caixa de pré-visualização da foto do funcionário
        box_preview_foto = ft.Container(
            width=72,
            height=72,
            alignment=_align_center(),
            content=_criar_avatar_widget(size=68, is_admin=False, border_radius=10),
        )
        lbl_foto_nome = ft.Text("Nenhuma foto selecionada", size=10, weight=ft.FontWeight.BOLD, color=TEXT_MUTED)
        tf_caminho_foto = ft.TextField(
            label="Caminho ou arquivo da foto (opcional)",
            hint_text="Ex: fotos_funcionarios/funcionario_1001.jpg",
            dense=True,
            text_size=11,
            bgcolor=BG_ELEVATED,
            visible=False,
        )

        def atualizar_preview(caminho: str = "", blob: Optional[bytes] = None, nome_arq: str = ""):
            estado_foto["path"] = (caminho or "").strip()
            if blob is not None:
                estado_foto["blob"] = blob
            elif estado_foto["path"] and os.path.isfile(estado_foto["path"]):
                try:
                    with open(estado_foto["path"], "rb") as f:
                        estado_foto["blob"] = f.read()
                except Exception:
                    estado_foto["blob"] = None
            else:
                estado_foto["blob"] = None

            estado_foto["nome"] = nome_arq or (os.path.basename(estado_foto["path"]) if estado_foto["path"] else "")
            eh_adm = (dd_role.value == "ADMIN")
            box_preview_foto.content = _criar_avatar_widget(
                foto_path=estado_foto["path"],
                foto_blob=estado_foto["blob"],
                size=68,
                is_admin=eh_adm,
                border_radius=10,
            )
            if estado_foto["blob"] or (estado_foto["path"] and os.path.isfile(estado_foto["path"])):
                lbl_foto_nome.value = f"✅ {estado_foto['nome'] or 'Foto carregada'}"
                lbl_foto_nome.color = "#059669"
            else:
                lbl_foto_nome.value = "Nenhuma foto selecionada"
                lbl_foto_nome.color = TEXT_MUTED
            self.page.update()

        def receber_tag_usuario(tag: str, origem: str = "Leitor RFID"):
            tag_fmt = database.formatar_rfid_uid(tag)
            tf_rfid_user.value = tag_fmt
            lbl_rfid_status.value = f"✅ Tag capturada ({origem}): {tag_fmt}"
            lbl_rfid_status.color = "#059669"
            self.page.update()

        self.callback_rfid_tela_usuarios = lambda t: receber_tag_usuario(t, "Leitor RFID")

        def abrir_seletor_fotos_salvas(e):
            pasta = _pasta_fotos_funcionarios()
            arquivos = []
            if os.path.isdir(pasta):
                for arq in sorted(os.listdir(pasta)):
                    if arq.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")):
                        arquivos.append(os.path.join(pasta, arq))

            opcoes_botoes = []
            for cam in arquivos:
                nome_b = os.path.basename(cam)
                opcoes_botoes.append(
                    _btn(
                        f"📷 {nome_b}",
                        on_click=lambda ev, c_sel=cam: (
                            atualizar_preview(caminho=c_sel, nome_arq=os.path.basename(c_sel)),
                            self.fechar_dialogo(dlg_foto),
                        ),
                        bgcolor="#E0F2FE",
                        color=MULTILOG_NAVY,
                        height=34,
                    )
                )

            tf_custom_path = ft.TextField(
                label="Ou informe o caminho do arquivo de imagem",
                value=estado_foto["path"],
                dense=True,
                text_size=11,
                bgcolor=BG_ELEVATED,
            )

            def carregar_caminho_manual(ev):
                cam_m = (tf_custom_path.value or "").strip()
                if cam_m and os.path.isfile(cam_m):
                    atualizar_preview(caminho=cam_m, nome_arq=os.path.basename(cam_m))
                    self.fechar_dialogo(dlg_foto)
                else:
                    self.mostrar_snackbar("Arquivo de imagem não encontrado neste caminho.", erro=True)

            dlg_foto = ft.AlertDialog(
                modal=True,
                title=ft.Text("📷 Selecionar Foto do Funcionário", size=14, weight=ft.FontWeight.BOLD),
                content=ft.Container(
                    width=300,
                    content=ft.Column(
                        tight=True,
                        spacing=6,
                        controls=[
                            ft.Text("Fotos disponíveis em fotos_funcionarios/:", size=11, color=TEXT_MUTED),
                            *(opcoes_botoes if opcoes_botoes else [ft.Text("Nenhuma foto na pasta padrão.", size=11, color=TEXT_SUBTLE)]),
                            ft.Divider(height=1),
                            tf_custom_path,
                            _btn("Carregar Caminho", on_click=carregar_caminho_manual, bgcolor=MULTILOG_BLUE, height=34),
                        ],
                    ),
                ),
                actions=[ft.TextButton("Fechar", on_click=lambda ev: self.fechar_dialogo(dlg_foto))],
            )
            self.abrir_dialogo(dlg_foto)

        def carregar_para_edicao(u: Dict[str, Any]):
            tf_id.value = str(u["id"])
            tf_nome.value = u["nome"]
            dd_role.value = u["role"]
            urfid = (u.get("rfid_uid") or "").strip()
            tf_rfid_user.value = urfid
            if urfid:
                lbl_rfid_status.value = f"🏷️ Editando '{u['nome']}' — passe nova tag para alterar"
                lbl_rfid_status.color = MULTILOG_CYAN
            else:
                lbl_rfid_status.value = f"📡 Editando '{u['nome']}' — aproxime a tag para vincular!"
                lbl_rfid_status.color = "#D97706"
            atualizar_preview(
                caminho=u.get("foto_path") or "",
                blob=u.get("foto_blob"),
                nome_arq=u.get("foto_nome") or "",
            )

        def limpar_formulario(e=None):
            tf_id.value = ""
            tf_nome.value = ""
            dd_role.value = "OPERARIO"
            tf_rfid_user.value = ""
            lbl_rfid_status.value = "📡 Passe a tag no leitor RFID para preencher automaticamente"
            lbl_rfid_status.color = MULTILOG_CYAN
            atualizar_preview("", blob=None, nome_arq="")

        def salvar_user(e):
            uid = (tf_id.value or "").strip()
            nome = (tf_nome.value or "").strip()
            role = dd_role.value or "OPERARIO"
            rfid_uid = database.formatar_rfid_uid(tf_rfid_user.value or "")
            if not uid or not nome:
                self.mostrar_snackbar("Preencha Matrícula/ID e Nome Completo.", erro=True)
                return

            foto_destino = ""
            foto_blob_salvar = estado_foto["blob"]
            foto_nome_salvar = estado_foto["nome"]
            pasta_fotos = _pasta_fotos_funcionarios()

            if estado_foto["path"] and os.path.isfile(estado_foto["path"]):
                ext = os.path.splitext(estado_foto["path"])[1].lower() or ".jpg"
                uid_safe = "".join(ch for ch in uid if ch.isalnum() or ch in ("_", "-")) or "user"
                destino_abs = os.path.join(pasta_fotos, f"funcionario_{uid_safe}{ext}")
                try:
                    if os.path.abspath(estado_foto["path"]) != os.path.abspath(destino_abs):
                        shutil.copy2(estado_foto["path"], destino_abs)
                    foto_destino = destino_abs
                    if not foto_blob_salvar:
                        with open(destino_abs, "rb") as f:
                            foto_blob_salvar = f.read()
                    if not foto_nome_salvar:
                        foto_nome_salvar = os.path.basename(destino_abs)
                except Exception:
                    foto_destino = estado_foto["path"]
            elif foto_blob_salvar:
                ext = os.path.splitext(foto_nome_salvar)[1].lower() if foto_nome_salvar else ".jpg"
                if not ext:
                    ext = ".jpg"
                uid_safe = "".join(ch for ch in uid if ch.isalnum() or ch in ("_", "-")) or "user"
                destino_abs = os.path.join(pasta_fotos, f"funcionario_{uid_safe}{ext}")
                try:
                    with open(destino_abs, "wb") as f:
                        f.write(foto_blob_salvar)
                    foto_destino = destino_abs
                except Exception:
                    pass
            else:
                foto_blob_salvar = None
                foto_nome_salvar = ""

            database.upsert_usuario(
                uid,
                nome,
                role,
                rfid_uid=rfid_uid,
                foto_path=foto_destino,
                foto_blob=foto_blob_salvar,
                foto_nome=foto_nome_salvar,
            )

            if str(self.funcionario_id) == str(uid):
                self._atualizar_badge_header()

            self.mostrar_snackbar(f"Usuário '{nome}' (ID {uid}) salvo em funcionarios.db!")
            self.renderizar_tela_atual()

        def excluir_user(uid: str):
            ok, msg = database.remover_usuario(uid, current_user_id=self.funcionario_id)
            self.mostrar_snackbar(msg, erro=not ok)
            if ok:
                self.renderizar_tela_atual()

        lista_u = ft.Column(spacing=6)
        for u in usuarios:
            uid = str(u["id"])
            eh_admin = u["role"] == "ADMIN"
            urfid = (u.get("rfid_uid") or "").strip()
            ublob = u.get("foto_blob")
            ufoto = (u.get("foto_path") or "").strip()
            tem_foto = bool((ublob and len(ublob) > 0) or (ufoto and os.path.isfile(ufoto)))

            avatar_card = _criar_avatar_widget(
                foto_path=ufoto,
                foto_blob=ublob,
                size=46,
                is_admin=eh_admin,
                border_radius=8,
            )

            lista_u.controls.append(
                ft.Container(
                    bgcolor=BG_CARD,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=10,
                    padding=8,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            avatar_card,
                            ft.Column(
                                spacing=2,
                                expand=True,
                                controls=[
                                    ft.Text(f"{u['nome']} (ID: {uid})", size=12, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                    ft.Row(
                                        spacing=4,
                                        wrap=True,
                                        controls=[
                                            ft.Container(
                                                bgcolor="#FEF3C7" if eh_admin else "#ECFDF5",
                                                border_radius=4,
                                                padding=_pad_sym(5, 1),
                                                content=ft.Text(
                                                    "⚡ ADMIN" if eh_admin else "● OPERADOR",
                                                    size=8,
                                                    weight=ft.FontWeight.BOLD,
                                                    color="#92400E" if eh_admin else "#065F46",
                                                ),
                                            ),
                                            ft.Container(
                                                bgcolor="#E0F2FE" if urfid else "#F1F5F9",
                                                border_radius=4,
                                                padding=_pad_sym(5, 1),
                                                content=ft.Text(
                                                    f"🏷️ {urfid}" if urfid else "🏷️ Sem RFID",
                                                    size=8,
                                                    weight=ft.FontWeight.BOLD,
                                                    color="#0369A1" if urfid else TEXT_MUTED,
                                                ),
                                            ),
                                            ft.Container(
                                                bgcolor="#DCFCE7" if tem_foto else "#F1F5F9",
                                                border_radius=4,
                                                padding=_pad_sym(5, 1),
                                                content=ft.Text(
                                                    "📷 Foto no BD" if tem_foto else "📷 Sem Foto",
                                                    size=8,
                                                    weight=ft.FontWeight.BOLD,
                                                    color="#166534" if tem_foto else TEXT_MUTED,
                                                ),
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            ft.Column(
                                spacing=3,
                                controls=[
                                    _btn("✏️ Editar", on_click=lambda e, usr=u: carregar_para_edicao(usr), bgcolor="#E2E8F0", color=TEXT_MAIN, height=30, font_size=11),
                                    *(
                                        [_btn("🗑️", on_click=lambda e, x=uid: excluir_user(x), bgcolor="#FEE2E2", color="#991B1B", height=30, font_size=11)]
                                        if uid != str(self.funcionario_id)
                                        else []
                                    ),
                                ],
                            ),
                        ],
                    ),
                )
            )

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=8,
            controls=[
                ft.Text("Gestão de Usuários & Crachás RFID", size=15, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                ft.Container(
                    bgcolor=BG_CARD,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=12,
                    padding=10,
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            ft.Text("Cadastrar / Editar Colaborador (funcionarios.db)", size=11, weight=ft.FontWeight.BOLD, color=MULTILOG_NAVY),
                            ft.Row(spacing=6, controls=[tf_id, tf_nome]),
                            dd_role,
                            ft.Row(
                                spacing=4,
                                controls=[
                                    tf_rfid_user,
                                    _btn("✕", on_click=lambda e: (setattr(tf_rfid_user, "value", ""), self.page.update()), bgcolor="#F1F5F9", color=TEXT_MUTED, width=38, height=36, font_size=12),
                                ],
                            ),
                            lbl_rfid_status,
                            ft.Row(
                                spacing=6,
                                controls=[
                                    _btn("🏷️ Tag ADM", on_click=lambda e: receber_tag_usuario("C4 AE 78 E5", "Atalho"), bgcolor="#FEF3C7", color="#B45309", expand=True, height=34, font_size=11),
                                    _btn("🏷️ Tag OP", on_click=lambda e: receber_tag_usuario("47 09 9E A3", "Atalho"), bgcolor="#E0F2FE", color=MULTILOG_NAVY, expand=True, height=34, font_size=11),
                                ],
                            ),
                            ft.Container(
                                bgcolor=BG_ELEVATED,
                                border=_border_all(1, "#CBD5E1"),
                                border_radius=8,
                                padding=8,
                                content=ft.Row(
                                    spacing=8,
                                    controls=[
                                        box_preview_foto,
                                        ft.Column(
                                            spacing=4,
                                            expand=True,
                                            controls=[
                                                lbl_foto_nome,
                                                ft.Row(
                                                    spacing=6,
                                                    controls=[
                                                        _btn("📷 Foto", on_click=abrir_seletor_fotos_salvas, bgcolor=MULTILOG_BLUE, expand=True, height=34, font_size=11),
                                                        _btn("✕ Limpar", on_click=lambda e: atualizar_preview("", blob=None, nome_arq=""), bgcolor="#FEE2E2", color="#991B1B", expand=True, height=34, font_size=11),
                                                    ],
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ),
                            tf_caminho_foto,
                            ft.Row(
                                spacing=6,
                                controls=[
                                    _btn("Limpar", on_click=limpar_formulario, bgcolor="#E2E8F0", color=TEXT_MAIN, height=38, font_size=12),
                                    _btn("SALVAR USUÁRIO ▶", on_click=salvar_user, bgcolor=MULTILOG_NAVY, expand=True, height=38, font_size=12),
                                ],
                            ),
                        ],
                    ),
                ),
                ft.Text(f"Colaboradores Cadastrados ({len(usuarios)})", size=12, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                lista_u,
            ],
        )


def main(page: ft.Page):
    MultilogMobileApp(page)


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
