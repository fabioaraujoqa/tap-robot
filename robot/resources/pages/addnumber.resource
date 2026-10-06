*** Settings ***
Documentation     BrowserStack AddNumber: soma dois números.
...
...               O APK mira o SDK 23 e o Android 15 recusa instalar pelo Appium. Instale uma vez à mão:
...               adb install -r --bypass-low-target-sdk-block apps/app-debug.apk
Resource          ../robo.resource


*** Variables ***
${CAMPO_NUM1}       id=com.browserstack.addnumber:id/num1
${CAMPO_NUM2}       id=com.browserstack.addnumber:id/num2
${BOTAO_ADD}        id=com.browserstack.addnumber:id/addBtn
${RESULTADO}        id=com.browserstack.addnumber:id/sampleLabel


*** Keywords ***
Abrir o AddNumber
    Iniciar sessão com robô
    ...    appium:appPackage=com.browserstack.addnumber
    ...    appium:appActivity=.MainActivity

Somar
    [Documentation]    A digitação é por software (Appium); só o toque no ADD é físico.
    [Arguments]    ${a}    ${b}
    Clear Text    ${CAMPO_NUM1}
    Input Text    ${CAMPO_NUM1}    ${a}
    Clear Text    ${CAMPO_NUM2}
    Input Text    ${CAMPO_NUM2}    ${b}
    Run Keyword And Ignore Error    Hide Keyboard
    Clicar    ${BOTAO_ADD}

Resultado deve ser
    [Arguments]    ${texto}
    Wait Until Element Is Visible    ${RESULTADO}    10s
    Element Text Should Be    ${RESULTADO}    ${texto}
