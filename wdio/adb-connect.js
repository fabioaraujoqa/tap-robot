// Acha o celular pelo serial, no cabo USB ou na Depuração por Wi-Fi, e devolve o UDID
// que o Appium deve usar (serial no USB, IP:porta no Wi-Fi).
//
// Pelo Wi-Fi a porta muda a cada vez que a depuração é religada; aqui ela é descoberta
// via mDNS (`adb mdns services`) e conectada com `adb connect`. O celular precisa já
// ter sido pareado uma vez com este computador (`adb pair`).
//
//   npm run connect              # conecta e mostra o UDID
//   node wdio/adb-connect.js <serial>

const { execFileSync } = require('child_process');

const DEFAULT_SERIAL = 'ZF525PMHVF'; // moto g06

function adb(...args) {
  return execFileSync('adb', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
}

function sleepMs(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

// Linhas "UDID  estado ..." do `adb devices`.
function listDevices() {
  return adb('devices')
    .split('\n')
    .slice(1)
    .map((line) => line.trim().split(/\s+/))
    .filter(([udid, state]) => udid && state)
    .map(([udid, state]) => ({ udid, state }));
}

// Endereço IP:porta anunciado pelo celular, ex.: "adb-ZF525PMHVF-iQtco6 _adb-tls-connect._tcp 192.168.15.20:41983".
function findWifiAddress(serial) {
  for (const line of adb('mdns', 'services').split('\n')) {
    const [name, type, address] = line.trim().split(/\s+/);
    if (type === '_adb-tls-connect._tcp' && name.startsWith(`adb-${serial}-`)) return address;
  }
  return null;
}

function resolveUdid(serial = DEFAULT_SERIAL, { attempts = 5 } = {}) {
  const devices = listDevices();
  if (devices.some((d) => d.udid === serial && d.state === 'device')) return serial; // cabo USB

  // Já conectado pelo Wi-Fi (o mDNS nem sempre responde, mas a conexão segue viva).
  for (const d of devices) {
    if (!d.udid.includes(':') || d.state !== 'device') continue;
    try {
      if (adb('-s', d.udid, 'shell', 'getprop', 'ro.serialno').trim() === serial) return d.udid;
    } catch {
      // aparelho sumiu entre o `adb devices` e esta consulta
    }
  }

  // O mDNS às vezes demora alguns segundos para enxergar o celular.
  let address = null;
  for (let i = 0; i < attempts && !address; i++) {
    if (i > 0) sleepMs(2000);
    address = findWifiAddress(serial);
  }
  if (!address) {
    throw new Error(
      `celular ${serial} não encontrado no USB nem no Wi-Fi. ` +
        'Ligue a Depuração por Wi-Fi e confira se o Mac está na mesma rede.',
    );
  }

  // Conexões antigas desse celular (porta/rede anterior) ficam "offline"; limpa para não confundir.
  for (const d of devices) {
    if (d.udid !== address && d.state === 'offline' && d.udid.includes(':')) adb('disconnect', d.udid);
  }

  const out = adb('connect', address);
  if (!/connected to/.test(out)) throw new Error(`adb connect ${address} falhou: ${out.trim()}`);
  return address;
}

module.exports = { resolveUdid };

if (require.main === module) {
  try {
    console.log(resolveUdid(process.argv[2] || DEFAULT_SERIAL));
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}
