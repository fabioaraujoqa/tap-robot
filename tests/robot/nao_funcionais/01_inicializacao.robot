*** Settings ***
Documentation     Tempo de inicialização: TotalTime do `am start -W`, com p50 e p90.
...               O estado real (COLD, WARM ou HOT) vem do Android e fica no CSV; só amostras
...               do estado esperado entram no cálculo.
Resource          resources/nfr_keywords.resource
Suite Setup       Abrir sessão NFR
Suite Teardown    Fechar sessão NFR
Test Tags         emulador    aparelho_real


*** Test Cases ***
Início frio
    Validar início    frio    COLD    ${INICIO_FRIO_P50_MAX_MS}    ${INICIO_FRIO_P90_MAX_MS}

Início morno
    Validar início    morno    WARM    ${INICIO_MORNO_P50_MAX_MS}    ${INICIO_MORNO_P90_MAX_MS}


*** Keywords ***
Validar início
    [Arguments]    ${modo}    ${estado_esperado}    ${limite_p50}    ${limite_p90}
    ${tempos}=    Create List
    FOR    ${repeticao}    IN RANGE    ${INICIO_REPETICOES}
        ${medida}=    Medir Inicio    ${PACOTE}    ${INICIAL}    ${modo}
        Gravar Csv    inicializacao    modo=${modo}    repeticao=${repeticao}    &{medida}
        IF    '${medida}[estado]' == '${estado_esperado}'
            Append To List    ${tempos}    ${medida}[total_ms]
        ELSE
            Log    Início ${modo} saiu como ${medida}[estado]: fora do cálculo.    WARN
        END
        Sleep    1s
    END
    Should Not Be Empty    ${tempos}    Nenhum início saiu como ${estado_esperado}.
    ${p50}=    Calcular Percentil    ${tempos}    50
    ${p90}=    Calcular Percentil    ${tempos}    90
    Validar limite máximo    Início ${modo} p50 (ms)    ${p50}    ${limite_p50}
    Validar limite máximo    Início ${modo} p90 (ms)    ${p90}    ${limite_p90}
