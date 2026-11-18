import qz from 'qz-tray';
import axios from 'axios';
import { KEYUTIL, KJUR, stob64, hextorstr } from 'jsrsasign';

interface PrintingOptions {
  signKey?: string;
  sign?: (payload: string) => Promise<string>;
  certificate?: () => Promise<string>;
}
let injectedSignKey: string | null = null;
let callbacks: PrintingOptions = {};


export function initPrinting(opts: PrintingOptions) {
  callbacks = opts;
  injectedSignKey = opts.signKey || null;
}

function ensureSignKey(): string {
  if (!injectedSignKey) {
    throw new Error(
      'QZ printing has not been initialized. Call initPrinting({ signKey: ... }) before using printWithQz.'
    );
  }
  return injectedSignKey;
}

export async function loadQzPrinter(host: string): Promise<void> {
  qz.security.setCertificatePromise((resolve: (data: string) => void, reject: (err?: string) => void) => {
    if (callbacks.certificate) {
      callbacks.certificate().then(resolve, (err) => reject(String(err)));
      return;
    }
    axios.get('/assets/ury/files/cert.pem')
      .then(({ data }) => resolve(data))
      .catch((err) => reject('Error fetching certificate: ' + String(err)));
  });
  if (!qz.websocket.isActive()) {
    await qz.websocket.connect({ host, usingSecure: true });
  }
}

export function disconnectQzPrinter(): void {
  if (qz.websocket.isActive()) qz.websocket.disconnect();
}

export async function printWithQz(host: string, htmlToPrint: string, printerName?: string): Promise<void> {
  const signKey = callbacks.sign ? null : ensureSignKey();

  qz.security.setSignatureAlgorithm('SHA512');
  qz.security.setSignaturePromise((toSign: string) => (resolve: (sig: string) => void, reject: (err?: string) => void) => {
    if (callbacks.sign) {
      callbacks.sign(toSign).then(resolve, (err) => reject(String(err)));
      return;
    }
    try {
      const pk = KEYUTIL.getKey(signKey as string);
      const sig = new KJUR.crypto.Signature({ alg: 'SHA512withRSA' });
      sig.init(pk);
      sig.updateString(toSign);
      const hex = sig.sign();
      resolve(stob64(hextorstr(hex)));
    } catch (err) {
      reject(String(err));
    }
  });

  const printing = async () => {
    const printer = printerName
      ? await qz.printers.find(printerName)
      : await qz.printers.getDefault();
    if (printerName && printer !== printerName) {
      throw new Error('The exact configured QZ printer was not found.');
    }
    const data = [{ type: 'pixel', format: 'html', flavor: 'plain', data: htmlToPrint }];
    if (typeof printer !== 'string' || !printer.trim()) {
      throw new Error('QZ did not resolve a single printer name.');
    }
    const config = qz.configs.create(printer);
    await qz.print(config, data as any);
  };

  if (qz.websocket.isActive()) {
    await printing();
  } else {
    await loadQzPrinter(host);
    await printing();
  }
}
