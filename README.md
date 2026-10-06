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
4. `python test_connection.py --latency`: conecta, envia um comando inofensivo e mede o
   tempo de resposta. Se aparecer "sem ack", o formato do comando pode ter mudado no
   seu firmware (veja *Solução de problemas*).

## 2. Mecânica

- **Gabarito do celular:** `cad/phone_jig.scad` (parametrizado com as medidas do Moto
  G06: 171,35 × 77,5 × 8,31 mm). **Não foi renderizado nem testado fisicamente**; imprima
  uma versão rápida e confira o encaixe. Só os cantos seguram o aparelho, deixando
  livres os botões laterais e a entrada USB-C. Cole/prenda a base na mesa sempre no
  mesmo lugar (marque a posição com fita).
- **Suporte da ponteira** (depende do seu cabeçote, então não vem pronto). Requisitos:
  1. A ponta da ponteira passa **abaixo do bico** (pelo menos ~5 mm), senão o bico bate
     no celular antes da ponteira.
  2. **Mola ou folga elástica** de 1–2 mm no sentido vertical.
  3. Fixação firme, sem nada aquecendo. Procure "pen holder" para P1P/P1S no MakerWorld.
  4. Se a ponteira ficar deslocada do bico, tudo bem para a calibração (ela absorve o
     deslocamento), mas a área alcançável da tela diminui. Ajuste `x_min/x_max/y_min/y_max`.
- Telas capacitivas às vezes exigem **aterramento**: se o celular não sentir o toque, ligue
  a espuma/borracha condutiva por um fio ao corpo do celular.
- A tela útil do G06 é ≈ 70 × 160 mm; a base fixa o celular com a tela a
  `3 + 8,31 = 11,31 mm` acima da mesa.

## 3. Segurança (leia antes de mover qualquer coisa)

- **Faça o homing (G28) com a mesa VAZIA.** Em alguns modelos o homing em Z encosta o
  bico/cabeçote na mesa; com o celular montado isso poderia esmagá-lo.
  `python test_connection.py --home --bed-empty` e só depois monte gabarito e celular.
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
python calibrate.py run
```

1. Você leva a ponteira, por comandos de jog (`x+ 5`, `y- 2`, `z- 10`), até ficar em cima
   da tela, perto do centro (tolerância ±8 mm em X e ±15 mm em Y).
2. O script desce a ponteira de 0,1 em 0,1 mm até o celular sentir o toque
   (lido via `adb shell getevent`) e grava o **Z de contato**.
3. Faz 2 toques de sondagem para descobrir orientação e escala e depois uma grade 3×3
   sobre a tela inteira. A cada toque, o celular diz em que pixel sentiu.
4. Ajusta uma transformação afim, salva em `calibration.json` e mostra o erro máximo
   (bom: < 0,5 mm).

Depois: `python calibrate.py verify` toca 10 pontos e mede o erro real.

Recalibre se mudar a posição do gabarito, a ponteira, ou a resolução/escala de exibição
do celular.

## 5. Usar nos testes Appium

Sem mudar os testes existentes (pytest): copie as fixtures de `examples/conftest_example.py`
para o seu `conftest.py`. Todo `element.click()` passa a ser físico.

Sem pytest, em qualquer script:

```python
from taprobot.appium_patch import physical_clicks
with physical_clicks(robot):
    driver.find_element(...).click()      # toque físico
robot.swipe_px(360, 1200, 360, 500)       # rolagem física
```

Exemplo completo: `examples/appium_example.py`.

### Testes em WebdriverIO (JS) com o robô em Python

O robô fica todo no Python, como um serviço local; os testes JS só chamam uma API HTTP.

O projeto já vem com um WebdriverIO configurado para o Moto G06 (`wdio.conf.js`, testes em
`specs/`, app de exemplo ApiDemos em `apps/`). Instalação:

```bash
npm install
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
# Só o Appium (clique por software)
appium                                  # terminal 1
npm run wdio                            # terminal 2

# Com o robô
appium                                  # terminal 1
.venv/bin/python server.py              # terminal 2  (--dry-run: sem a impressora)
npm run wdio:robot                      # terminal 3
```

- `--dry-run` sem `config.yaml`/`calibration.json` usa valores **simulados**: o servidor
  imprime o G-code de cada toque e o teste também clica por software para seguir em frente.
  Serve para validar a integração sem hardware; as coordenadas em mm não significam nada.
- Celular: o `wdio.conf.js` acha o Moto G06 sozinho, no cabo USB ou na Depuração por Wi-Fi
  (descobre o IP:porta e faz o `adb connect`; precisa ter pareado uma vez com `adb pair`).
  Só conectar: `npm run connect`. Outro aparelho: `ANDROID_UDID=<serial ou IP:porta> npm run wdio`.

- `wdio/robot-client.js`: cliente (Node 18+, usa `fetch`).
- `wdio/wdio.conf.snippet.js`: trechos para o seu `wdio.conf.js`. Com `ROBOT=1`, todo
  `element.click()` vira toque físico; sem a variável, os testes rodam como antes.
  Também cria `browser.robotSwipe(...)` e `browser.robotLongPress(...)`.
- Rotas: `GET /health`, `POST /tap`, `/long_press`, `/swipe`, `/park`, sempre em pixels.
  Cada chamada só responde quando o movimento estimado termina, então o `await` espera o toque.
- O servidor escuta só em `127.0.0.1` e **não tem autenticação**. Não exponha na rede.
- Outros comandos do WebdriverIO que fazem toque por dentro (ex.: `element.tap()`,
  `touchAction`) não são interceptados; use `robot.tap(...)` ou sobrescreva-os do mesmo jeito.
- Testado: o WebdriverIO no Moto G06 com e sem `ROBOT=1` (servidor em dry-run simulado).
  Não foi testado com a P1S.

Observações:
- O Appium segue fazendo `send_keys`, screenshots e esperas por software. Só o toque é físico.
- Toques fora da tela (elemento parcialmente visível com centro fora) geram erro claro.
- Cada toque leva ~1–2 s (descer devagar protege a tela). Depois que tudo estiver estável,
  aumente `feed_z_touch`/`feed_xy` no config e reduza `tap_dwell_ms` para acelerar.

## 6. Teste de resistência (soak) e de consumo

O módulo `soak/` roda um cenário em laço com toque físico enquanto mede o celular via
adb, e no fim gera um relatório. Serve para achar vazamento de memória, queda de fluidez,
aquecimento, consumo de bateria, crashes e ANRs. Usa o `RobotTap` direto (sem `server.py`),
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
- [ ] P1S homed com a mesa vazia; `python calibrate.py verify` passou há pouco.
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
| Nenhum touchscreen encontrado | `adb devices`, autorizar depuração USB; alguns aparelhos restringem `getevent` |
| Toque não detectado na descida | ponteira fora da tela, sem aterramento, borracha pouco condutiva, `z_floor` alto |
| Erro de calibração > 0,5 mm | celular folgado no gabarito, ponteira bamba, `settle_s` baixo |

## Estrutura

```
taprobot/          biblioteca (bambu.py MQTT, robot.py gestos, calibration.py, touch_reader.py, appium_patch.py)
calibrate.py       calibração, verificação e jog manual
test_connection.py conexão e latência
server.py          servidor HTTP local do robô (para testes em JS/WebdriverIO)
wdio/              cliente JS e trechos de wdio.conf.js
wdio.conf.js       configuração do WebdriverIO (Moto G06)
specs/             testes WebdriverIO
apps/              APK de exemplo (ApiDemos)
examples/          integração com Appium/pytest (Python)
soak/              teste de resistência e de consumo (cenário, coletor, guardião, relatório)
runs/              execuções do soak (não versionar)
docs/              decisões e aprendizados
cad/               gabarito do celular (OpenSCAD)
tests/             testes da lógica (sem hardware)
```
