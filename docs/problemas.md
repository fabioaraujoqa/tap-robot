# Limitações e solução de problemas

## Limitações conhecidas

- O MQTT só confirma que o comando foi **aceito**, não que o movimento **terminou**. O código
  espera um tempo estimado (distância ÷ velocidade + folga `settle_s`). Se sentir toques
  atropelados, aumente `settle_s`.
- A P1S confirma cada comando ao recebê-lo, mas **descarta comandos em excesso sem avisar**
  quando muitos chegam de uma vez. O `RobotTap` espera cada gesto terminar, então não
  acumula; código novo que mande G-code direto deve fazer o mesmo.
- Só orientação retrato; rotação da tela exige recalibrar.
- A impressora fica ocupada durante os testes e o fuso Z trabalha a cada toque.
- A câmera da P1S dá para usar para evidência (stream pelo modo LAN), mas não está
  integrada aqui (ver as ideias em [decisoes.md](decisoes.md)).

## Solução de problemas

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
