import { useEffect, useRef, useState } from 'react';
import { Button, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@ury/ui';
import { parseFrappeError } from '@ury/core';
import { t } from '../i18n';
import { estimatedLineCost, estimatedTotalCost } from '../lib/arrangement-cost';
import { usePOSStore } from '../store/pos-store';
import { arrangementFeature, getArrangementContext, searchArrangementItems, getArrangementDraft,
  saveArrangementDraft, prepareArrangement, getArrangementMaterialCosts } from '../lib/arrangement-api';
import type { ArrangementContext, ArrangementItem, ArrangementComponent, ArrangementValues, MaterialEstimate } from '../lib/arrangement-api';

const inputClass = 'w-full border border-gray-300 rounded-md px-3 py-2 disabled:bg-gray-100';

function ItemSearch({ profile, purpose, query, onQuery, onPick, allowNew, onNew, disabled }: {
  profile: string; purpose: 'finished' | 'material'; query: string; onQuery: (value: string) => void;
  onPick: (item: ArrangementItem) => void; allowNew?: boolean; onNew?: () => void; disabled: boolean;
}) {
  const [items, setItems] = useState<ArrangementItem[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setItems([]); setSearching(true);
    const timer = setTimeout(() => {
      searchArrangementItems(profile, query, purpose).then(rows => {
        if (active) { setItems(rows); setError(''); setSearching(false); }
      }).catch(error => { if (active) { setError(parseFrappeError(error) || t('arrangements.failed')); setSearching(false); } });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [profile, query, purpose]);
  return <div className="space-y-1">
    <input aria-label={t(purpose === 'finished' ? 'arrangements.name' : 'arrangements.material_search')}
      className={inputClass} value={query} disabled={disabled} maxLength={100}
      placeholder={t(purpose === 'finished' ? 'arrangements.name_placeholder' : 'arrangements.material_search')}
      onFocus={() => setOpen(true)} onChange={event => { onQuery(event.target.value); setOpen(true); }} />
    {error && <p role="alert" className="text-red-600 text-sm">{error}</p>}
    {open && !disabled && <div className="border rounded-md max-h-40 overflow-y-auto bg-white">
      {items.map(item => <button type="button" key={item.name} className="block w-full text-start px-3 py-2 hover:bg-blue-50"
        onClick={() => { onPick(item); setOpen(false); }}>
        {item.item_name} <span className="text-xs text-gray-500">{item.name} · {item.available_qty ?? 0} {item.stock_uom}</span>
      </button>)}
      {allowNew && query.trim() && <button type="button" className="w-full text-start border-t px-3 py-2 text-blue-700"
        onClick={() => { onNew?.(); setOpen(false); }}>{t('arrangements.create_new')} “{query.trim()}”</button>}
      {searching && <p className="p-3 text-sm text-gray-500">{t('arrangements.searching_items')}</p>}
      {!items.length && !searching && !error && <p className="p-3 text-sm text-gray-500">{t('arrangements.no_results')}</p>}
    </div>}
  </div>;
}

function ArrangementDialog({ profile, onClose }: { profile: string; onClose: () => void }) {
  const [context, setContext] = useState<ArrangementContext | null>(null);
  const [targetText, setTargetText] = useState('');
  const [target, setTarget] = useState<ArrangementItem | null>(null);
  const [newItem, setNewItem] = useState(false);
  const [kind, setKind] = useState('Flower Bouquet');
  const [price, setPrice] = useState('');
  const [notes, setNotes] = useState('');
  const [components, setComponents] = useState<ArrangementComponent[]>([]);
  const [materialQuery, setMaterialQuery] = useState('');
  const [estimate, setEstimate] = useState<MaterialEstimate | null>(null);
  const [costError, setCostError] = useState('');
  const materialCodes = JSON.stringify([...new Set(components.map(row => row.item_code))].sort());
  useEffect(() => {
    let active = true;
    setEstimate(null); setCostError('');
    const codes: string[] = JSON.parse(materialCodes);
    if (!codes.length) return () => { active = false; };
    const timer = setTimeout(() => {
      getArrangementMaterialCosts(profile, codes).then(value => { if (active) setEstimate(value); })
        .catch(error => { if (active) setCostError(parseFrappeError(error) || t('arrangements.failed')); });
    }, 200);
    return () => { active = false; clearTimeout(timer); };
  }, [profile, materialCodes]);
  const unitCost = (code: string) => {
    const value = estimate?.rates[code];
    return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
  };
  const lineCost = (row: ArrangementComponent) => estimatedLineCost(unitCost(row.item_code), row.qty);
  const totalCost = estimatedTotalCost(components, estimate?.rates || {});
  const money = (value: number | null) => value === null ? t('arrangements.unavailable')
    : `${estimate?.currency || ''} ${value.toFixed(2)}`;
  const [savedId, setSavedId] = useState<string>();
  const [readyId, setReadyId] = useState<string>();
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  // Prepare responses must never land in another tab or company's cart.
  const initialTab = useRef(usePOSStore.getState().activeTabId);

  useEffect(() => {
    let active = true;
    getArrangementContext(profile).then(value => { if (active) setContext(value); })
      .catch(error => { if (active) setError(parseFrappeError(error) || t('arrangements.failed')); });
    return () => { active = false; };
  }, [profile]);

  const values = (): ArrangementValues => {
    if ((!target && !newItem) || !targetText.trim()) throw new Error(t('arrangements.choose_target'));
    if (!Number.isFinite(Number(price)) || Number(price) <= 0 || !components.length ||
        components.some(row => !Number.isFinite(row.qty) || row.qty <= 0)) throw new Error(t('arrangements.invalid_values'));
    return { arrangement_name: targetText.trim(), existing_item: target?.name || null,
      arrangement_type: kind, selling_price: Number(price), notes,
      components: components.map(row => ({ item_code: row.item_code, qty: row.qty })) };
  };
  const report = (error: unknown) => setError(parseFrappeError(error) || (error instanceof Error ? error.message : t('arrangements.failed')));

  const selectSaved = async (name: string) => {
    if (busyRef.current) return;
    if (!name) {
      setSavedId(undefined); setReadyId(undefined); setLocked(false); setTargetText(''); setTarget(null);
      setNewItem(false); setComponents([]); setPrice(''); setNotes(''); setError(''); setMessage('');
      return;
    }
    const selected = context?.arrangements.find(row => row.name === name);
    if (selected?.status === 'Repacked') {
      setReadyId(name); setSavedId(name); setLocked(true); setError(''); return;
    }
    busyRef.current = true; setBusy(true); setError('');
    try {
      const draft = await getArrangementDraft(profile, name);
      setSavedId(draft.name); setReadyId(undefined); setLocked(false);
      setTargetText(draft.arrangement_name); setNewItem(!draft.existing_item);
      setTarget(draft.existing_item ? { name: draft.existing_item, item_name: draft.arrangement_name, stock_uom: '' } : null);
      setKind(draft.arrangement_type); setPrice(String(draft.selling_price)); setNotes(draft.notes || ''); setComponents(draft.components);
    } catch (error) { report(error); }
    finally { busyRef.current = false; setBusy(false); }
  };

  const save = async (prepare: boolean) => {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const state = usePOSStore.getState();
      if (state.posProfile?.name !== profile || state.activeTabId !== initialTab.current) throw new Error(t('arrangements.cart_changed'));
      let name = readyId || savedId;
      if (!locked && !readyId) {
        const draft = await saveArrangementDraft(profile, values(), savedId);
        name = draft.name; setSavedId(name);
      }
      if (!name) throw new Error(t('arrangements.choose_target'));
      if (!prepare) { setMessage(`${t('arrangements.saved')} ${name}`); return; }
      if (!context?.enabled || !context.opening_entry) throw new Error(t('arrangements.preparation_unavailable'));
      // Retain this exact saved ID after any preparation error. A retry must
      // never create a second recipe/Repack after a response was lost.
      setLocked(true); setReadyId(name);
      const prepared = await prepareArrangement(name, context.opening_entry);
      const current = usePOSStore.getState();
      if (current.posProfile?.name !== profile || current.activeTabId !== initialTab.current) throw new Error(t('arrangements.cart_changed'));
      const item = prepared.item;
      await current.addToOrder({ id: item.item_code, name: item.item_name, price: item.rate, quantity: 1,
        item: item.item_code, item_name: item.item_name, item_image: null, image: null, course: '',
        description: item.description, custom_flora_arrangement: prepared.arrangement });
      if (!usePOSStore.getState().activeOrders.some(row => row.custom_flora_arrangement === prepared.arrangement)) {
        throw new Error(t('arrangements.add_failed'));
      }
      onClose();
    } catch (error) { report(error); }
    finally { busyRef.current = false; setBusy(false); }
  };

  return <Dialog open onOpenChange={open => { if (!open && !busyRef.current) onClose(); }}>
    <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
      <DialogHeader><DialogTitle>{t('arrangements.title')}</DialogTitle>
        <DialogDescription>{t('arrangements.intro')}</DialogDescription></DialogHeader>
      {error && <p role="alert" className="rounded bg-red-50 p-3 mx-6 text-red-700">{error}</p>}
      {message && <p role="status" className="text-green-700">{message}</p>}
      {!context ? <p>{t('arrangements.loading')}</p> : <div className="space-y-4 px-6 pb-6">
        {!context.enabled && <p className="bg-amber-50 p-3 rounded text-sm">{t('arrangements.disabled')}</p>}
        {!context.opening_entry && <p className="text-sm text-amber-700">{t('arrangements.no_opening')}</p>}
        <label className="block text-sm font-medium">{t('arrangements.saved_arrangements')}
          <select className={inputClass} value={readyId || savedId || ''} disabled={busy} onChange={event => selectSaved(event.target.value)}>
            <option value="">{t('arrangements.new_arrangement')}</option>
            {savedId && !context.arrangements.some(row => row.name === savedId) && <option value={savedId}>{savedId}</option>}
            {context.arrangements.map(row => <option key={row.name} value={row.name}>
              {row.arrangement_name} · {row.name} · {t(row.status === 'Repacked' ? 'arrangements.prepared' : 'arrangements.draft')}
            </option>)}
          </select>
        </label>
        {savedId && <p className="text-sm text-gray-600">{t('arrangements.reference')}: {savedId}</p>}
        {readyId ? <p className="bg-blue-50 p-3 rounded">{t('arrangements.prepared_help')}</p> : <>
          <div><p className="text-sm font-medium mb-1">{t('arrangements.name')}</p>
            <ItemSearch profile={profile} purpose="finished" query={targetText} disabled={busy || locked} allowNew
              onQuery={value => { setTargetText(value); setTarget(null); setNewItem(false); }}
              onPick={item => { setTarget(item); setTargetText(item.item_name); setNewItem(false); }} onNew={() => { setTarget(null); setNewItem(true); }} />
            <p className="text-sm text-gray-500 mt-1">{t('arrangements.item_filter')}: {context.finished_item_group} · {context.finished_item_uom}</p>
            <p className="text-sm text-gray-500 mt-1">{target ? `${t('arrangements.existing_item')}: ${target.name}` : newItem ? t('arrangements.new_item') : t('arrangements.target_help')}</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm font-medium">{t('arrangements.type')}
              <select className={inputClass} value={kind} disabled={busy || locked} onChange={event => setKind(event.target.value)}>
                <option value="Flower Bouquet">{t('arrangements.flowers')}</option><option value="Chocolate Box">{t('arrangements.chocolate')}</option>
                <option value="Mixed Arrangement">{t('arrangements.mixed')}</option>
              </select></label>
            <label className="text-sm font-medium">{t('arrangements.price')} ({context.currency})
              <input className={inputClass} type="number" min="0" step="any" value={price} disabled={busy || locked} onChange={event => setPrice(event.target.value)} /></label>
          </div>
          <div><p className="text-sm font-medium mb-1">{t('arrangements.materials')}</p>
            <ItemSearch profile={profile} purpose="material" query={materialQuery} disabled={busy || locked}
              onQuery={setMaterialQuery} onPick={item => {
                setComponents(rows => rows.some(row => row.item_code === item.name) ? rows.map(row => row.item_code === item.name ? { ...row, qty: row.qty + 1 } : row)
                  : [...rows, { item_code: item.name, item_name: item.item_name, stock_uom: item.stock_uom, qty: 1 }]); setMaterialQuery('');
              }} />
            <div className="space-y-2 mt-3">{components.map(row => <div key={row.item_code} className="border rounded-md p-2"><div className="flex items-center gap-2">
              <span className="flex-1 text-sm">{row.item_name || row.item_code} <span className="text-gray-500">({row.stock_uom})</span></span>
              <input aria-label={`${t('arrangements.quantity')} ${row.item_name || row.item_code}`} className="border rounded px-2 py-1 w-24" type="number" min="0" step="any" value={Number.isNaN(row.qty) ? '' : row.qty} disabled={busy || locked}
                onChange={event => setComponents(rows => rows.map(value => value.item_code === row.item_code ? { ...value, qty: event.target.value === '' ? NaN : Number(event.target.value) } : value))} />
              <Button variant="outline" disabled={busy || locked} onClick={() => setComponents(rows => rows.filter(value => value.item_code !== row.item_code))}>{t('arrangements.remove')}</Button>
            </div><div className="flex flex-wrap gap-4 text-xs text-gray-600 mt-2">
              <span>{t('arrangements.unit_cost')}: {money(unitCost(row.item_code))}</span>
              <span>{t('arrangements.line_cost')}: {money(lineCost(row))}</span>
            </div></div>)}</div>
            <div className="rounded-md bg-blue-50 p-3 mt-3 text-sm" aria-live="polite">
              <p className="font-semibold">{t('arrangements.total_cost')}: {money(totalCost)}</p>
              <p className="text-xs mt-1">{t('arrangements.cost_help')}{estimate ? ` (${estimate.warehouse})` : ''}</p>
              {costError && <p role="alert" className="text-red-700">{costError}</p>}
            </div>
          </div>
          <label className="block text-sm font-medium">{t('arrangements.notes')}
            <textarea className={inputClass} value={notes} disabled={busy || locked} onChange={event => setNotes(event.target.value)} /></label>
        </>}
        <p className="text-xs text-gray-500">{t('arrangements.stock_help')}</p>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" disabled={busy} onClick={onClose}>{t('arrangements.close')}</Button>
          {!readyId && <Button variant="outline" disabled={busy || locked} onClick={() => save(false)}>{t('arrangements.save_draft')}</Button>}
          <Button disabled={busy || !context.enabled || !context.opening_entry} onClick={() => save(true)}>
            {busy ? t('arrangements.working') : readyId ? t('arrangements.retry_add') : t('arrangements.prepare_add')}
          </Button>
        </div>
      </div>}
    </DialogContent>
  </Dialog>;
}

export function ArrangementLauncher() {
  const profile = usePOSStore(state => state.posProfile?.name);
  const [available, setAvailable] = useState(false);
  const [featureError, setFeatureError] = useState('');
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let active = true;
    setAvailable(false); setOpen(false); setFeatureError('');
    if (profile) arrangementFeature(profile).then(value => { if (active) setAvailable(value); }).catch(error => { if (active) setFeatureError(parseFrappeError(error) || t('arrangements.failed')); });
    return () => { active = false; };
  }, [profile]);
  if (!profile || (!available && !featureError)) return null;
  return <><Button variant="outline" disabled={!available} title={featureError || undefined} onClick={() => setOpen(true)}>{t('arrangements.title')}</Button>
    {open && <ArrangementDialog key={profile} profile={profile} onClose={() => setOpen(false)} />}</>;
}
