import database
import hardware_mock
from typing import Dict, Any, Tuple, Optional

# Margem de erro permitida para a balança (5%)
TOLERANCIA_PESO = 0.05

def validar_peso(peso_medido: float, peso_unitario: float, quantidade: int) -> bool:
    """Valida se o peso medido está dentro da tolerância do peso esperado."""
    if peso_unitario <= 0:
        return True
    peso_esperado = peso_unitario * quantidade
    margem = peso_esperado * TOLERANCIA_PESO
    limite_inferior = peso_esperado - margem
    limite_superior = peso_esperado + margem
    return limite_inferior <= peso_medido <= limite_superior

def processar_operacao(
    funcionario_id: str,
    peca_data: Dict[str, Any],
    tipo_operacao: str,
    peso_informado: Optional[float] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Processa o fluxo completo de adição ou remoção de peça.
    Se peso_informado for passado pela UI mobile, utiliza-o diretamente;
    caso contrário, consulta hardware_mock.ler_peso_balanca.
    """
    database.upsert_peca(peca_data)
    
    quantidade_operacao = int(peca_data.get('quantidade', 0))
    if quantidade_operacao <= 0:
        return False, "Quantidade deve ser maior que 0.", peca_data
        
    if tipo_operacao == "REMOCAO":
        peca_db = database.get_peca(peca_data['id'])
        if not peca_db or peca_db['quantidade_estoque'] < quantidade_operacao:
            return False, f"Estoque insuficiente. Disponível: {peca_db['quantidade_estoque'] if peca_db else 0}", peca_data

    hardware_mock.acender_led(peca_data['posicao_linha'], peca_data['posicao_coluna'])
    
    peso_esperado_total = float(peca_data['peso_unitario_g']) * quantidade_operacao
    peso_medido = peso_informado if peso_informado is not None else hardware_mock.ler_peso_balanca(peso_esperado=peso_esperado_total)
    
    if peso_medido is None:
        hardware_mock.apagar_led()
        return False, "Operação cancelada (Peso não informado).", peca_data
        
    if not validar_peso(peso_medido, float(peca_data['peso_unitario_g']), quantidade_operacao):
        hardware_mock.apagar_led()
        hardware_mock.tocar_buzzer_erro()
        return False, f"Erro de peso! Esperado ~{peso_esperado_total:.1f}g, Lido: {peso_medido:.1f}g", peca_data
        
    qtd_alteracao = quantidade_operacao if tipo_operacao == "ADICAO" else -quantidade_operacao
    try:
        nova_qtd = database.update_estoque(peca_data['id'], qtd_alteracao)
        database.registrar_operacao(funcionario_id, peca_data['id'], tipo_operacao, quantidade_operacao)
        hardware_mock.apagar_led()
        return True, f"Operação concluída. Novo estoque: {nova_qtd}", peca_data
    except Exception as e:
        hardware_mock.apagar_led()
        return False, f"Erro ao atualizar banco de dados: {e}", peca_data

def obter_item_os_pendente(os_itens: list, peca_id: int) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Verifica se a peça pertence à O.S. e se possui quantidade pendente.
    Retorna (item_os, mensagem_erro). Se válido, mensagem_erro é vazia.
    """
    itens_da_peca = [i for i in os_itens if i['peca_id'] == peca_id]
    if not itens_da_peca:
        return None, "Esta peça não consta na sua Ordem de Serviço atual."
    
    item_pendente = next(
        (i for i in itens_da_peca if i.get('quantidade_restante', i['quantidade'] - i.get('quantidade_atendida', 0)) > 0),
        None
    )
    if not item_pendente:
        return None, "Esta peça já teve sua quantidade totalmente atendida nesta O.S."
        
    return item_pendente, ""

def validar_operacao_os(item_os: Dict[str, Any], tipo_operacao: str, quantidade: int, estoque_atual: int) -> Tuple[bool, str]:
    """
    Valida estritamente se a operação e a quantidade solicitadas estão de acordo com o item da O.S.
    """
    op_esperada = item_os['tipo_operacao']
    if tipo_operacao != op_esperada:
        return False, f"Operação inválida. Esta O.S. prevê apenas {op_esperada} para esta peça."
        
    if quantidade <= 0:
        return False, "Quantidade deve ser maior que zero."
        
    qtd_restante = item_os.get('quantidade_restante', item_os['quantidade'] - item_os.get('quantidade_atendida', 0))
    if quantidade > qtd_restante:
        return False, f"Quantidade ({quantidade}) excede o previsto na O.S. Restam {qtd_restante} un."
        
    if tipo_operacao == "REMOCAO" and quantidade > estoque_atual:
        return False, f"Estoque insuficiente. Disponível: {estoque_atual} un."
        
    return True, "OK"


def ordenar_ordens_servico(ordens: list, criterio: str = "RECENTE") -> list:
    """
    Ordena/agrupa uma lista de Ordens de Serviço conforme o critério selecionado:
    - 'RECENTE': Da mais recente para a mais antiga (data_criacao / id decrescente)
    - 'ANTIGA': Da mais antiga para a mais recente (data_criacao / id crescente)
    - 'AZ': Ordem alfabética A-Z pelo título da O.S.
    - 'ZA': Ordem alfabética Z-A pelo título da O.S.
    """
    crit = (criterio or "RECENTE").strip().upper()
    lista = list(ordens or [])
    if crit == "ANTIGA":
        return sorted(
            lista,
            key=lambda o: ((o.get("data_criacao") or ""), int(o.get("id") or 0)),
            reverse=False,
        )
    if crit == "AZ":
        return sorted(
            lista,
            key=lambda o: ((o.get("titulo") or "").strip().casefold(), int(o.get("id") or 0)),
            reverse=False,
        )
    if crit == "ZA":
        return sorted(
            lista,
            key=lambda o: (o.get("titulo") or "").strip().casefold(),
            reverse=True,
        )
    # Padrão: RECENTE (mais recente primeiro)
    return sorted(
        lista,
        key=lambda o: ((o.get("data_criacao") or ""), int(o.get("id") or 0)),
        reverse=True,
    )


