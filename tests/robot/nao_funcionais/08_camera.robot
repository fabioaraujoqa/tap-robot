*** Settings ***
Documentation     Câmera: abre e fecha o preview várias vezes e testa a permissão negada.
...               Nenhum dos dois casos pode derrubar o app.
Resource          resources/nfr_keywords.resource
Suite Setup       Abrir sessão NFR
Suite Teardown    Fechar sessão NFR
Test Tags         emulador    aparelho_real


*** Variables ***
${TELA_CAMERA}    .graphics.CameraPreview
${PERMISSAO}      android.permission.CAMERA


*** Test Cases ***
Preview abre e fecha repetidamente
    ${crashes}=    Contar Crashes    ${PACOTE}
    ${pid}=    Obter Pid    ${PACOTE}
    FOR    ${repeticao}    IN RANGE    ${CAMERA_REPETICOES}
        Abrir Activity    ${PACOTE}    ${TELA_CAMERA}
        Sleep    2s
        Adb Shell    input keyevent BACK
        Sleep    1s
        ${pid_agora}=    Obter Pid    ${PACOTE}
        ${total}=    Contar Crashes    ${PACOTE}
        Gravar Csv    camera    caso=repeticoes    repeticao=${repeticao}    pid=${pid_agora}    crashes=${{${total} - ${crashes}}}
    END
    App deve continuar vivo    ${pid}    ${crashes}

Permissão negada não derruba o app
    [Teardown]    Devolver permissão
    Abrir Activity    ${PACOTE}    ${INICIAL}
    # o Android encerra o processo ao revogar a permissão, então o app é reaberto em seguida
    Adb Shell    pm revoke ${PACOTE} ${PERMISSAO}
    Abrir Activity    ${PACOTE}    ${INICIAL}
    Sleep    1s
    ${crashes}=    Contar Crashes    ${PACOTE}
    ${pid}=    Obter Pid    ${PACOTE}
    Abrir Activity    ${PACOTE}    ${TELA_CAMERA}
    Sleep    3s
    ${total}=    Contar Crashes    ${PACOTE}
    Gravar Csv    camera    caso=permissao_negada    repeticao=0    pid=${pid}    crashes=${{${total} - ${crashes}}}
    Should Be Equal As Integers    ${total}    ${crashes}    O app caiu ao abrir a câmera sem permissão.
    ${pid_depois}=    Obter Pid    ${PACOTE}
    Should Be Equal As Integers    ${pid_depois}    ${pid}    O processo morreu sem permissão de câmera.


*** Keywords ***
Devolver permissão
    Adb Shell    pm grant ${PACOTE} ${PERMISSAO}
