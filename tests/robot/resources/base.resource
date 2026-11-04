*** Settings ***
Documentation     Sessão Appium no celular (Moto G06). O celular é encontrado sozinho,
...               no cabo USB ou na Depuração por Wi-Fi.
...
...               Variáveis que podem ser trocadas na linha de comando (-v NOME:valor):
...               UDID (serial ou IP:porta; vazio = acha o Moto G06), APPIUM_URL.
Library           AppiumLibrary
Library           ../libraries/TapRobotLibrary.py    simulado=${SIMULADO}


*** Variables ***
${APPIUM_URL}     http://127.0.0.1:4723
${UDID}           ${EMPTY}
${ROBO}           False
${SIMULADO}       False


*** Keywords ***
Iniciar sessão
    [Documentation]    Abre o app no celular. Os argumentos são as capabilities do app.
    [Arguments]    &{app}
    ${udid}=    Set Variable If    '${UDID}' == '${EMPTY}'    ${None}    ${UDID}
    IF    $udid is None
        ${udid}=    Descobrir Celular
    END
    Open Application    ${APPIUM_URL}
    ...    platformName=Android
    ...    appium:automationName=UiAutomator2
    ...    appium:udid=${udid}
    ...    appium:autoGrantPermissions=${True}
    ...    appium:newCommandTimeout=${240}
    ...    &{app}

Fechar sessão
    Run Keyword And Ignore Error    Capture Page Screenshot
    Close Application
