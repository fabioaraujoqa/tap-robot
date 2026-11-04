*** Settings ***
Documentation     Sensores simulados (`mobile: sensorSet` só existe em emulador) e rotação
...               durante o preenchimento de um campo.
Resource          resources/nfr_keywords.resource
Suite Setup       Abrir o ApiDemos
Suite Teardown    Fechar sessão NFR
Test Tags         emulador


*** Variables ***
${CAMPO_SALVO}    id=io.appium.android.apis:id/saved
${TEXTO}          texto preservado


*** Test Cases ***
Tela de sensores aguenta mudanças de leitura
    # .os.Sensors não serve: cai ao abrir, porque pede amostragem máxima sem a permissão exigida
    Abrir Activity    ${PACOTE}    .graphics.Compass
    Sleep    1s
    ${pid}=    Obter Pid    ${PACOTE}
    ${crashes}=    Contar Crashes    ${PACOTE}
    FOR    ${sensor}    ${valor}    IN
    ...    light    50
    ...    proximity    1
    ...    temperature    25
    ...    pressure    1000
    ...    humidity    60
    ...    acceleration    0:9.8:0
    ...    acceleration    9.8:0:0
        Set Sensor    ${sensor}    ${valor}
        Sleep    500ms
    END
    App deve continuar vivo    ${pid}    ${crashes}

Texto sobrevive à rotação durante o preenchimento
    [Teardown]    Portrait
    Abrir Activity    ${PACOTE}    .app.SaveRestoreState
    Wait Until Element Is Visible    ${CAMPO_SALVO}    10s
    Clear Text    ${CAMPO_SALVO}
    Input Text    ${CAMPO_SALVO}    ${TEXTO}
    Landscape
    Sleep    1s
    Element Text Should Be    ${CAMPO_SALVO}    ${TEXTO}
    Portrait
    Sleep    1s
    Element Text Should Be    ${CAMPO_SALVO}    ${TEXTO}
