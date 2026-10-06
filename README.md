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

> Decisões de arquitetura, aprendizados no hardware real e pendências:
> [docs/decisoes.md](docs/decisoes.md).

> **Status:** a lógica (conversão, limites de segurança, geração de G-code, parser do
> `getevent`, soak) tem testes automáticos que passam. **Testado no hardware:** conexão
> MQTT com a P1S, homing, movimento e desenho com caneta no papel; Appium no Moto G06 pelo
> Wi-Fi. **Ainda não testado:** toque na tela com a ponteira, calibração e soak real.
> Faça o primeiro uso com calma, seguindo a ordem abaixo.

## 1. Preparar a P1S

1. Na tela da impressora: ative **Modo LAN** e **Modo Desenvolvedor** (os nomes mudam
   com o firmware). Anote **IP**, **número de série** e **access code**.
2. Copie `config.example.yaml` para `config.yaml` e preencha. Não versione esse arquivo.
3. `pip install -r requirements.txt`
4. `python -m tools.test_connection --latency`: conecta, envia um comando inofensivo e mede o
   tempo de resposta. Se aparecer "sem ack", o formato do comando pode ter mudado no
   seu firmware (veja *Solução de problemas*).

## 2. Mecânica

- **Gabarito do celular:** o modelo usado ainda vai ser adicionado ao projeto. Requisitos:
  prender o Moto G06 (171,35 × 77,5 × 8,31 mm) só pelos cantos, deixando livres os botões
  laterais e a entrada USB-C, e ficar preso na mesa sempre no mesmo lugar (marque a
  posição com fita).
- **Suporte da ponteira** (depende do seu cabeçote, então não vem pronto). Requisitos:
  1. A ponta da ponteira passa **abaixo do bico** (pelo menos ~5 mm), senão o bico bate
     no celular antes da ponteira.
  2. **Mola ou folga elástica** de 1–2 mm no sentido vertical.
  3. Fixação firme, sem nada aquecendo. Testado: o "P1/X1 Pen Plotter Module" do
     MakerWorld, que encaixa no cabeçote e tem mola (ver `docs/decisoes.md`).
  4. Se a ponteira ficar deslocada do bico, tudo bem para a calibração (ela absorve o
     deslocamento), mas a área alcançável da tela diminui. Ajuste `x_min/x_max/y_min/y_max`.
- Telas capacitivas às vezes exigem **aterramento**: se o celular não sentir o toque, ligue
  a espuma/borracha condutiva por um fio ao corpo do celular.
- A tela útil do G06 é ≈ 70 × 160 mm. A tela fica a `espessura da base + 8,31 mm` acima
  da mesa; esse valor entra no cálculo do `motion.z_floor`.

## 3. Segurança (leia antes de mover qualquer coisa)

- **Faça o homing (G28) com a mesa VAZIA.** Em alguns modelos o homing em Z encosta o
  bico/cabeçote na mesa; com o celular montado isso poderia esmagá-lo.
  `python -m tools.test_connection --home --bed-empty` e só depois monte gabarito e celular.
  Depois disso **não reinicie nem desligue a impressora** durante a sessão, e não
  desative os motores (a posição Z se perde).
- Z na Bambu é a **distância bico–mesa**: Z maior = mesa mais baixa. Tocar = diminuir Z.
- `motion.z_floor` é o **Z mínimo permitido**; o código bloqueia qualquer movimento abaixo
  dele. Comece com um valor **alto** e vá baixando.
- A P1S não tem um "parar já" por software confiável para G-code solto: mantenha a mão
  perto do botão de energia nas primeiras execuções.
- A impressora usa certificado TLS autoassinado, então o código não valida o certificado
  do broker MQTT. Use só em rede local confiável.

## 4. Calibração

Fluxo (≈ 3 minutos, quase todo automático):

```bash
python -m tools.calibrate run
```

1. Você leva a ponteira, por comandos de jog (`x+ 5`, `y- 2`, `z- 10`), até ficar em cima
   da tela, perto do centro (tolerância ±8 mm em X e ±15 mm em Y).
2. O script desce a ponteira de 0,1 em 0,1 mm até o celular sentir o toque
   (lido via `adb shell getevent`) e grava o **Z de contato**.
3. Faz 2 toques de sondagem para descobrir orientação e escala e depois uma grade 3×3
   sobre a tela inteira. A cada toque, o celular diz em que pixel sentiu.
4. Ajusta uma transformação afim, salva em `calibration.json` e mostra o erro máximo
   (bom: < 0,5 mm).

Depois: `python -m tools.calibrate verify` toca 10 pontos e mede o erro real.

Recalibre se mudar a posição do gabarito, a ponteira, ou a resolução/escala de exibição
do celular.

## 5. Testes Appium com Robot Framework

Os testes ficam em `robot/`, no estilo palavra-chave do Robot Framework + AppiumLibrary.
O Appium localiza o elemento; com `ROBO=True`, o toque é feito pela ponteira da P1S.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
appium                                                        # outro terminal

robot -d results robot/tests                                  # clique por software
robot -d results -v ROBO:True robot/tests                     # toque físico (P1S calibrada)
robot -d results -v ROBO:True -v SIMULADO:True robot/tests    # robô simulado, sem a P1S
robot -d results -e addnumber robot/tests                     # sem o AddNumber (exige instalar à mão)
```

```
robot/
  libraries/TapRobotLibrary.py      palavras-chave do robô físico (envolve o RobotTap)
  resources/base.resource           sessão Appium; acha o celular sozinho (USB ou Wi-Fi)
  resources/robo.resource           "Clicar": físico com ROBO=True, por software sem
  resources/pages/*.resource        seletores e ações de cada tela
  tests/*.robot                     casos de teste
```

**Palavras-chave do robô** (`TapRobotLibrary`), todas em pixels da tela:
`Conectar Robô`, `Desconectar Robô` (estaciona a ponteira), `Toque Físico No Elemento`,
`Toque Longo Físico No Elemento`, `Toque Físico Em Coordenada`,
`Toque Longo Físico Em Coordenada`, `Arraste Físico`, `Estacionar Ponteira`,
`Descobrir Celular`. Nos testes, use `Clicar    ${LOCATOR}` (de `robo.resource`): o mesmo
teste roda com ou sem o robô.

Um teste novo segue o padrão de `robot/tests/apidemos.robot`: seletores e ações num
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

### Outras formas de usar o robô

- **Servidor HTTP** (`python -m tools.server`, `--dry-run` sem a impressora): expõe o robô
  para testes em qualquer linguagem. Rotas `GET /health`, `POST /tap`, `/long_press`,
  `/swipe`, `/park`, sempre em pixels; cada chamada só responde quando o movimento estimado
  termina. Escuta só em `127.0.0.1` e **não tem autenticação**: não exponha na rede.
- **pytest:** `examples/conftest_example.py` transforma todo `element.click()` em toque
  físico (`taprobot.appium_patch.physical_clicks`). Exemplo em `examples/appium_example.py`.

## 6. Teste de resistência (soak) e de consumo

O módulo `soak/` roda um cenário em laço com toque físico enquanto mede o celular via
adb, e no fim gera um relatório. Serve para achar vazamento de memória, queda de fluidez,
aquecimento, consumo de bateria, crashes e ANRs. Usa o `RobotTap` direto (sem o servidor HTTP),
então todas as travas de segurança do `taprobot` continuam valendo.

```bash
python -m soak run soak/examples/apidemos_soak.yaml --serial <IP:porta>     # soak (carregador)
python -m soak run soak/examples/apidemos_consumo.yaml --serial <IP:porta>  # consumo (bateria)
python -m soak run soak/examples/apidemos_soak.yaml --dry-run               # sem P1S e sem celular, ~2 min
python -m soak report runs/<pasta>                                          # (re)gera o relatório
python -m soak ui --serial <IP:porta>                                       # itens da tela com coordenadas
```

**Dois perfis** (`mode` no cenário):

- `soak`: celular **no carregador**. Foco em memória, fluidez, crash e ANR.
- `consumo`: celular **na bateria**, com adb **pelo Wi-Fi** (o cabo USB carregaria o
  celular). Mede %/h e mAh/h. O teste não começa se o celular estiver carregando e
  para se ele começar a carregar. Use brilho fixo para comparar execuções.

**Cenário (YAML):** passos `tap`, `swipe`, `long_press` (em pixels), `wait` (segundos ou
`[mín, máx]`) e `key` (tecla via adb, ex.: `BACK`; não é toque físico). Também: variação
aleatória `jitter_px` com `seed` fixa (execução reproduzível), `duration_min` ou
`iterations`, `min_interval_s` entre toques, `pause` ociosa a cada N iterações, limites do
guardião (`limits`) e do veredito (`verdict`). Veja os exemplos comentados em
`soak/examples/`. As coordenadas dos exemplos são estimadas: confira com `python -m soak ui`.

**O que é medido**, a cada `sampling.interval_s` (padrão 60 s), em `samples.csv`: memória
do app (PSS, heap Java e nativa), quadros e quadros travados no intervalo, CPU do processo,
bateria (nível, temperatura, carregando, contador de carga), estado térmico e temperaturas,
app vivo, app em primeiro plano, tela ligada. Em `events.jsonl`: crash, crash nativo e ANR
(do logcat), reinícios do app, avisos, abortos. Capturas de tela em `screenshots/`.

**O guardião para o teste e estaciona a ponteira** quando: o app cai mais vezes que
`app_restarts_max` (antes disso, ele é reaberto); a tela apaga; o adb fica fora mais que
`adb_offline_max_s` (enquanto isso, nenhum toque); o robô/MQTT erra `robot_errors_max`
vezes seguidas; um movimento esbarra numa trava de segurança; a bateria passa de
`battery_temp_max_c`; os toques passam de `max_touches`; a verificação de calibração falha;
ou você aperta Ctrl+C. A **verificação de calibração** toca periodicamente o ponto de
`calibration_check` e confere, pelo `getevent`, onde o celular sentiu o toque. Esse toque
chega ao app: escolha um ponto neutro (ex.: a barra de título).

**Desgaste:** cada toque gasta a borracha e o fuso Z. O total acumulado fica em
`runs/wear.json`; o teste avisa ao passar de `limits.wear_warn_touches`.

**Relatório** (`report.html`, um arquivo só, abre offline): veredito OK / ATENÇÃO / FALHA
com os motivos, gráficos no tempo (memória com a tendência em MB/h por regressão linear,
% de quadros travados, CPU, temperaturas, bateria), linha do tempo de eventos, capturas e a
tabela completa. O resumo também vai para `summary.csv`. Crash e ANR são sempre FALHA;
aborto por problema do ambiente (adb, tela, robô) é ATENÇÃO, porque não diz nada do app.

### Como escalar com segurança

Rode **10 min**, depois **1 h** e só então **uma noite inteira**
(`--duration-min 10`, `60`, `480`). Antes de cada etapa:

- [ ] `python -m soak run ... --dry-run` passou (valida o cenário sem mover nada).
- [ ] P1S homed com a mesa vazia; `python -m tools.calibrate verify` passou há pouco.
- [ ] `motion.z_floor` correto para o celular na base.
- [ ] Base presa na mesa, celular firme; nenhum cabo no caminho da ponteira.
- [ ] Tela desbloqueada e sem apagar: "Permanecer ativo" (carregador) ou tempo de tela
      maior que o teste (bateria). O teste avisa se a tela vai apagar antes do fim.
- [ ] Carregador ligado no modo soak; impressora e computador na tomada (sem suspender).
- [ ] Acompanhe as **primeiras horas** com a mão perto do botão de energia da P1S.
- [ ] Na noite inteira, confira de manhã o `wear.json` e a borracha da ponteira.

## 7. Limitações conhecidas

- O MQTT só confirma que o comando foi **aceito**, não que o movimento **terminou**. O código
  espera um tempo estimado (distância ÷ velocidade + folga `settle_s`). Se sentir toques
  atropelados, aumente `settle_s`.
- A P1S confirma cada comando ao recebê-lo, mas **descarta comandos em excesso sem avisar**
  quando muitos chegam de uma vez. O `RobotTap` espera cada gesto terminar, então não
  acumula; código novo que mande G-code direto deve fazer o mesmo.
- Só orientação retrato; rotação da tela exige recalibrar.
- A impressora fica ocupada durante os testes e o fuso Z trabalha a cada toque.
- A câmera da P1S dá para usar para evidência (stream pelo modo LAN), mas não está
  integrada aqui.

## 8. Solução de problemas

| Sintoma | O que verificar |
|---|---|
| Timeout ao conectar | IP, Modo LAN ligado, PC na mesma rede, porta 8883 liberada |
| "conexão recusada" | access code (muda ao reiniciar o Modo LAN) |
| "sem confirmação da impressora" | firmware pode ter mudado o protocolo ou exigir Modo Desenvolvedor; confira o tópico/formato `gcode_line` na documentação da comunidade para a sua versão |
| Robot: nenhum elemento encontrado | tela bloqueada ou apagada no celular; desbloqueie antes de rodar |
| Robot: celular não encontrado | Depuração por Wi-Fi desligada (ao trocar de rede ela desliga) ou computador em outra rede |
| Nenhum touchscreen encontrado | `adb devices`, autorizar depuração USB; alguns aparelhos restringem `getevent` |
| Toque não detectado na descida | ponteira fora da tela, sem aterramento, borracha pouco condutiva, `z_floor` alto |
| Erro de calibração > 0,5 mm | celular folgado no gabarito, ponteira bamba, `settle_s` baixo |

## Estrutura

```
taprobot/      biblioteca do robô (bambu.py MQTT, robot.py gestos, calibration.py,
               touch_reader.py, device.py busca do celular, appium_patch.py)
robot/         testes Appium em Robot Framework (bibliotecas, resources, testes)
soak/          teste de resistência e de consumo (cenário, coletor, guardião, relatório)
tools/         linha de comando: calibrate, test_connection, server (python -m tools.<nome>)
tests/         testes unitários da lógica (sem hardware): python -m pytest tests -q
examples/      alternativa em pytest para os testes Appium
apps/          APK de exemplo (ApiDemos)
docs/          decisões e aprendizados
results/       saída do Robot (não versionar)
runs/          execuções do soak (não versionar)
```
