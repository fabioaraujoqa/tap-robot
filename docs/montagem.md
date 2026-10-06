# Montagem, segurança e calibração

Ordem para o primeiro uso: preparar a P1S, montar a mecânica, ler a segurança e calibrar.

## 1. Preparar a P1S

1. Na tela da impressora: ative **Modo LAN** e **Modo Desenvolvedor** (os nomes mudam
   com o firmware). Anote **IP**, **número de série** e **access code**.
2. Copie `config.example.yaml` para `config.yaml` e preencha. Não versione esse arquivo.
3. `pip install -r requirements.txt`
4. `python -m tools.test_connection --latency`: conecta, envia um comando inofensivo e mede o
   tempo de resposta. Se aparecer "sem ack", o formato do comando pode ter mudado no
   seu firmware (veja [problemas.md](problemas.md)).

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
     MakerWorld, que encaixa no cabeçote e tem mola (ver [decisoes.md](decisoes.md)).
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
