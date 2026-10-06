"""Conexão MQTT (modo LAN) com a Bambu Lab P1S para enviar G-code.

Requer na impressora: Modo LAN + Modo Desenvolvedor ligados. A impressora expõe
um broker MQTT em TLS na porta 8883 (usuário "bblp", senha = access code).
O formato do comando segue o que a comunidade documentou para a linha P1/X1;
confira se o firmware da sua impressora continua aceitando "gcode_line".
"""
from __future__ import annotations

import json
import logging
import random
import ssl
import threading

import paho.mqtt.client as mqtt

log = logging.getLogger("taprobot.bambu")


class BambuError(RuntimeError):
    pass


class BambuLink:
    def __init__(self, ip, serial, access_code, port=8883, ack_timeout=3.0):
        self.ip = ip
        self.serial = serial
        self.access_code = access_code
        self.port = port
        self.ack_timeout = ack_timeout
        self.request_topic = f"device/{serial}/request"
        self.report_topic = f"device/{serial}/report"

        self._client = None
        self._connected = threading.Event()
        self._connect_error = None
        self._lock = threading.Lock()
        self._seq = random.randint(10_000, 900_000)
        self._pending: dict[str, threading.Event] = {}
        self._results: dict[str, dict] = {}

    # ------------------------------------------------------------------ conexão
    def connect(self, timeout: float = 10.0):
        client_id = f"taprobot-{random.randint(0, 999_999)}"
        try:  # paho-mqtt 2.x
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        except AttributeError:  # paho-mqtt 1.x
            client = mqtt.Client(client_id=client_id)

        client.username_pw_set("bblp", self.access_code)

        # A impressora usa certificado autoassinado, então não há como validar a
        # cadeia. O tráfego é só dentro da sua rede local.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        client.tls_set_context(ctx)

        client.on_connect = self._on_connect
        client.on_message = self._on_message
        self._client = client

        client.connect(self.ip, self.port, keepalive=30)
        client.loop_start()
        if not self._connected.wait(timeout):
            self.close()
            raise BambuError(
                self._connect_error
                or f"timeout conectando em {self.ip}:{self.port} (IP correto? Modo LAN ligado?)"
            )
        if self._connect_error:
            self.close()
            raise BambuError(self._connect_error)
        log.info("conectado à P1S %s", self.serial)

    def close(self):
        if self._client is not None:
            try:
                # Nesta ordem: com loop_stop() antes, o join da thread de rede fica
                # esperando para sempre (paho-mqtt 2.x com a P1S).
                self._client.disconnect()
                self._client.loop_stop()
            finally:
                self._client = None

    def _on_connect(self, client, userdata, flags, rc, *args):
        failed = rc.is_failure if hasattr(rc, "is_failure") else rc != 0
        if failed:
            self._connect_error = f"conexão MQTT recusada (código {rc}); confira o access code"
        else:
            client.subscribe(self.report_topic)
        self._connected.set()

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except ValueError:
            return
        body = payload.get("print")
        if not isinstance(body, dict) or body.get("command") != "gcode_line":
            return
        seq = str(body.get("sequence_id"))
        with self._lock:
            event = self._pending.get(seq)
            if event is not None:
                self._results[seq] = body
                event.set()

    # ------------------------------------------------------------------ envio
    def send_gcode(self, gcode: str, wait_ack: bool = True):
        """Envia uma ou mais linhas de G-code. Devolve a resposta da impressora (ou None).

        O ack só confirma que o comando foi ACEITO, não que o movimento terminou.
        """
        if self._client is None:
            raise BambuError("não conectado")
        if not gcode.endswith("\n"):
            gcode += "\n"

        with self._lock:
            self._seq += 1
            seq = str(self._seq)
            event = threading.Event()
            self._pending[seq] = event

        payload = {"print": {"sequence_id": seq, "command": "gcode_line", "param": gcode}}
        # qos=0: o broker da P1S não devolve PUBACK, então com qos=1 o wait_for_publish
        # esperava o timeout inteiro a cada comando. A confirmação real é a resposta abaixo.
        info = self._client.publish(self.request_topic, json.dumps(payload), qos=0)
        info.wait_for_publish(timeout=self.ack_timeout)

        if not wait_ack:
            with self._lock:
                self._pending.pop(seq, None)
            return None

        got = event.wait(self.ack_timeout)
        with self._lock:
            self._pending.pop(seq, None)
            result = self._results.pop(seq, None)
        if not got:
            log.warning("sem confirmação da impressora para o comando %s", seq)
            return None
        status = str(result.get("result", "success")).lower()
        if status not in ("success", "ok"):
            raise BambuError(f"impressora recusou o G-code: {result}")
        return result

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()
