*** Settings ***
Documentation     Latência do toque físico até a mudança na tela, com p50 e p95. Só faz sentido
...               com o braço de verdade: toque por software não gera evento no `getevent`.
...
...               Mede do BTN_TOUCH DOWN no `getevent -lt` até o primeiro quadro novo no
...               `gfxinfo framestats`, ambos no relógio do aparelho. AINDA NÃO VALIDADO com a P1S.
Resource          resources/nfr_keywords.resource
Suite Setup       Preparar medição
Suite Teardown    Encerrar medição
Test Tags         braco


*** Test Cases ***
Latência do toque físico dentro do limite
    ${latencias}=    Create List
    ${ultimo_toque}=    Set Variable    ${None}
    FOR    ${repeticao}    IN RANGE    ${LATENCIA_REPETICOES}
        Wait Until Element Is Visible    ${MENU_VIEWS}    10s
        Sleep    1s
        Clicar    ${MENU_VIEWS}
        Sleep    1s
        ${medida}=    Medir Latencia Toque    ${PACOTE}    ${ultimo_toque}
        ${ultimo_toque}=    Set Variable    ${medida}[toque_s]
        Append To List    ${latencias}    ${medida}[latencia_ms]
        Gravar Csv    latencia    repeticao=${repeticao}    &{medida}
        Go Back
    END
    ${p50}=    Calcular Percentil    ${latencias}    50
    ${p95}=    Calcular Percentil    ${latencias}    95
    Validar limite máximo    Latência p50 (ms)    ${p50}    ${LATENCIA_P50_MAX_MS}
    Validar limite máximo    Latência p95 (ms)    ${p95}    ${LATENCIA_P95_MAX_MS}


*** Keywords ***
Preparar medição
    IF    not ${ROBO} or ${SIMULADO}
        Skip    Precisa do braço real: rode com -v ROBO:True, sem SIMULADO.
    END
    Abrir sessão NFR
    ${touchscreen}=    Obter Touchscreen
    Iniciar Getevent    ${touchscreen}

Encerrar medição
    IF    ${ROBO} and not ${SIMULADO}
        Run Keyword And Ignore Error    Parar Getevent
        Fechar sessão NFR
    END
