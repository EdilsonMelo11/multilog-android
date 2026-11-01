import flet as ft
import database
from typing import Dict, Any, Optional

# Identidade Visual Oficial Multilog - Modo Pro Clean
MULTILOG_NAVY = "#003865"
MULTILOG_BLUE = "#0066CC"
MULTILOG_CYAN = "#0284C7"
BG_APP = "#F0F4F8"
BG_CARD = "#FFFFFF"
BG_ELEVATED = "#F8FAFC"
BORDER_SUBTLE = "#E2E8F0"
TEXT_MAIN = "#0F172A"
TEXT_MUTED = "#64748B"
ACCENT_EMERALD = "#10B981"
ACCENT_AMBER = "#F59E0B"
ACCENT_ROSE = "#EF4444"


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
    height: int = 36,
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


def _status_badge_cores(status: str):
    st = (status or "").upper()
    if "CUMPRIDA" in st and "NAO" not in st:
        return "#DCFCE7", "#15803D"
    if "INCOMPLETA" in st or "ABERTA" in st:
        return "#FEF3C7", "#B45309"
    if "ATRASO" in st or "NAO_CUMPRIDA" in st:
        return "#FEE2E2", "#B91C1C"
    return "#E0F2FE", "#0369A1"


def construir_tela_diario(page: ft.Page, mostrar_snackbar) -> ft.Control:
    """Constrói a visão mobile vertical 20:9 de Diário de Movimentações, Auditoria de O.S. e Extrato por Gaveta."""
    aba_ativa = {"idx": 0}

    # --- Filtros Aba 1: Movimentações ---
    dd_op_mov = ft.Dropdown(
        label="Operador",
        value="TODOS",
        expand=True,
        dense=True,
        text_size=12,
        bgcolor=BG_ELEVATED,
        border_color=BORDER_SUBTLE,
    )
    dd_tipo_mov = ft.Dropdown(
        label="Operação",
        value="TODAS",
        width=125,
        dense=True,
        text_size=12,
        bgcolor=BG_ELEVATED,
        border_color=BORDER_SUBTLE,
        options=[
            _opt("TODAS", "Todas"),
            _opt("ADICAO", "Entrada (+)"),
            _opt("REMOCAO", "Saída (-)"),
        ],
    )
    tf_busca_mov = ft.TextField(
        label="Buscar peça, O.S. ou operador...",
        dense=True,
        text_size=12,
        bgcolor=BG_ELEVATED,
        border_color=BORDER_SUBTLE,
        expand=True,
    )
    lista_mov_col = ft.Column(spacing=6)

    # --- Filtros Aba 2: Auditoria O.S. ---
    dd_status_os = ft.Dropdown(
        label="Status O.S.",
        value="TODOS",
        expand=True,
        dense=True,
        text_size=12,
        bgcolor=BG_ELEVATED,
        border_color=BORDER_SUBTLE,
        options=[
            _opt("TODOS", "Todos"),
            _opt("ABERTA", "Aberta"),
            _opt("CUMPRIDA", "Cumprida"),
            _opt("INCOMPLETA", "Incompleta"),
            _opt("ATRASO", "Em Atraso"),
        ],
    )
    tf_busca_os = ft.TextField(
        label="Buscar título ou nº O.S...",
        dense=True,
        text_size=12,
        bgcolor=BG_ELEVATED,
        border_color=BORDER_SUBTLE,
        expand=True,
    )
    lista_os_col = ft.Column(spacing=6)

    # --- Filtros Aba 3: Extrato por Gaveta ---
    dd_data_ext = ft.Dropdown(
        label="Data",
        expand=True,
        dense=True,
        text_size=12,
        bgcolor=BG_ELEVATED,
        border_color=BORDER_SUBTLE,
    )
    dd_estante_ext = ft.Dropdown(
        label="Estante",
        expand=True,
        dense=True,
        text_size=12,
        bgcolor=BG_ELEVATED,
        border_color=BORDER_SUBTLE,
    )
    sw_vazias_ext = ft.Switch(label="Gavetas vazias", value=False)
    lista_ext_col = ft.Column(spacing=6)

    container_conteudo = ft.Container(expand=True)

    def carregar_opcoes_filtros():
        usuarios = database.get_todos_usuarios()
        opts_u = [_opt("TODOS", "Todos")]
        for u in usuarios:
            opts_u.append(_opt(str(u["id"]), f"{u['nome']} ({u['id']})"))
        dd_op_mov.options = opts_u
        if not dd_op_mov.value:
            dd_op_mov.value = "TODOS"

        datas = database.get_datas_com_movimentacoes()
        dd_data_ext.options = [_opt(d, d) for d in datas]
        if datas and not dd_data_ext.value:
            dd_data_ext.value = datas[0]

        estantes = database.get_todas_estantes()
        dd_estante_ext.options = [_opt(str(e["id"]), e["nome"]) for e in estantes]
        if estantes and not dd_estante_ext.value:
            dd_estante_ext.value = str(estantes[0]["id"])

    def abrir_dialogo(dlg: ft.AlertDialog):
        try:
            page.show_dialog(dlg)
        except Exception:
            try:
                page.open(dlg)
            except Exception:
                page.dialog = dlg
                dlg.open = True
                page.update()

    def fechar_dialogo(dlg: ft.AlertDialog):
        try:
            page.pop_dialog()
        except Exception:
            try:
                page.close(dlg)
            except Exception:
                dlg.open = False
                page.update()

    def abrir_modal_conciliacao(ordem_id: int):
        try:
            det = database.get_detalhes_conciliacao_os(ordem_id)
        except Exception as ex:
            mostrar_snackbar(f"Erro ao carregar conciliação: {ex}", erro=True)
            return

        ordem = det["ordem"]
        itens = det["itens_planejados"]
        movs = det["movimentacoes_realizadas"]

        itens_widgets = []
        for it in itens:
            peca = database.get_peca(it["peca_id"])
            nome_peca = peca["nome"] if peca else f"Peça #{it['peca_id']}"
            atendido = it.get("quantidade_atendida", 0)
            planejado = it.get("quantidade", 0)
            cor_it = ACCENT_EMERALD if atendido >= planejado else ACCENT_AMBER
            itens_widgets.append(
                ft.Container(
                    bgcolor=BG_ELEVATED,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=8,
                    padding=8,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=1,
                                expand=True,
                                controls=[
                                    ft.Text(nome_peca, weight=ft.FontWeight.BOLD, size=12, color=TEXT_MAIN),
                                    ft.Text(f"Op: {it['tipo_operacao']}", size=10, color=TEXT_MUTED),
                                ],
                            ),
                            ft.Container(
                                bgcolor=cor_it,
                                border_radius=6,
                                padding=_pad_sym(7, 3),
                                content=ft.Text(f"{atendido}/{planejado} un", color="#FFFFFF", size=10, weight=ft.FontWeight.BOLD),
                            ),
                        ],
                    ),
                )
            )

        movs_widgets = []
        if not movs:
            movs_widgets.append(ft.Text("Nenhuma movimentação registrada.", size=11, color=TEXT_MUTED))
        else:
            for m in movs:
                sinal = "+" if m["tipo_operacao"] == "ADICAO" else "-"
                cor_m = ACCENT_EMERALD if m["tipo_operacao"] == "ADICAO" else MULTILOG_CYAN
                movs_widgets.append(
                    ft.Container(
                        bgcolor="#FFFFFF",
                        border=_border_all(1, BORDER_SUBTLE),
                        border_radius=8,
                        padding=7,
                        content=ft.Column(
                            spacing=1,
                            controls=[
                                ft.Text(f"{m.get('peca_nome') or 'Peça'} ({sinal}{m['quantidade']} un)", weight=ft.FontWeight.BOLD, size=11, color=cor_m),
                                ft.Text(f"Op: {m.get('operador_nome') or m['funcionario_id']} · {m['data_hora']}", size=10, color=TEXT_MUTED),
                            ],
                        ),
                    )
                )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"O.S. #{ordem['id']} · {ordem['titulo']}", size=14, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=300,
                height=380,
                content=ft.Column(
                    scroll=ft.ScrollMode.AUTO,
                    spacing=8,
                    controls=[
                        ft.Text(f"Status: {ordem['status_calculado']}", weight=ft.FontWeight.BOLD, size=11, color=MULTILOG_NAVY),
                        ft.Text(f"Prazo: {ordem.get('prazo_limite') or '-'}", size=10, color=TEXT_MUTED),
                        ft.Divider(height=1),
                        ft.Text("Planejado vs. Realizado", weight=ft.FontWeight.BOLD, size=12, color=TEXT_MAIN),
                        ft.Column(spacing=5, controls=itens_widgets),
                        ft.Divider(height=1),
                        ft.Text("Histórico da O.S.", weight=ft.FontWeight.BOLD, size=12, color=TEXT_MAIN),
                        ft.Column(spacing=5, controls=movs_widgets),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Fechar", on_click=lambda e: fechar_dialogo(dlg)),
            ],
        )
        abrir_dialogo(dlg)

    def atualizar_aba_movimentacoes():
        filtros = {
            "funcionario_id": dd_op_mov.value or "TODOS",
            "tipo_operacao": dd_tipo_mov.value or "TODAS",
            "busca": (tf_busca_mov.value or "").strip(),
        }
        movs = database.get_diario_movimentacoes(filtros)
        lista_mov_col.controls.clear()

        if not movs:
            lista_mov_col.controls.append(
                ft.Container(
                    padding=18,
                    alignment=_align_center(),
                    content=ft.Text("Nenhuma movimentação encontrada.", size=12, color=TEXT_MUTED),
                )
            )
        else:
            for m in movs[:80]:
                eh_adicao = m.get("tipo_operacao") == "ADICAO"
                cor_badge = "#DCFCE7" if eh_adicao else "#E0F2FE"
                cor_txt = "#15803D" if eh_adicao else "#0369A1"
                sinal = "+" if eh_adicao else "-"
                os_info = f"O.S. #{m['ordem_id']}" if m.get("ordem_id") else "Avulsa"

                lista_mov_col.controls.append(
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
                                        ft.Text(
                                            f"{m.get('peca_nome') or 'Peça'} (#{m.get('peca_id')})",
                                            weight=ft.FontWeight.BOLD,
                                            size=12,
                                            color=TEXT_MAIN,
                                        ),
                                        ft.Text(
                                            f"👤 {m.get('funcionario_nome') or m.get('funcionario_id')} · 📋 {os_info}",
                                            size=10,
                                            color=MULTILOG_NAVY,
                                        ),
                                        ft.Text(f"🕒 {m.get('data_hora')}", size=10, color=TEXT_MUTED),
                                    ],
                                ),
                                ft.Container(
                                    bgcolor=cor_badge,
                                    border_radius=8,
                                    padding=_pad_sym(8, 5),
                                    content=ft.Text(
                                        f"{sinal}{m.get('quantidade')} un",
                                        weight=ft.FontWeight.BOLD,
                                        size=12,
                                        color=cor_txt,
                                    ),
                                ),
                            ],
                        ),
                    )
                )

    def atualizar_aba_auditoria():
        filtros = {
            "status": dd_status_os.value or "TODOS",
            "busca": (tf_busca_os.value or "").strip(),
        }
        ordens = database.get_auditoria_ordens_servico(filtros)
        lista_os_col.controls.clear()

        if not ordens:
            lista_os_col.controls.append(
                ft.Container(
                    padding=18,
                    alignment=_align_center(),
                    content=ft.Text("Nenhuma Ordem de Serviço encontrada.", size=12, color=TEXT_MUTED),
                )
            )
        else:
            for o in ordens:
                bg_st, fg_st = _status_badge_cores(o["status_calculado"])
                plan = o.get("total_planejado", 0)
                atend = o.get("total_atendido", 0)
                oid = o["id"]

                lista_os_col.controls.append(
                    ft.Container(
                        bgcolor=BG_CARD,
                        border=_border_all(1, BORDER_SUBTLE),
                        border_radius=10,
                        padding=10,
                        content=ft.Column(
                            spacing=4,
                            controls=[
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    controls=[
                                        ft.Text(f"O.S. #{oid} · {o['titulo']}", weight=ft.FontWeight.BOLD, size=12, color=TEXT_MAIN, expand=True),
                                        ft.Container(
                                            bgcolor=bg_st,
                                            border_radius=6,
                                            padding=_pad_sym(6, 3),
                                            content=ft.Text(o["status_calculado"], size=9, weight=ft.FontWeight.BOLD, color=fg_st),
                                        ),
                                    ],
                                ),
                                ft.Text(
                                    f"Op: {o.get('operador_id') or 'Todos'} · {atend}/{plan} un · Prazo: {o.get('prazo_limite') or '-'}",
                                    size=10,
                                    color=TEXT_MUTED,
                                ),
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.END,
                                    controls=[
                                        ft.TextButton(
                                            "Conciliação Detalhada",
                                            on_click=lambda e, x=oid: abrir_modal_conciliacao(x),
                                        )
                                    ],
                                ),
                            ],
                        ),
                    )
                )

    def atualizar_aba_extrato():
        datas_disp = database.get_datas_com_movimentacoes()
        data_sel = dd_data_ext.value or (datas_disp[0] if datas_disp else "")
        est_sel = int(dd_estante_ext.value or 1)
        extrato = database.get_extrato_caixas_por_dia(data_sel, est_sel, incluir_vazias=bool(sw_vazias_ext.value))
        lista_ext_col.controls.clear()

        if not extrato:
            lista_ext_col.controls.append(
                ft.Container(
                    padding=18,
                    alignment=_align_center(),
                    content=ft.Text("Nenhuma movimentação nesta data.", size=12, color=TEXT_MUTED),
                )
            )
        else:
            for item in extrato:
                saldo = item["saldo_liquido"]
                sinal_saldo = f"+{saldo}" if saldo > 0 else str(saldo)
                lista_ext_col.controls.append(
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
                                        ft.Text(f"{item['identificador_gaveta']} · {item['peca_nome']}", weight=ft.FontWeight.BOLD, size=12, color=TEXT_MAIN),
                                        ft.Text(
                                            f"Ent: +{item['total_entradas']} | Saí: -{item['total_saidas']} | Movs: {item['total_movimentacoes']}",
                                            size=10,
                                            color=TEXT_MUTED,
                                        ),
                                    ],
                                ),
                                ft.Container(
                                    bgcolor="#DCEBFA",
                                    border_radius=8,
                                    padding=_pad_sym(8, 5),
                                    content=ft.Text(f"Saldo: {sinal_saldo}", weight=ft.FontWeight.BOLD, size=11, color=MULTILOG_NAVY),
                                ),
                            ],
                        ),
                    )
                )

    def renderizar_aba():
        idx = aba_ativa["idx"]
        if idx == 0:
            atualizar_aba_movimentacoes()
            container_conteudo.content = ft.Column(
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
                controls=[
                    ft.Row(spacing=6, controls=[dd_op_mov, dd_tipo_mov]),
                    ft.Row(
                        spacing=6,
                        controls=[
                            tf_busca_mov,
                            _btn("Filtrar", on_click=lambda e: (atualizar_aba_movimentacoes(), page.update())),
                        ],
                    ),
                    lista_mov_col,
                ],
            )
        elif idx == 1:
            atualizar_aba_auditoria()
            container_conteudo.content = ft.Column(
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
                controls=[
                     dd_status_os,
                    ft.Row(
                        spacing=6,
                        controls=[
                            tf_busca_os,
                            _btn("Filtrar", on_click=lambda e: (atualizar_aba_auditoria(), page.update())),
                        ],
                    ),
                    lista_os_col,
                ],
            )
        else:
            atualizar_aba_extrato()
            container_conteudo.content = ft.Column(
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
                controls=[
                    ft.Row(spacing=6, controls=[dd_data_ext, dd_estante_ext]),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            sw_vazias_ext,
                            _btn("Atualizar", on_click=lambda e: (atualizar_aba_extrato(), page.update())),
                        ],
                    ),
                    lista_ext_col,
                ],
            )

    def selecionar_aba(novo_idx: int):
        aba_ativa["idx"] = novo_idx
        atualizar_botoes_abas()
        renderizar_aba()
        page.update()

    btn_aba_0 = _btn("📜 Movs", on_click=lambda e: selecionar_aba(0), expand=True, height=36, font_size=12)
    btn_aba_1 = _btn("🔍 O.S.", on_click=lambda e: selecionar_aba(1), expand=True, height=36, font_size=12)
    btn_aba_2 = _btn("📦 Extrato", on_click=lambda e: selecionar_aba(2), expand=True, height=36, font_size=12)

    def atualizar_botoes_abas():
        for i, b in enumerate([btn_aba_0, btn_aba_1, btn_aba_2]):
            ativo = (aba_ativa["idx"] == i)
            cor_txt = "#FFFFFF" if ativo else TEXT_MAIN
            b.bgcolor = MULTILOG_NAVY if ativo else "#E2E8F0"
            b.color = cor_txt
            if hasattr(b, "content") and isinstance(b.content, ft.Text):
                b.content.color = cor_txt

    carregar_opcoes_filtros()
    atualizar_botoes_abas()
    renderizar_aba()

    return ft.Column(
        expand=True,
        spacing=8,
        controls=[
            ft.Text("Diário e Auditoria", size=16, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
            ft.Row(spacing=4, controls=[btn_aba_0, btn_aba_1, btn_aba_2]),
            container_conteudo,
        ],
    )
