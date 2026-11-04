*** Settings ***
Documentation     Fluidez: zera o gfxinfo, rola uma lista e valida o % de quadros com jank.
Resource          resources/nfr_keywords.resource
Suite Setup       Abrir sessão NFR    .view.List1
Suite Teardown    Fechar sessão NFR
Test Tags         emulador    aparelho_real


*** Test Cases ***
Rolagem de lista dentro do limite de jank
    Sleep    1s
    Zerar Gfxinfo    ${PACOTE}
    FOR    ${rolagem}    IN RANGE    ${JANK_ROLAGENS}
        ${direcao}=    Evaluate    1 if ${rolagem} % 10 < 5 else -1
        Rolar a tela    ${direcao}
    END
    ${jank}=    Obter Jank    ${PACOTE}
    Gravar Csv    fluidez    &{jank}
    IF    ${jank}[frames] < ${JANK_MIN_QUADROS}
        Fail    Só ${jank}[frames] quadros desenhados: poucos para medir o jank.
    END
    Validar limite máximo    Jank (%)    ${jank}[janky_pct]    ${JANK_MAX_PCT}
