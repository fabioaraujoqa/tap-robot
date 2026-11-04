# Testes Appium com Robot Framework

Os testes ficam em `tests/robot/`, no estilo palavra-chave do Robot Framework + AppiumLibrary.
O Appium localiza o elemento; com `ROBO=True`, o toque é feito pela ponteira da P1S.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
appium                                                        # outro terminal

robot -d results tests/robot/funcionais tests/robot/e2e                               # clique por software
robot -d results -v ROBO:True tests/robot/funcionais tests/robot/e2e                  # toque físico (P1S calibrada)
robot -d results -v ROBO:True -v SIMULADO:True tests/robot/funcionais tests/robot/e2e # robô simulado, sem a P1S
robot -d results -e addnumber tests/robot/funcionais                                  # sem o AddNumber (exige instalar à mão)
```

```
tests/robot/
  libraries/TapRobotLibrary.py      palavras-chave do robô físico (envolve o RobotTap)
  resources/base.resource           sessão Appium; acha o celular sozinho (USB ou Wi-Fi)
  resources/robo.resource           "Clicar": físico com ROBO=True, por software sem
  resources/pages/*.resource        seletores e ações de cada tela
  funcionais/*.robot                casos de teste funcionais
  e2e/*.robot                       e2e curtos, os únicos que usam o braço
  nao_funcionais/                   suíte não funcional (tem README próprio)
```

**Palavras-chave do robô** (`TapRobotLibrary`), todas em pixels da tela:
`Conectar Robô`, `Desconectar Robô` (estaciona a ponteira), `Toque Físico No Elemento`,
`Toque Longo Físico No Elemento`, `Toque Físico Em Coordenada`,
`Toque Longo Físico Em Coordenada`, `Arraste Físico`, `Arraste Físico Entre Elementos`,
`Estacionar Ponteira`, `Descobrir Celular`. Nos testes, use as palavras-chave de
`robo.resource` (`Clicar`, `Tocar em coordenada`, `Arrastar`, `Arrastar entre elementos`):
o mesmo teste roda com ou sem o robô.

Com o robô real, cada gesto só passa se o celular sentir o contato (`getevent`), sem olhar o
app. `tests/robot/e2e/e2e_gestos.robot` usa só isso: toca e arrasta para os testes não funcionais.

Um teste novo segue o padrão de `tests/robot/funcionais/apidemos.robot`: seletores e ações num
`.resource` em `pages/`, e o `.robot` só com os passos legíveis.

- **Celular:** sem `-v UDID:...`, o `base.resource` acha o Moto G06 sozinho, no cabo USB ou
  na Depuração por Wi-Fi (descobre o IP:porta e faz o `adb connect`; precisa ter pareado
  uma vez com `adb pair`). Só conectar: `python -m taprobot.device`.
  Outro aparelho: `-v UDID:<serial ou IP:porta>`.
- **Tela desbloqueada:** com a tela de bloqueio aparecendo, o app abre por trás dela e
  nenhum elemento é encontrado.
- **Simulado:** o G-code de cada toque vai para o `log.html` e o teste também clica por
  software para seguir em frente. Valida os testes sem hardware; as coordenadas em mm
  não significam nada.
- O robô roda **no mesmo processo** do Robot: o `Desconectar Robô` do teardown estaciona a
  ponteira mesmo quando o teste falha.

Observações:
- O Appium segue fazendo digitação, capturas de tela e esperas por software. Só o toque é físico.
- Toques fora da tela (elemento parcialmente visível com centro fora) geram erro claro.
- Cada toque leva ~1–2 s (descer devagar protege a tela). Depois que tudo estiver estável,
  aumente `feed_z_touch`/`feed_xy` no config e reduza `tap_dwell_ms` para acelerar.

## Outras formas de usar o robô

- **Servidor HTTP** (`python -m tools.server`, `--dry-run` sem a impressora): expõe o robô
  para testes em qualquer linguagem. Rotas `GET /health`, `POST /tap`, `/long_press`,
  `/swipe`, `/park`, sempre em pixels; cada chamada só responde quando o movimento estimado
  termina. Escuta só em `127.0.0.1` e **não tem autenticação**: não exponha na rede.
- **Python direto:** `from taprobot import simulated_robot, RobotTap` e use `tap_px`,
  `swipe_px` e `long_press_px` (é o que a `TapRobotLibrary` faz por baixo).
