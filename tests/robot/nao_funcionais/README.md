# Testes não funcionais

Suíte da palestra "Testes mobile além do funcional". Toda ela roda pelo Appium com UiAutomator2,
por software. O braço robótico só entra no teste 10, que é o único que mede o toque físico.

## Preparar

Os comandos de shell (`dumpsys`, `am start -W`, `getevent`) exigem um servidor Appium com a flag
abaixo. Sem ela, o teste falha na abertura da sessão com uma mensagem explicando isso.

```bash
appium --port 4725 --allow-insecure=uiautomator2:adb_shell
```

Nos comandos abaixo, `NFR` é esta pasta, a partir da raiz do repositório:

```bash
NFR=tests/robot/nao_funcionais
```

Sem `-v UDID:...`, o teste procura o Moto G06. Em emulador, informe `-v UDID:emulator-5554`. O
aparelho precisa estar desbloqueado, senão a sessão falha avisando.

## Testes

| Arquivo | O que mede | Tags | Aparelho |
|---|---|---|---|
| `01_inicializacao` | `TotalTime` frio e morno, p50 e p90 | `emulador`, `aparelho_real` | Qualquer um |
| `02_fluidez_jank` | % de jank rolando `.view.List1` | `emulador`, `aparelho_real` | Qualquer um |
| `03_soak_memoria` | MB/h por regressão, picos e crashes | `emulador`, `aparelho_real`, `longo` | Qualquer um |
| `04_bateria` | %/h com o app em uso | `aparelho_real`, `longo` | Real, fora da tomada |
| `05_sensores` | `sensorSet` e rotação com texto digitado | `emulador` | Emulador |
| `06_rede_resiliencia` | App vivo sem rede e em redes lentas | `emulador` | Emulador |
| `07_interrupcoes` | Estado após chamada, SMS e segundo plano | `emulador` | Emulador |
| `08_camera` | Preview repetido e permissão negada | `emulador`, `aparelho_real` | Qualquer um |
| `09_geolocalizacao` | Rota, salto brusco e GPS desligado | `emulador`, `aparelho_real` | Qualquer um |
| `10_latencia_toque` | Toque físico até a tela mudar, p50 e p95 | `braco` | Real, com a P1S |

## Exemplos

```bash
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 $NFR/01_inicializacao.robot
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 $NFR/02_fluidez_jank.robot
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 $NFR/03_soak_memoria.robot                   # 30 min
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 -v DURACAO_MIN:1440 $NFR/03_soak_memoria.robot  # 24 h
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 $NFR/04_bateria.robot                        # fora da tomada
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 -v UDID:emulator-5554 $NFR/05_sensores.robot
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 -v UDID:emulator-5554 $NFR/06_rede_resiliencia.robot
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 -v UDID:emulator-5554 $NFR/07_interrupcoes.robot
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 $NFR/08_camera.robot
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 $NFR/09_geolocalizacao.robot
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 -v ROBO:True $NFR/10_latencia_toque.robot   # P1S calibrada

robot --dryrun --output NONE --log NONE --report NONE $NFR                     # só sintaxe
robot -d results -v APPIUM_URL:http://127.0.0.1:4725 -v UDID:emulator-5554 -i emulador -e longo $NFR
```

## Limites e resultados

- **Limites:** ficam em `resources/nfr_limites.py` e são provisórios até uma rodada de referência.
  Qualquer um pode ser trocado na linha de comando, como `-v SOAK_MB_POR_HORA_MAX:15`.
- **CSV:** cada teste grava em `results/nfr/<tipo>_<data-hora>.csv`, linha a linha, então os dados
  sobrevivem se o teste cair no meio.

## Gráficos

```bash
pip install -e .[graficos]
python $NFR/scripts/gerar_graficos.py     # PNGs em results/nfr/graficos/
```

Gera memória, p95 da latência e bateria, a partir do CSV mais recente de cada tipo.

## O que estes testes não provam

- **Rede e GPS:** o ApiDemos não usa rede nem tem tela de GPS. Os testes 06 e 09 mostram que o
  app sobrevive às mudanças, não que ele reage bem a elas.
- **Soak curto:** poucos minutos não indicam vazamento. A inclinação só diz algo em rodadas longas.
- **Bateria:** se o aparelho carregar durante o teste, o resultado é SKIP, não aprovação.
