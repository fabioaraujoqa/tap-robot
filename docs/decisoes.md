# Decisões e aprendizados

Registro do porquê das escolhas do projeto e do que foi aprendido no hardware real.
O "como usar" fica no [README](../README.md).

## 1. Tudo em Python, testes em Robot Framework

Em 6 de outubro de 2026 os testes em JS (WebdriverIO) foram trocados por **Robot Framework
+ AppiumLibrary**, e o projeto ficou todo em Python. O estado anterior, com o JS, está no
primeiro commit do repositório.

| Parte | Onde |
|---|---|
| Robô (MQTT, G-code, travas de segurança, calibração, leitura de toque, busca do celular) | `taprobot/` |
| Testes Appium (palavras-chave) | `robot/` |
| Teste de resistência e de consumo (cenário em YAML) | `soak/` |
| Linha de comando (calibração, teste de conexão, servidor HTTP) | `tools/` |
| Testes unitários (pytest, sem hardware) | `tests/` |

**Por quê.** Uma linguagem só: o robô entra nos testes no mesmo processo, sem o servidor
HTTP no meio, e qualquer parte do projeto pode ser mantida pela mesma pessoa. O Robot
Framework foi escolhido (e não pytest puro) porque palavras-chave legíveis e o relatório
pronto (log.html/report.html) valem muito para testes de QA, e já era familiar.

**Formato dos testes.** Parecido com um projeto Robot simples (um resource de sessão +
testes), com duas camadas a mais por causa do robô:

- `robo.resource` tem o `Clicar`: toque físico com `ROBO=True`, clique por software sem.
  O mesmo teste roda nos dois modos, e o modo simulado valida tudo sem a P1S.
- `pages/*.resource` guarda seletores e ações de cada tela (page object leve), para os
  `.robot` ficarem só com passos legíveis.

**O que ficou de fora do Robot, de propósito.** O soak roda em Python puro (não como
teste Robot): ele roda horas sem ninguém olhando, e o guardião precisa controlar o robô
diretamente para estacionar a ponteira em qualquer falha. Quem escreve o roteiro edita só o
YAML. O servidor HTTP continua em `tools/` para quem quiser usar o robô de outra linguagem,
e `examples/` mostra a alternativa em pytest.

## 2. Próximo passo possível: soak com fluxo em Robot

O cenário do soak usa coordenadas fixas. Se um app real tiver layout que muda, uma opção é
um modo `python -m soak monitor`, que só coleta, vigia e gera o relatório, enquanto uma
suíte Robot roda em laço localizando elementos pelo Appium. O guardião precisaria avisar a
suíte para parar (ex.: a `TapRobotLibrary` passa a recusar toques depois de um aborto).
Só vale a pena quando houver esse app.

### Ideias vindas do BambuScribe

O [BambuScribe](https://github.com/Animesh-Varma/BambuScribe) (projeto GPLv3 que transforma impressoras Bambu em
plotter) serviu de referência. Por ser GPLv3, nada do código dele foi copiado; se alguma
ideia for implementada, deve ser reescrita aqui.

- **Câmera da P1S como evidência.** A câmera é lida pela rede local: conexão TLS na porta
  6000 (certificado autoassinado), um pacote de autenticação com o usuário `bblp` e o
  access code, e depois um fluxo de JPEGs (cada quadro entre os marcadores `FF D8` e
  `FF D9`). No soak, daria para guardar fotos do robô e do celular junto com as capturas de
  tela, e anexar uma foto ao relatório quando houver aborto.
- **Reenvio quando o comando some.** Eles também viram a impressora descartar comandos com
  a fila cheia e resolvem esperando a resposta com o mesmo `sequence_id` por até 8 s e
  reenviando se ela não vier. O `RobotTap` não precisa disso hoje (espera cada gesto
  terminar), mas é o caminho se algum dia for preciso mandar G-code em sequência rápida.

## 3. Aprendizados no hardware (5 e 6 de outubro de 2026)

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
  é religada ou a rede muda (`python -m taprobot.device` acha a porta nova; os testes Robot fazem isso sozinhos). Ao trocar de rede, é
  preciso religar a depuração no celular e aceitar a rede.
- O app Appium Settings fecha sozinho no Android 15 sem permissão de localização
  ("Appium Settings app is not running"). Correção, uma vez por instalação:
  `adb shell pm grant io.appium.settings android.permission.ACCESS_FINE_LOCATION`
  (e também `ACCESS_COARSE_LOCATION` e `ACCESS_BACKGROUND_LOCATION`).
- A tela apaga em 60 s e o celular tem bloqueio de tela: para testes longos, desbloquear e
  ligar "Permanecer ativo" (no carregador) ou aumentar o tempo de tela (na bateria).

## 4. Pendências para o uso real

1. Trocar a caneta pela ponteira de borracha condutiva (no mesmo módulo).
2. Adicionar ao projeto o gabarito do celular que for usado, e testar o encaixe.
3. Definir `motion.z_floor` no `config.yaml` (hoje vazio) e rodar `python -m tools.calibrate run`.
4. Confirmar as coordenadas dos cenários de exemplo com `python -m soak ui`.
5. Rodar `robot -d results robot/tests` com o celular desbloqueado (a migração para o Robot
   só foi testada até abrir a sessão: o celular estava bloqueado).
6. Primeiro soak real: 10 min, acompanhando de perto.
