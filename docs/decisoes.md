# Decisões e aprendizados

Registro do porquê das escolhas do projeto e do que foi aprendido no hardware real.
O "como usar" fica no [README](../README.md).

## 1. Que parte fica em qual linguagem

| Parte | Linguagem | Onde |
|---|---|---|
| Robô (MQTT, G-code, travas de segurança, calibração, leitura de toque) | Python | `taprobot/`, `calibrate.py` |
| Servidor HTTP do robô (para testes em outras linguagens) | Python | `server.py` |
| Teste de resistência e de consumo | Python (cenário em YAML) | `soak/` |
| Testes funcionais Appium | JS (WebdriverIO) | `specs/`, `wdio.conf.js`, `wdio/` |
| Integração com pytest (alternativa aos testes em JS) | Python | `examples/`, `taprobot/appium_patch.py` |

A regra combinada: **as integrações com o hardware ficam em Python**; os testes podem ser
em qualquer linguagem, falando com o robô pelo `server.py`.

## 2. Por que o soak é em Python e não em JS

O soak não é um teste do mesmo tipo dos specs: é infraestrutura que roda horas sem
ninguém olhando. Quem escreve o roteiro edita só o YAML, sem programar.

- **Segurança.** O guardião controla o robô no mesmo processo e chama `park()` em qualquer
  saída, inclusive Ctrl+C e exceções. Em JS, isso passaria pelo HTTP do `server.py`: se o
  processo JS morresse, ninguém estacionaria a ponteira.
- **Reaproveitamento.** A verificação de calibração usa o `TouchReader` (getevent), a
  conversão px → mm e as travas (`z_floor`, limites XY), que já existem em Python.
- **Análise.** As tendências de memória e consumo usam regressão linear (numpy).
- **Menos peças numa noite inteira.** Um processo só, sem Appium nem WebdriverIO, que
  tendem a derrubar sessões longas.

O que se perde: quem não conhece Python não consegue mexer no coletor, no guardião ou no
relatório. E o cenário usa coordenadas fixas, não localiza elementos pelo Appium.

## 3. Próximo passo possível: modo monitor

Se um app real tiver layout que muda (coordenadas fixas frágeis), criar
`python -m soak monitor`: só coleta, vigia e gera o relatório, enquanto o roteiro de toques
é um spec (JS ou Python) em laço usando o robô pelo `server.py` e localizando elementos
pelo Appium. Custos: o guardião precisa avisar o spec para parar (ex.: o `server.py`
passa a recusar toques depois de um aborto) e estacionar a ponteira depende do servidor.
Não foi feito: só vale a pena quando houver esse app.

## 4. Caminho para o projeto todo em Python

Os testes Appium também podem ser em Python, e aí o robô entra direto, sem HTTP.
Duas opções; as duas usam o mesmo Appium, o mesmo `taprobot` e o mesmo soak.

**pytest + Appium-Python-Client.** Já tem exemplo pronto (`examples/conftest_example.py`):
todo `element.click()` vira toque físico. É Python comum, flexível para lógica (laços,
dados de teste, esperas complexas) e fácil de depurar.

**Robot Framework + AppiumLibrary.** Testes escritos como palavras-chave legíveis por
quem não programa, e um relatório HTML (log + report) muito bom sem esforço. Para o
robô, basta uma biblioteca de palavras-chave em Python que envolva o `RobotTap`
(ex.: `Toque Físico No Elemento`, `Arraste Físico`), já que o Robot carrega classes
Python diretamente. Contras: é mais uma linguagem (a sintaxe do Robot), lógica complexa
fica desajeitada e a depuração é mais difícil.

Critério sugerido: se os testes vão ser lidos ou escritos por gente de QA sem perfil de
programação, ou se o relatório pronto pesa muito, **Robot Framework**. Se é você quem
escreve tudo e quer aprender Python de verdade, **pytest** (e, se quiser, o Robot depois,
porque as palavras-chave dele são escritas em Python mesmo). Não há pressa em migrar os
specs do WebdriverIO: eles funcionam e falam com o robô pelo `server.py`.

## 5. Aprendizados no hardware (5 e 6 de outubro de 2026)

**Rede e P1S**
- Mac, celular e impressora precisam estar na mesma rede (a da impressora).
- Modo LAN + Modo Desenvolvedor são obrigatórios; o Desenvolvedor só aparece depois de
  ligar o "Somente LAN" (a nuvem da Bambu deixa de funcionar enquanto isso).
- O número de série verdadeiro vem no certificado TLS da porta 8883 (começa com `01P`
  na P1S). O código impresso perto dele na etiqueta não é o serial.
- O broker MQTT da P1S **não devolve PUBACK**: publicar com qos 1 fazia cada comando
  esperar 3 s. Com qos 0, a confirmação real (a resposta "success") chega em ~12 ms.
- Fechar a conexão chamando `loop_stop()` antes de `disconnect()` travava para sempre.
- A P1S confirma o comando ao recebê-lo, mas **descarta o excesso sem avisar** quando
  muitos chegam de uma vez: um desenho mandado de uma vez saiu pela metade. O `RobotTap`
  espera cada gesto terminar, então não sofre disso; código que mande G-code direto deve
  acompanhar o ritmo da impressora.

**Caneta / ponteira**
- Módulo usado: "P1/X1 Pen Plotter Module" (MakerWorld), que encaixa no cabeçote e tem mola.
- **O homing (G28) é sempre sem o módulo**: no G28 a mesa sobe até encostar no bico, e a
  caneta bateria antes.
- Ajuste que funcionou com papel na mesa (sem papelão): mesa em Z=8, caneta descida até
  encostar e comprimir a mola; desenho bom com Z=7,5; caneta levantada em Z=11.
- Com o desenho legível visto de frente para a impressora, +Y aponta para o fundo.

**Celular (Moto G06, Android 15)**
- Depuração por Wi-Fi: parear uma vez (`adb pair`); a porta muda a cada vez que a depuração
  é religada ou a rede muda (`npm run connect` acha a porta nova). Ao trocar de rede, é
  preciso religar a depuração no celular e aceitar a rede.
- O app Appium Settings fecha sozinho no Android 15 sem permissão de localização
  ("Appium Settings app is not running"). Correção, uma vez por instalação:
  `adb shell pm grant io.appium.settings android.permission.ACCESS_FINE_LOCATION`
  (e também `ACCESS_COARSE_LOCATION` e `ACCESS_BACKGROUND_LOCATION`).
- A tela apaga em 60 s e o celular tem bloqueio de tela: para testes longos, desbloquear e
  ligar "Permanecer ativo" (no carregador) ou aumentar o tempo de tela (na bateria).

## 6. Pendências para o uso real

1. Trocar a caneta pela ponteira de borracha condutiva (no mesmo módulo).
2. Imprimir e testar o gabarito do celular (`cad/phone_jig.scad`).
3. Definir `motion.z_floor` no `config.yaml` (hoje vazio) e rodar `python calibrate.py run`.
4. Confirmar as coordenadas dos cenários de exemplo com `python -m soak ui`.
5. Primeiro soak real: 10 min, acompanhando de perto.
