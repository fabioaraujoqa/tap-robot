*** Settings ***
Documentation     Tela inicial e Views do ApiDemos (app de exemplo em apps/).
Resource          ../robo.resource


*** Variables ***
${APIDEMOS_APK}         ${CURDIR}/../../../../apps/ApiDemos-debug.apk
${MENU_VIEWS}           accessibility_id=Views
${VIEWS_BUTTONS}        accessibility_id=Buttons
${MENU_ANIMATION}       accessibility_id=Animation
${BOUNCING_BALLS}       accessibility_id=Bouncing Balls
${DRAG_AND_DROP}        accessibility_id=Drag and Drop
${PONTO_1}              id=io.appium.android.apis:id/drag_dot_1
${PONTO_2}              id=io.appium.android.apis:id/drag_dot_2


*** Keywords ***
Abrir o ApiDemos
    Iniciar sessão com robô
    ...    appium:app=${APIDEMOS_APK}
    ...    appium:appPackage=io.appium.android.apis
    ...    appium:appActivity=.ApiDemos

Tela inicial deve estar visível
    Wait Until Element Is Visible    ${MENU_VIEWS}    10s

Entrar em Views
    Clicar    ${MENU_VIEWS}

Tela Views deve estar visível
    Wait Until Element Is Visible    ${VIEWS_BUTTONS}    10s

Voltar
    Go Back

Esperar e clicar
    [Documentation]    Espera só para sincronizar com a troca de tela; não é verificação do app.
    [Arguments]    ${locator}
    Wait Until Element Is Visible    ${locator}    10s
    Clicar    ${locator}

Abrir Bouncing Balls
    Esperar e clicar    ${MENU_ANIMATION}
    Esperar e clicar    ${BOUNCING_BALLS}
    Sleep    1s

Abrir Drag and Drop
    Esperar e clicar    ${MENU_VIEWS}
    Esperar e clicar    ${DRAG_AND_DROP}
    Wait Until Element Is Visible    ${PONTO_1}    10s

Voltar ao menu inicial
    Go Back
    Wait Until Element Is Visible    ${MENU_ANIMATION}    5s
