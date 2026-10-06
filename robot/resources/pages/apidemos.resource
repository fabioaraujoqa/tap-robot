*** Settings ***
Documentation     Tela inicial e Views do ApiDemos (app de exemplo em apps/).
Resource          ../robo.resource


*** Variables ***
${APIDEMOS_APK}         ${CURDIR}/../../../apps/ApiDemos-debug.apk
${MENU_VIEWS}           accessibility_id=Views
${VIEWS_BUTTONS}        accessibility_id=Buttons


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
