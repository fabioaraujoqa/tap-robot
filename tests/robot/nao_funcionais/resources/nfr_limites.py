"""Limites e parâmetros da suíte não funcional (arquivo de variáveis do Robot).

Os valores são PROVISÓRIOS: ajuste depois de uma rodada de referência no aparelho. Qualquer
um pode ser trocado na linha de comando: -v SOAK_MB_POR_HORA_MAX:15
"""

# 01 Inicialização (TotalTime do `am start -W`, em ms)
INICIO_REPETICOES = 10
INICIO_FRIO_P50_MAX_MS = 2000
INICIO_FRIO_P90_MAX_MS = 3000
INICIO_MORNO_P50_MAX_MS = 1000
INICIO_MORNO_P90_MAX_MS = 1500

# 02 Fluidez
JANK_ROLAGENS = 20
JANK_MAX_PCT = 25
JANK_MIN_QUADROS = 30  # abaixo disso a medida não vale: quase nada foi desenhado

# 03 Soak
SOAK_PAUSA_CICLO_S = 10
SOAK_CICLOS_AQUECIMENTO = 3  # o começo só enche caches; fica de fora da regressão
SOAK_MB_POR_HORA_MAX = 20
SOAK_MIN_MINUTOS_REGRESSAO = 15  # abaixo disso, a inclinação só extrapola ruído
SOAK_PSS_MAX_MB = 300
SOAK_THREADS_MAX = 200
SOAK_TEMP_MAX_C = 45
SOAK_CRASHES_MAX = 0

# 04 Bateria
BATERIA_INTERVALO_MIN = 5
BATERIA_MAX_PCT_POR_HORA = 25
BATERIA_TELA_LIGADA_MS = 1800000

# 08 Câmera
CAMERA_REPETICOES = 10

# 10 Latência do toque
LATENCIA_REPETICOES = 20
LATENCIA_P50_MAX_MS = 150
LATENCIA_P95_MAX_MS = 300
