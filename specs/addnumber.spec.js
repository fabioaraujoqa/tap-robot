// BrowserStack AddNumber: soma dois números.
// Com ROBOT=1, o toque no botão ADD é físico; a digitação continua por software (Appium).

const num1 = () => $('id=com.browserstack.addnumber:id/num1');
const num2 = () => $('id=com.browserstack.addnumber:id/num2');
const addBtn = () => $('id=com.browserstack.addnumber:id/addBtn');
const result = () => $('id=com.browserstack.addnumber:id/sampleLabel');

async function add(a, b) {
  await num1().setValue(a);
  await num2().setValue(b);
  if (await driver.isKeyboardShown()) await driver.hideKeyboard();
  await addBtn().click();
}

describe('AddNumber', () => {
  it('abre com os campos vazios', async () => {
    await expect(addBtn()).toBeDisplayed();
    await expect(result()).toHaveText('Hello World!');
  });

  it('soma 7 + 5', async () => {
    await add('7', '5');
    await expect(result()).toHaveText('Answer: 12');
  });

  it('soma números negativos', async () => {
    await add('-3', '10');
    await expect(result()).toHaveText('Answer: 7');
  });
});
