"""Teste de resistência (soak) e de consumo com toque físico.

O robô (taprobot.RobotTap) executa um cenário em laço enquanto o computador mede o
celular via adb. No fim, um relatório HTML resume memória, fluidez, CPU, bateria,
temperatura, crashes e ANRs.

  python -m soak run cenario.yaml
  python -m soak report runs/<pasta>
"""
