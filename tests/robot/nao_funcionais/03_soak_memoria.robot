*** Settings ***
Documentation     Soak: navega em laço e acompanha memória, CPU, threads e temperatura.
...               Valida o crescimento da memória (MB/h) por regressão linear. Em crash, registra
...               o evento, reabre o app e segue; a falha sai no final, com o total de crashes.
...
...               Padrão de 30 min. Para 24 h: --variable DURACAO_MIN:1440
Resource          resources/nfr_keywords.resource
Suite Setup       Abrir sessão NFR
Suite Teardown    Fechar sessão NFR
Test Tags         emulador    aparelho_real    longo


*** Variables ***
${DURACAO_MIN}    30
@{TELAS}          .view.List1    .animation.BouncingBalls    .view.DragAndDropDemo


*** Test Cases ***
Memória estável durante a navegação
    ${inicio}=    Evaluate    time.time()
    ${fim}=    Evaluate    ${inicio} + ${DURACAO_MIN} * 60
    ${crashes_base}=    Contar Crashes    ${PACOTE}
    ${pid_atual}=    Obter Pid    ${PACOTE}
    ${amostras}=    Create List
    ${crashes}=    Set Variable    ${0}
    WHILE    time.time() < ${fim}    limit=NONE
        Run Keyword And Ignore Error    Navegar pelas telas
        ${pid}=    Obter Pid    ${PACOTE}
        ${caiu}=    Evaluate    $pid != $pid_atual
        ${evento}=    Set Variable If    ${caiu}    crash    ${EMPTY}
        ${amostra}=    Registrar amostra    soak    ${inicio}    ${evento}
        IF    ${caiu}
            ${crashes}=    Evaluate    ${crashes} + 1
            Log    App caiu ou reiniciou (PID ${pid_atual} -> ${pid}). Reabrindo.    WARN
            Abrir Activity    ${PACOTE}    ${INICIAL}
            ${pid_atual}=    Obter Pid    ${PACOTE}
        ELSE
            Append To List    ${amostras}    ${amostra}
            Validar picos    ${amostra}
        END
        Esperar mantendo a sessão    ${SOAK_PAUSA_CICLO_S}
    END
    ${no_logcat}=    Contar Crashes    ${PACOTE}
    Log    Crashes no logcat durante o soak: ${{${no_logcat} - ${crashes_base}}}    console=True
    ${memoria}=    Calcular Inclinacao Memoria    ${amostras}    ${SOAK_CICLOS_AQUECIMENTO}
    Log    Memória: ${memoria}    console=True
    IF    ${memoria}[horas] * 60 < ${SOAK_MIN_MINUTOS_REGRESSAO}
        Log    Trecho curto demais para concluir sobre vazamento: inclinação não validada.    WARN
    ELSE
        Validar limite máximo    Crescimento da memória (MB/h)    ${memoria}[mb_por_hora]    ${SOAK_MB_POR_HORA_MAX}
    END
    Validar limite máximo    Crashes    ${crashes}    ${SOAK_CRASHES_MAX}


*** Keywords ***
Navegar pelas telas
    FOR    ${tela}    IN    @{TELAS}
        Abrir Activity    ${PACOTE}    ${tela}
        Rolar a tela
        Sleep    1s
        # sem voltar, as telas se empilham e a memória cresce por causa do próprio teste
        Adb Shell    input keyevent BACK
        Sleep    1s
    END

Validar picos
    [Arguments]    ${amostra}
    IF    $amostra['pss_mb'] is not None
        Validar limite máximo    PSS (MB)    ${amostra}[pss_mb]    ${SOAK_PSS_MAX_MB}
    END
    IF    $amostra['threads'] is not None
        Validar limite máximo    Threads    ${amostra}[threads]    ${SOAK_THREADS_MAX}
    END
    IF    $amostra['temperatura_c'] is not None
        Validar limite máximo    Temperatura (°C)    ${amostra}[temperatura_c]    ${SOAK_TEMP_MAX_C}
    END
