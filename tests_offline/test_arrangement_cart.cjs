/* Exercises the actual store with a small Zustand/localStorage double.
 * No browser test is claimed. Uses built-in TS stripping where available,
 * otherwise the project's existing TypeScript dev dependency.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const nodeModule = require('node:module');
const root = path.resolve(__dirname, '..');

function js(relativePath) {
  const source = fs.readFileSync(path.join(root, relativePath), 'utf8')
    .replace(/^import [^\n]*;\r?\n/gm, '')
    .replace(/^export /gm, '');
  if (typeof nodeModule.stripTypeScriptTypes === 'function') {
    return nodeModule.stripTypeScriptTypes(source);
  }
  const ts = require('typescript');
  return ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
}

let state;
let tableOrder;
let sequence = 0;
const context = {
  console,
  storage: { getItem: () => null },
  localStorage: { getItem: () => null, setItem: () => {} },
  DEFAULT_ORDER_TYPE: 'Take Away',
  uuidv4: () => `tab-${++sequence}`,
  getTableOrder: async () => ({ message: tableOrder }),
  create: factory => {
    const set = values => { state = { ...state, ...values }; };
    state = factory(set, () => state);
    return { getState: () => state, subscribe: () => {} };
  },
};
vm.runInNewContext(
  js('pos/src/lib/cart-line-identity.ts') + '\n' + js('pos/src/store/pos-store.ts') +
  '\n;globalThis.testExports = { getCartLineId, generateCartHash };', context);
const { getCartLineId, generateCartHash } = context.testExports;

(async () => {
  const coffee = { id: 'COFFEE', quantity: 1, price: 12 };
  assert.equal(getCartLineId(coffee), 'COFFEE-default-no-addons-');
  await state.addToOrder(coffee);
  await state.addToOrder(coffee);
  assert.equal(state.activeOrders.length, 1);
  assert.equal(state.activeOrders[0].quantity, 2);
  state.activeOrders = [];

  const first = { id: 'BOUQUET', quantity: 1, price: 100, custom_flora_arrangement: 'ARR-1' };
  const second = { ...first, price: 120, custom_flora_arrangement: 'ARR-2' };
  await state.addToOrder(first);
  await state.addToOrder(second);
  assert.equal(state.activeOrders.length, 2);
  assert.notEqual(state.activeOrders[0].uniqueId, state.activeOrders[1].uniqueId);
  await state.addToOrder({ ...first, comment: 'Gift card' });
  assert.equal(state.activeOrders.length, 2);
  assert.equal(state.activeOrders[0].quantity, 1);
  assert.notEqual(generateCartHash({ activeOrders: [first] }), generateCartHash({ activeOrders: [second] }));
  assert.equal(generateCartHash({ activeOrders: [first, second] }),
               generateCartHash({ activeOrders: [second, first] }));

  tableOrder = { name: 'POS-1', items: [
    { item_code: 'BOUQUET', item_name: 'Bouquet', qty: 1, rate: 100, custom_flora_arrangement: 'ARR-1' },
    { item_code: 'BOUQUET', item_name: 'Bouquet', qty: 1, rate: 120, custom_flora_arrangement: 'ARR-2' },
  ] };
  await state.loadTableOrder('TABLE-1');
  assert.notEqual(state.activeOrders[0].uniqueId, state.activeOrders[1].uniqueId);
  await state.addToOrder(first);
  assert.equal(state.activeOrders.length, 2);
  assert.equal(state.activeOrders[0].quantity, 1);
  console.log('Cart identity, native Item merging, retry and table reload checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
