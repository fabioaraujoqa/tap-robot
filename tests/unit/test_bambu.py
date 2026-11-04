"""BambuLink sem rede: confirmação dos comandos enviados à impressora."""
import json
from types import SimpleNamespace

import pytest

from taprobot import BambuError, BambuLink


class FakeClient:
    """Responde (ou não) a cada publicação, como o broker da P1S."""

    def __init__(self, link, result=None):
        self.link, self.result = link, result

    def publish(self, topic, payload, qos=0):
        if self.result is not None:
            seq = json.loads(payload)["print"]["sequence_id"]
            body = {"print": {"command": "gcode_line", "sequence_id": seq, "result": self.result}}
            self.link._on_message(None, None, SimpleNamespace(payload=json.dumps(body)))
        return SimpleNamespace(wait_for_publish=lambda timeout=None: None)


def make_link(result=None):
    link = BambuLink("192.0.2.1", "SERIAL", "CODE", ack_timeout=0.01)
    link._client = FakeClient(link, result)
    return link


def test_comando_confirmado_devolve_a_resposta():
    assert make_link("success").send_gcode("G90")["result"] == "success"


def test_comando_sem_confirmacao_e_erro():
    with pytest.raises(BambuError, match="sem confirmação"):
        make_link().send_gcode("G90")


def test_comando_recusado_e_erro():
    with pytest.raises(BambuError, match="recusou"):
        make_link("failed").send_gcode("G90")


def test_sem_esperar_confirmacao_nao_e_erro():
    assert make_link().send_gcode("G90", wait_ack=False) is None
