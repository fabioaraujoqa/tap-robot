// Primeiro teste: navega no ApiDemos só com cliques.
// Com ROBOT=1, cada click() abaixo é um toque físico da ponteira.

describe('ApiDemos', () => {
  it('abre a tela inicial', async () => {
    await expect($('~Views')).toBeDisplayed();
  });

  it('entra em Views', async () => {
    await $('~Views').click();
    await expect($('~Buttons')).toBeDisplayed(); // só existe dentro de Views
  });

  it('volta para a tela inicial', async () => {
    await driver.back();
    await expect($('~Views')).toBeDisplayed();
  });
});
