# Robô de toque para testes Appium (Bambu Lab P1S + Moto G06)

Usa a P1S como robô cartesiano: o cabeçote leva uma ponteira (borracha touch) até o
ponto da tela e a mesa sobe/desce para tocar. Os testes Appium continuam iguais:
o Appium localiza o elemento, o robô faz o toque físico.

```
Teste Appium → element.rect (centro em px)
      ↓
RobotTap: px → mm (calibração) → G-code
      ↓ MQTT/TLS (modo LAN)
P1S → ponteira toca a tela
```

> **Status:** a lógica (conversão, limites de segurança, geração de G-code, parser do
> `getevent`, soak) tem testes automáticos que passam. **Testado no hardware:** conexão
> MQTT com a P1S, homing, movimento e desenho com caneta no papel; Appium no Moto G06 pelo
> Wi-Fi (ainda com os testes em JS). **Ainda não testado:** os testes Robot com a tela
> desbloqueada, toque na tela com a ponteira, calibração e soak real.
> Faça o primeiro uso com calma, seguindo [docs/montagem.md](docs/montagem.md).

## Começo rápido

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
source .venv/bin/activate
python -m pytest                                              # testes da lógica, sem hardware

appium                                                        # em outro terminal
robot -d results -e addnumber robot/tests                     # testes no celular (clique por software)
robot -d results -e addnumber -v ROBO:True -v SIMULADO:True robot/tests   # com o robô simulado
python -m soak run soak/examples/apidemos_soak.yaml --dry-run # soak simulado, ~2 min
```

O celular (Moto G06) é encontrado sozinho, no cabo USB ou na Depuração por Wi-Fi, e
precisa estar com a tela desbloqueada. Para usar a P1S de verdade, siga a montagem e a
calibração antes.

## Documentação

| Para | Leia |
|---|---|
| Preparar a P1S, montar a ponteira, regras de segurança e calibrar | [docs/montagem.md](docs/montagem.md) |
| Escrever e rodar testes Appium (Robot Framework) com toque físico | [docs/testes-robot.md](docs/testes-robot.md) |
| Teste de resistência (soak) e de consumo de bateria | [docs/soak.md](docs/soak.md) |
| Limitações e solução de problemas | [docs/problemas.md](docs/problemas.md) |
| Por que o projeto é assim, aprendizados no hardware e pendências | [docs/decisoes.md](docs/decisoes.md) |

## Segurança, em resumo

- **Homing (G28) sempre com a mesa vazia** e sem o módulo da ponteira no cabeçote.
- `motion.z_floor` é o Z mínimo permitido: o código bloqueia qualquer movimento abaixo dele.
- Nas primeiras execuções, mantenha a mão perto do botão de energia da P1S.
- `config.yaml` (com o access code) e `calibration.json` nunca vão para o git.

## Estrutura

```
taprobot/      biblioteca do robô (bambu.py MQTT, robot.py gestos, calibration.py,
               touch_reader.py, adb.py, device.py busca do celular, simulated.py)
robot/         testes Appium em Robot Framework (bibliotecas, resources, testes)
soak/          teste de resistência e de consumo (cenário, coletor, guardião, relatório)
tools/         linha de comando: calibrate, test_connection, server (python -m tools.<nome>)
tests/         testes unitários da lógica (sem hardware): python -m pytest tests -q
apps/          APK de exemplo (ApiDemos)
docs/          decisões e aprendizados
results/       saída do Robot (não versionar)
runs/          execuções do soak (não versionar)
```
