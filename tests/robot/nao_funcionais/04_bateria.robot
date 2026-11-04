*** Settings ***
Documentation     Consumo de bateria com o app em uso e a tela ligada, em %/h.
...
...               Rode FORA da tomada, pela Depuração por Wi-Fi. Se o aparelho estiver carregando,
...               o teste avisa, grava o CSV e termina como SKIP: o consumo medido não valeria.
Resource          resources/nfr_keywords.resource
Suite Setup       Preparar medição
Suite Teardown    Encerrar medição
Test Tags         aparelho_real    longo


*** Variables ***
${DURACAO_MIN}    30


*** Test Cases ***
Consumo de bateria dentro do limite
    ${inicio}=    Evaluate    time.time()
    ${ciclos}=    Evaluate    int(${DURACAO_MIN} / ${BATERIA_INTERVALO_MIN})
    ${horas}=    Create List
    ${niveis}=    Create List
    ${carregou}=    Set Variable    ${False}
    FOR    ${ciclo}    IN RANGE    ${ciclos} + 1
        ${amostra}=    Registrar amostra    bateria    ${inicio}
        Append To List    ${horas}    ${amostra}[horas]
        Append To List    ${niveis}    ${amostra}[bateria_pct]
        IF    ${amostra}[carregando]
            ${carregou}=    Set Variable    ${True}
            Log    O aparelho está carregando: tire da tomada para medir o consumo.    WARN
        END
        IF    ${ciclo} < ${ciclos}
            Esperar mantendo a sessão    ${{${BATERIA_INTERVALO_MIN} * 60}}
        END
    END
    Skip If    ${carregou}    O aparelho carregou durante o teste; o consumo não foi validado.
    ${variacao}=    Calcular Inclinacao Por Hora    ${horas}    ${niveis}
    Validar limite máximo    Consumo de bateria (%/h)    ${{-${variacao}}}    ${BATERIA_MAX_PCT_POR_HORA}


*** Keywords ***
Preparar medição
    Abrir sessão NFR    .animation.BouncingBalls
    ${tempo}=    Adb Shell    settings get system screen_off_timeout
    Set Suite Variable    ${TEMPO_DE_TELA}    ${tempo.strip()}
    Adb Shell    settings put system screen_off_timeout ${BATERIA_TELA_LIGADA_MS}

Encerrar medição
    Run Keyword And Ignore Error
    ...    Adb Shell    settings put system screen_off_timeout ${TEMPO_DE_TELA}
    Fechar sessão NFR
