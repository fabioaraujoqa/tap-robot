# Teste de resistência (soak) e de consumo

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

## Como escalar com segurança

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
