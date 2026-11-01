import json
import socket
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, List, Optional

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    serial = None
    HAS_SERIAL = False

import database


def _remover_acentos_ascii(texto: str) -> str:
    """Converte caracteres acentuados para ASCII puro compatível com LCD HD44780 16x2."""
    nfkd = unicodedata.normalize("NFKD", texto or "")
    limpo = "".join(c for c in nfkd if not unicodedata.combining(c))
    return "".join(c if 32 <= ord(c) <= 126 else " " for c in limpo).strip()


class _ESP32RequestHandler(BaseHTTPRequestHandler):
    """
    Servidor HTTP local para comunicação Wi-Fi com o ESP32:
      - GET /api/ping -> Verificação de conectividade ("OK")
      - GET /api/item?tag=XX%20YY... -> Retorna o nome da peça para o LCD 16x2 e aciona o popup na UI
      - GET /api/sync?peso=12.3&tag=... -> Recebe telemetria de peso e tag RFID via Wi-Fi (sem cabo USB)
    """
    hw_manager: Optional["HardwareManager"] = None

    def log_message(self, format, *args):
        # Silencia logs padrão do BaseHTTPRequestHandler no terminal
        pass

    def _responder_json(self, status_code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        rota = parsed.path.rstrip("/") or "/"
        params = urllib.parse.parse_qs(parsed.query)
        hw = self.hw_manager
        if hw is not None and self.client_address:
            hw.registrar_contato_wifi(self.client_address[0])

        if rota in ("/", "/api/ping"):
            cmd = hw.consumir_comando_wifi() if hw else ""
            self._responder_json(200, {"ok": True, "app": "MULTILOG", "cmd": cmd})
            return

        if rota == "/api/item":
            raw_tag = params.get("tag", [""])[0]
            nome_lcd = "Nao Cadastrado"
            encontrado = False
            if hw and raw_tag:
                tag_fmt = hw._formatar_uid(raw_tag)
                if tag_fmt:
                    nome_lcd, encontrado = hw.obter_nome_item_para_lcd(tag_fmt)
                    # Dispara também o callback na interface (abre a gaveta/modal mesmo sem cabo USB!)
                    hw._notificar_rfid_recebido(tag_fmt, origem="WIFI")

            cmd = hw.consumir_comando_wifi() if hw else ""
            self._responder_json(
                200,
                {
                    "ok": True,
                    "found": encontrado,
                    "nome": nome_lcd[:16],
                    "cmd": cmd,
                },
            )
            return

        if rota == "/api/sync":
            if hw:
                if "peso" in params:
                    try:
                        peso_val = float(params["peso"][0].replace(",", "."))
                        hw._notificar_peso_recebido(peso_val)
                    except ValueError:
                        pass
                if "tag" in params and params["tag"][0].strip():
                    tag_fmt = hw._formatar_uid(params["tag"][0])
                    if tag_fmt:
                        hw._notificar_rfid_recebido(tag_fmt, origem="WIFI")

            cmd = hw.consumir_comando_wifi() if hw else ""
            self._responder_json(200, {"ok": True, "cmd": cmd})
            return

        if rota == "/api/buzzer":
            # Permite acionar o buzzer remotamente via HTTP se necessário
            if hw:
                hw.acionar_buzzer_erro()
            self._responder_json(200, {"ok": True, "buzzer": "ERRO"})
            return

        self._responder_json(404, {"ok": False, "error": "Rota nao encontrada"})


class HardwareManager:
    """
    Gerencia a comunicação em segundo plano (Thread) com o ESP32:
      1. Via Porta Serial USB (115200 bps) quando disponível no PC
      2. Via Rede Wi-Fi (Servidor HTTP na porta 5000 + Descoberta Automática UDP + Cliente HTTP ativo na porta 80 do ESP32)
    """
    _instancia: Optional["HardwareManager"] = None

    def __init__(self, host_padrao: str = "192.168.4.1"):
        self.serial_conn: Optional[object] = None
        self.porta_atual: Optional[str] = None
        self.baudrate: int = 115200
        self.rodando: bool = False
        self.thread: Optional[threading.Thread] = None

        self.host_configurado: str = self._limpar_host(host_padrao)
        self.host_ativo: str = self.host_configurado
        self.conectado: bool = False
        self.mensagem_status: str = "Modo Simulador / Buscando ESP32..."
        self.led_atual: Optional[tuple] = None

        self.http_server: Optional[ThreadingHTTPServer] = None
        self.http_thread: Optional[threading.Thread] = None
        self.http_port: int = 5000
        self.udp_thread: Optional[threading.Thread] = None
        self.esp_client_thread: Optional[threading.Thread] = None
        self.esp_ip_descoberto: Optional[str] = None
        self.ultimo_tag_seq_esp: int = -1
        self.ultimo_contato_wifi: float = 0.0
        self.ip_ultimo_esp32: str = ""

        self._fila_comandos_wifi: List[str] = []
        self._lock_fila = threading.Lock()

        self.callbacks_rfid: List[Callable[[str], None]] = []
        self.callbacks_peso: List[Callable[[float], None]] = []

        self.ultimo_peso: float = 0.0
        self.ultima_tag: str = ""
        self._ultimo_rfid_notificado_tag: str = ""
        self._ultimo_rfid_notificado_ts: float = 0.0
        self.janela_dedup_rfid_s: float = 2.0
        self.ultimo_erro_buzzer_ts: float = 0.0
        self.resolver_nome_custom: Optional[Callable[[str], Optional[str]]] = None

    @classmethod
    def get_instancia(cls) -> "HardwareManager":
        if cls._instancia is None:
            cls._instancia = HardwareManager()
        return cls._instancia

    def _limpar_host(self, host: str) -> str:
        h = (host or "192.168.4.1").strip()
        if h.startswith("http://"):
            h = h[len("http://"):]
        elif h.startswith("https://"):
            h = h[len("https://"):]
        return h.rstrip("/")

    def definir_host(self, novo_host: str) -> None:
        h = self._limpar_host(novo_host)
        self.host_configurado = h
        self.host_ativo = h
        self.esp_ip_descoberto = h

    def registrar_contato_wifi(self, ip_cliente: str):
        self.ultimo_contato_wifi = time.time()
        self.ip_ultimo_esp32 = ip_cliente
        self.esp_ip_descoberto = ip_cliente
        self.host_ativo = ip_cliente
        self.conectado = True
        self.mensagem_status = f"Wi-Fi Conectado ({ip_cliente})"

    def wifi_ativo_recentemente(self, janela_segundos: float = 15.0) -> bool:
        return (time.time() - self.ultimo_contato_wifi) <= janela_segundos

    def obter_ip_local(self) -> str:
        """Retorna o endereço IPv4 da máquina/celular na rede Wi-Fi local."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def obter_todos_ips_locais(self) -> List[str]:
        """Lista todos os IPs IPv4 ativos das interfaces de rede."""
        ips: List[str] = []
        ip_principal = self.obter_ip_local()
        if ip_principal and not ip_principal.startswith("127."):
            ips.append(ip_principal)
        try:
            _, _, lista = socket.gethostbyname_ex(socket.gethostname())
            for ip in lista:
                if ip and not ip.startswith("127.") and ip not in ips:
                    ips.append(ip)
        except Exception:
            pass
        return ips

    def iniciar_servidor_wifi(self, porta: int = 5000):
        """Inicia o servidor HTTP (porta 5000) e o respondedor UDP para o ESP32 encontrar o app automaticamente."""
        self.http_port = porta
        if self.http_server is None:
            try:
                _ESP32RequestHandler.hw_manager = self
                self.http_server = ThreadingHTTPServer(("0.0.0.0", porta), _ESP32RequestHandler)
                self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
                self.http_thread.start()
                ip_local = self.obter_ip_local()
                print(f"[HARDWARE WIFI] Servidor HTTP ativo em http://{ip_local}:{porta}")
            except Exception as e:
                print(f"[HARDWARE WIFI] Aviso: Não foi possível iniciar servidor HTTP na porta {porta}: {e}")

        if self.udp_thread is None or not self.udp_thread.is_alive():
            self.udp_thread = threading.Thread(target=self._loop_udp_discovery, args=(porta,), daemon=True)
            self.udp_thread.start()

        if self.esp_client_thread is None or not self.esp_client_thread.is_alive():
            self.esp_client_thread = threading.Thread(target=self._loop_cliente_esp32_wifi, daemon=True)
            self.esp_client_thread.start()

    def _loop_udp_discovery(self, porta_udp: int):
        """Escuta pacotes UDP de broadcast do ESP32 ('DISCOVER_MULTILOG') e responde com o IP."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", porta_udp))
            sock.settimeout(1.5)
            print(f"[HARDWARE WIFI] Descoberta automática UDP ativa na porta {porta_udp}")
        except Exception as e:
            print(f"[HARDWARE WIFI] Aviso UDP Discovery ({porta_udp}): {e}")
            return

        while True:
            try:
                data, addr = sock.recvfrom(256)
                msg = data.decode("utf-8", errors="ignore").strip()
                if msg.startswith("DISCOVER_MULTILOG"):
                    self.registrar_contato_wifi(addr[0])
                    resposta = f"MULTILOG_PC_OK:{self.http_port}".encode("utf-8")
                    sock.sendto(resposta, addr)
            except socket.timeout:
                if not self.rodando and self.http_server is None:
                    break
            except Exception:
                time.sleep(0.5)

    def _sondar_ip_esp32(self, ip: str, timeout: float = 0.35) -> bool:
        """Testa se o IP informado responde como o servidor HTTP do ESP32 (porta 80 /status)."""
        ip_local = self.obter_ip_local()
        url = f"http://{ip}/status?pc_ip={ip_local}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                if resp.status == 200:
                    raw = resp.read().decode("utf-8", errors="ignore")
                    dados = json.loads(raw)
                    if isinstance(dados, dict) and dados.get("ok") is True and "peso" in dados:
                        return True
        except Exception:
            pass
        return False

    def _descobrir_esp32_na_rede(self) -> Optional[str]:
        """Localiza automaticamente o IP do ESP32 na mesma rede Wi-Fi."""
        # 0. Testa primeiro o host configurado manualmente ou último IP conhecido
        for candidato in [self.esp_ip_descoberto, self.ip_ultimo_esp32, self.host_configurado, "192.168.4.1"]:
            if candidato and self._sondar_ip_esp32(candidato, timeout=0.6):
                return candidato

        # 1. Tenta resolver via mDNS (esp32-logistica.local)
        try:
            ip_mdns = socket.gethostbyname("esp32-logistica.local")
            if ip_mdns and self._sondar_ip_esp32(ip_mdns, timeout=0.8):
                return ip_mdns
        except Exception:
            pass

        # 2. Varre as sub-redes locais /24 em paralelo (rápido ~1.5s)
        subredes = set()
        for ip in self.obter_todos_ips_locais():
            partes = ip.split(".")
            if len(partes) == 4:
                # Evita varrer redes virtuais de emuladores Android (10.0.2.x) se desnecessário, mas permite 192.168.x.x / 10.x / 172.x
                subredes.add(".".join(partes[:3]))

        ips_locais = set(self.obter_todos_ips_locais())
        for prefixo in subredes:
            candidatos = [f"{prefixo}.{i}" for i in range(1, 255) if f"{prefixo}.{i}" not in ips_locais]
            encontrado: Optional[str] = None
            with ThreadPoolExecutor(max_workers=48) as pool:
                futuros = {pool.submit(self._sondar_ip_esp32, ip, 0.35): ip for ip in candidatos}
                for fut in as_completed(futuros):
                    ip_cand = futuros[fut]
                    try:
                        if fut.result():
                            encontrado = ip_cand
                            break
                    except Exception:
                        pass
            if encontrado:
                return encontrado
        return None

    def _loop_cliente_esp32_wifi(self):
        """
        Cliente ativo: conecta diretamente na porta 80 do ESP32 (GET http://<ip_esp32>/status).
        Funciona mesmo quando o Firewall bloqueia conexões de entrada.
        """
        falhas_seguidas = 0
        while True:
            if not self.rodando and self.http_server is None:
                break

            if not self.esp_ip_descoberto:
                ip_achado = self._descobrir_esp32_na_rede()
                if ip_achado:
                    self.esp_ip_descoberto = ip_achado
                    self.host_ativo = ip_achado
                    self.registrar_contato_wifi(ip_achado)
                    falhas_seguidas = 0
                    print(f"[HARDWARE WIFI] Conectado diretamente ao ESP32 em http://{ip_achado}/status")
                else:
                    if not (self.serial_conn and getattr(self.serial_conn, "is_open", False)):
                        self.conectado = False
                        self.mensagem_status = f"Offline / Simulador ({self.host_configurado})"
                    time.sleep(2.5)
                    continue

            ip_esp = self.esp_ip_descoberto
            ip_local = self.obter_ip_local()
            cmd_pendente = ""
            if not (self.serial_conn and getattr(self.serial_conn, "is_open", False)):
                cmd_pendente = self.consumir_comando_wifi()

            params = {"pc_ip": ip_local}
            if cmd_pendente:
                params["cmd"] = cmd_pendente
            query = urllib.parse.urlencode(params)
            url = f"http://{ip_esp}/status?{query}"

            try:
                with urllib.request.urlopen(url, timeout=0.9) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                    dados = json.loads(raw)

                falhas_seguidas = 0
                self.registrar_contato_wifi(ip_esp)

                if "peso" in dados:
                    try:
                        self._notificar_peso_recebido(float(dados["peso"]))
                    except (ValueError, TypeError):
                        pass

                tag_seq = int(dados.get("tag_seq", 0) or 0)
                tag_str = str(dados.get("tag") or dados.get("ultima_tag") or "").strip()

                if self.ultimo_tag_seq_esp == -1:
                    # Na primeira conexão, sincroniza o contador para não disparar tag antiga
                    self.ultimo_tag_seq_esp = tag_seq
                    if tag_seq > 0:
                        try:
                            urllib.request.urlopen(
                                f"http://{ip_esp}/status?pc_ip={ip_local}&ack_seq={tag_seq}",
                                timeout=0.6,
                            ).read()
                        except Exception:
                            pass
                elif tag_seq > 0 and tag_seq != self.ultimo_tag_seq_esp and tag_str:
                    self.ultimo_tag_seq_esp = tag_seq
                    tag_fmt = self._formatar_uid(tag_str)
                    nome_lcd = "Nao Cadastrado"
                    if tag_fmt:
                        nome_lcd, _ = self.obter_nome_item_para_lcd(tag_fmt)
                        self._notificar_rfid_recebido(tag_fmt, origem="WIFI")

                    # Envia o nome do item e o ACK imediatamente para o LCD 16x2 do ESP32
                    ack_q = urllib.parse.urlencode(
                        {"pc_ip": ip_local, "ack_seq": tag_seq, "item": nome_lcd[:16]}
                    )
                    try:
                        urllib.request.urlopen(f"http://{ip_esp}/status?{ack_q}", timeout=0.8).read()
                    except Exception:
                        pass

                time.sleep(0.22)
            except Exception:
                falhas_seguidas += 1
                if falhas_seguidas >= 4:
                    print(f"[HARDWARE WIFI] Sem resposta de {ip_esp}; redescobrindo ESP32 na rede...")
                    self.esp_ip_descoberto = None
                    self.ultimo_tag_seq_esp = -1
                    if not (self.serial_conn and getattr(self.serial_conn, "is_open", False)):
                        self.conectado = False
                        self.mensagem_status = f"Offline / Simulador ({self.host_configurado})"
                    falhas_seguidas = 0
                time.sleep(0.5)

    def enfileirar_comando_wifi(self, comando: str):
        cmd_limpo = (comando or "").strip()
        if not cmd_limpo:
            return
        with self._lock_fila:
            if len(self._fila_comandos_wifi) < 30:
                self._fila_comandos_wifi.append(cmd_limpo)

    def consumir_comando_wifi(self) -> str:
        with self._lock_fila:
            if not self._fila_comandos_wifi:
                return ""
            cmds = list(self._fila_comandos_wifi)
            self._fila_comandos_wifi.clear()
            return "|".join(cmds)

    def obter_nome_item_para_lcd(self, tag_uid: str) -> tuple[str, bool]:
        """Consulta o banco de dados pelo UID da tag e retorna (nome_ascii_16_chars, encontrado)."""
        try:
            if self.resolver_nome_custom is not None:
                nome_custom = self.resolver_nome_custom(tag_uid)
                if nome_custom:
                    nome_limpo = _remover_acentos_ascii(nome_custom)
                    return (nome_limpo[:16] if nome_limpo else "Tag Lida"), True

            peca = database.get_peca_por_rfid(tag_uid)
            if peca and peca.get("nome"):
                nome_limpo = _remover_acentos_ascii(str(peca["nome"]))
                return (nome_limpo[:16] if nome_limpo else "Item OK"), True

            usuario = database.get_usuario_por_rfid(tag_uid)
            if usuario and usuario.get("nome"):
                prefixo = "ADM " if usuario.get("role") == "ADMIN" else "OP "
                nome_usr = _remover_acentos_ascii(prefixo + str(usuario["nome"]))
                return (nome_usr[:16] if nome_usr else "Usuario OK"), True
        except Exception as e:
            print(f"[HARDWARE] Erro ao consultar banco para LCD: {e}")
        return "Nao Cadastrado", False

    def detectar_porta_esp32(self) -> Optional[str]:
        """Busca automaticamente a porta COM onde o ESP32 (CP210x, CH340, USB Serial) está conectado."""
        if not HAS_SERIAL or serial is None:
            return None
        try:
            portas = list(serial.tools.list_ports.comports())
            palavras_chave = ["CP210", "CH340", "CH910", "USB", "UART", "SERIAL", "SILICON LABS", "ESP32"]
            for p in portas:
                desc = f"{p.description} {p.manufacturer or ''}".upper()
                if any(k in desc for k in palavras_chave):
                    return p.device
            if portas:
                return portas[0].device
        except Exception:
            pass
        return None

    def conectar(self, porta: Optional[str] = None) -> bool:
        """
        Inicia a thread de comunicação Serial/Wi-Fi.
        Se 'porta' parecer um endereço IP (ex: '192.168.1.50'), define o host Wi-Fi e testa a conexão HTTP.
        """
        if porta and ("." in porta or porta.startswith("http")):
            self.definir_host(porta)
            self.iniciar_servidor_wifi(self.http_port)
            self.rodando = True
            if self._sondar_ip_esp32(self.host_configurado, timeout=1.2):
                self.registrar_contato_wifi(self.host_configurado)
                return True
            self.conectado = False
            self.mensagem_status = f"Offline / Simulador ({self.host_configurado})"
            return False

        self.iniciar_servidor_wifi(self.http_port)

        if self.rodando and self.thread and self.thread.is_alive():
            return self.esta_conectado()

        self.porta_atual = porta
        self.rodando = True
        if HAS_SERIAL:
            self.thread = threading.Thread(target=self._loop_leitura, daemon=True)
            self.thread.start()
        return True

    def iniciar_monitoramento_background(self):
        """Inicia o servidor Wi-Fi, descoberta UDP, cliente HTTP ESP32 e thread Serial sem bloquear a abertura do app."""
        self.conectar()

    def desconectar(self):
        self.rodando = False
        self.conectado = False
        self.mensagem_status = "Desconectado"
        if self.serial_conn and getattr(self.serial_conn, "is_open", False):
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.serial_conn = None

    def esta_conectado(self) -> bool:
        serial_ok = bool(self.serial_conn is not None and getattr(self.serial_conn, "is_open", False))
        return serial_ok or self.wifi_ativo_recentemente() or self.conectado

    def registrar_callback_rfid(self, callback: Callable[[str], None]):
        if callback not in self.callbacks_rfid:
            self.callbacks_rfid.append(callback)

    def desregistrar_callback_rfid(self, callback: Callable[[str], None]):
        if callback in self.callbacks_rfid:
            self.callbacks_rfid.remove(callback)

    def registrar_callback_peso(self, callback: Callable[[float], None]):
        if callback not in self.callbacks_peso:
            self.callbacks_peso.append(callback)

    def desregistrar_callback_peso(self, callback: Callable[[float], None]):
        if callback in self.callbacks_peso:
            self.callbacks_peso.remove(callback)

    def enviar_comando(self, comando: str) -> bool:
        """Envia comando para o ESP32 via Serial USB (se conectado) e também enfileira para Wi-Fi."""
        cmd_limpo = comando.strip()
        enviou_serial = False
        if self.serial_conn and getattr(self.serial_conn, "is_open", False):
            try:
                linha = cmd_limpo + "\n"
                self.serial_conn.write(linha.encode("utf-8"))
                self.serial_conn.flush()
                enviou_serial = True
            except Exception as e:
                print(f"[HARDWARE] Erro ao enviar comando '{cmd_limpo}': {e}")

        # Sempre enfileira também para o canal Wi-Fi caso o ESP32 esteja operando sem fio
        if not enviou_serial:
            self.enfileirar_comando_wifi(cmd_limpo)
        return enviou_serial or self.wifi_ativo_recentemente()

    def enviar_nome_lcd(self, nome_item: str):
        """Envia o nome da peça para ser exibido na segunda linha do LCD 16x2 do ESP32."""
        nome_ascii = _remover_acentos_ascii(nome_item)[:16] or "Item OK"
        self.enviar_comando(f"ITEM:{nome_ascii}")

    def acender_led(self, linha: int, coluna: int):
        """Envia comando para acender o LED físico correspondente à gaveta (converte 0-based para 1-based no ESP32)."""
        l_1based = linha + 1 if linha in (0, 1) else linha
        c_1based = coluna + 1 if coluna in (0, 1, 2) else coluna
        self.led_atual = (l_1based, c_1based)
        self.enviar_comando(f"LED:{l_1based},{c_1based}")

    def apagar_led(self):
        self.led_atual = None
        self.enviar_comando("LED:OFF")

    def tarar_balanca(self):
        self.ultimo_peso = 0.0
        self.enviar_comando("TARA")
        for cb in list(self.callbacks_peso):
            try:
                cb(0.0)
            except Exception:
                pass

    def acionar_buzzer_erro(self):
        """Aciona o buzzer sonoro no pino D2 do ESP32 (com cooldown de 1.2s para não saturar)."""
        agora = time.time()
        if (agora - self.ultimo_erro_buzzer_ts) < 1.2:
            return
        self.ultimo_erro_buzzer_ts = agora
        self.enviar_comando("BUZZER:ERRO")

    def ler_ultimo_peso(self) -> float:
        return self.ultimo_peso

    def simular_leitura_rfid(self, tag: str):
        """Permite simular ou injetar uma leitura de tag RFID diretamente pelo app."""
        tag_fmt = self._formatar_uid(tag)
        if not tag_fmt:
            return
        self._notificar_rfid_recebido(tag_fmt, origem="SIMULADOR")

    def simular_peso(self, peso: float):
        """Permite simular o peso na balança diretamente pelo app."""
        self._notificar_peso_recebido(float(peso))

    def _formatar_uid(self, raw_uid: str) -> str:
        """Formata qualquer string hexadecimal de UID no padrão 'C4 AE 78 E5'."""
        limpo = raw_uid.replace(":", "").replace("-", "").replace(" ", "").strip().upper()
        if len(limpo) >= 8 and len(limpo) % 2 == 0:
            partes = [limpo[i:i + 2] for i in range(0, len(limpo), 2)]
            return " ".join(partes)
        return raw_uid.strip().upper()

    def _notificar_peso_recebido(self, val: float):
        self.ultimo_peso = val
        for cb in list(self.callbacks_peso):
            try:
                cb(val)
            except Exception as e:
                print(f"[HARDWARE] Erro no callback de Peso: {e}")

    def _notificar_rfid_recebido(self, tag_formatada: str, origem: str = "SERIAL"):
        if not tag_formatada:
            return
        agora = time.time()
        # Evita disparo duplo quando o ESP32 está conectado no USB E no Wi-Fi ao mesmo tempo
        if (
            tag_formatada == self._ultimo_rfid_notificado_tag
            and (agora - self._ultimo_rfid_notificado_ts) < self.janela_dedup_rfid_s
        ):
            print(f"[HARDWARE] Tag RFID duplicada ignorada ({origem}): {tag_formatada}")
            return

        self._ultimo_rfid_notificado_tag = tag_formatada
        self._ultimo_rfid_notificado_ts = agora
        self.ultima_tag = tag_formatada
        print(f"[HARDWARE {origem}] Tag RFID Lida: {tag_formatada}")
        for cb in list(self.callbacks_rfid):
            try:
                cb(tag_formatada)
            except Exception as e:
                print(f"[HARDWARE] Erro no callback de RFID: {e}")

    def _processar_linha(self, linha: str):
        linha = linha.strip()
        if not linha:
            return

        upper = linha.upper()

        # 1. Formato estruturado: RFID:C4 AE 78 E5
        if upper.startswith("RFID:"):
            raw_tag = linha.split(":", 1)[1].strip()
            tag_formatada = self._formatar_uid(raw_tag)
            if tag_formatada:
                nome_lcd, _ = self.obter_nome_item_para_lcd(tag_formatada)
                self.enviar_nome_lcd(nome_lcd)
                self._notificar_rfid_recebido(tag_formatada, origem="SERIAL")
            return

        # 2. Formato legado do MFRC522: "UID da tag : C4 AE 78 E5"
        if "UID DA TAG" in upper and ":" in linha:
            raw_tag = linha.split(":", 1)[1].strip()
            tag_formatada = self._formatar_uid(raw_tag)
            if tag_formatada:
                nome_lcd, _ = self.obter_nome_item_para_lcd(tag_formatada)
                self.enviar_nome_lcd(nome_lcd)
                self._notificar_rfid_recebido(tag_formatada, origem="SERIAL")
            return

        # 3. Formato estruturado de Peso: PESO:125.4
        if upper.startswith("PESO:"):
            raw_peso = linha.split(":", 1)[1].strip().replace("g", "").replace("G", "").strip()
            try:
                val = float(raw_peso)
                self._notificar_peso_recebido(val)
            except ValueError:
                pass
            return

    def _loop_leitura(self):
        if not HAS_SERIAL or serial is None:
            return
        while self.rodando:
            if self.serial_conn is None or not self.serial_conn.is_open:
                porta = self.porta_atual or self.detectar_porta_esp32()
                if porta:
                    try:
                        self.serial_conn = serial.Serial(porta, self.baudrate, timeout=0.2)
                        self.conectado = True
                        self.mensagem_status = f"USB Serial ({porta})"
                        print(f"[HARDWARE] Conectado ao ESP32 na porta {porta} ({self.baudrate} bps)")
                        time.sleep(0.5)
                        ip_pc = self.obter_ip_local()
                        self.enviar_comando(f"PCIP:{ip_pc}:{self.http_port}")
                    except Exception:
                        self.serial_conn = None
                        time.sleep(2.0)
                        continue
                else:
                    time.sleep(2.0)
                    continue

            try:
                if self.serial_conn.in_waiting > 0:
                    raw = self.serial_conn.readline()
                    linha = raw.decode("utf-8", errors="ignore").strip()
                    if linha:
                        self._processar_linha(linha)
                else:
                    time.sleep(0.03)
            except Exception as e:
                print(f"[HARDWARE] Conexão serial perdida ({e}). Tentando reconectar...")
                try:
                    if self.serial_conn:
                        self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None
                time.sleep(1.5)
