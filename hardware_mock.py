from typing import Optional, Tuple
import hardware_manager

led_ativo: Optional[Tuple[int, int]] = None

def acender_led(linha: int, coluna: int) -> None:
    """Acende o LED físico via ESP32 (Serial/Wi-Fi) ou atualiza o estado visual."""
    global led_ativo
    led_ativo = (linha, coluna)
    hw = hardware_manager.HardwareManager.get_instancia()
    hw.acender_led(linha, coluna)
    print(f"[HARDWARE LED] -> ACENDER LED na posição: Linha {linha}, Coluna {coluna}")

def apagar_led() -> None:
    """Apaga os LEDs físicos via ESP32 (Serial/Wi-Fi) ou atualiza o estado visual."""
    global led_ativo
    led_ativo = None
    hw = hardware_manager.HardwareManager.get_instancia()
    hw.apagar_led()
    print("[HARDWARE LED] -> APAGAR todos os LEDs.")

def tocar_buzzer_erro() -> None:
    """Aciona o buzzer de alerta de erro (pino D2) no ESP32 via Serial/Wi-Fi."""
    hw = hardware_manager.HardwareManager.get_instancia()
    hw.acionar_buzzer_erro()
    print("[HARDWARE BUZZER] -> ALERTA SONORO DE ERRO (D2)")

def ler_peso_balanca(peso_esperado: float = 0.0) -> Optional[float]:
    """
    Lê o último peso real recebido da célula de carga HX711 no ESP32.
    Caso o ESP32 não esteja conectado no momento, retorna o peso simulado para não travar testes offline.
    """
    hw = hardware_manager.HardwareManager.get_instancia()
    if hw.esta_conectado():
        peso_real = hw.ler_ultimo_peso()
        return peso_real
    if hw.ler_ultimo_peso() > 0:
        return hw.ler_ultimo_peso()
    return float(peso_esperado)
