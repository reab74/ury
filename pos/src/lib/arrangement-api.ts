import { call } from '@ury/core';

export interface ArrangementItem { name: string; item_name: string; stock_uom: string; available_qty?: number }
export interface ArrangementComponent { item_code: string; item_name?: string; stock_uom?: string; qty: number }
export interface ArrangementValues {
  arrangement_name: string;
  existing_item?: string | null;
  arrangement_type: string;
  selling_price: number;
  notes: string;
  components: Array<{ item_code: string; qty: number }>;
}
export interface ArrangementDraft extends ArrangementValues { name: string; components: ArrangementComponent[] }
export interface SavedArrangement { name: string; arrangement_name: string; status: string; selling_price: number }
export interface ArrangementContext {
  pos_profile: string; currency: string; enabled: number; opening_entry: string | null;
  arrangements: SavedArrangement[];
  finished_item_group: string; finished_item_uom: string;
}
export interface PreparedArrangement {
  arrangement: string;
  stock_entry: string;
  item: { item_code: string; item_name: string; description?: string; rate: number;
    warehouse: string; custom_flora_arrangement: string };
}
const method = 'flora_pos.services.ury_builder.';

export async function arrangementFeature(profile: string): Promise<boolean> {
  const result = await call.get('ury.ury.api.invoice_item_extensions.get_pos_features', { pos_profile: profile });
  return (result.message || []).some((feature: { id: string }) => feature.id === 'flora_arrangements');
}
export async function getArrangementContext(profile: string): Promise<ArrangementContext> {
  return (await call.get(method + 'get_context', { pos_profile: profile })).message;
}
export async function searchArrangementItems(profile: string, query: string, purpose: 'finished' | 'material'): Promise<ArrangementItem[]> {
  return (await call.get(method + 'search_items', { pos_profile: profile, query, purpose })).message;
}
export async function getArrangementDraft(profile: string, name: string): Promise<ArrangementDraft> {
  return (await call.get(method + 'get_draft', { pos_profile: profile, arrangement_name: name })).message;
}
export async function saveArrangementDraft(profile: string, values: ArrangementValues, name?: string): Promise<ArrangementDraft> {
  return (await call.post(method + 'save_draft', { pos_profile: profile, values, arrangement_name: name })).message;
}
export async function prepareArrangement(name: string, opening: string): Promise<PreparedArrangement> {
  return (await call.post(method + 'prepare_for_cart', { arrangement_name: name, opening_entry: opening })).message;
}

export interface MaterialEstimate { warehouse: string; currency: string; rates: Record<string, number | null> }
export async function getArrangementMaterialCosts(profile: string, codes: string[]): Promise<MaterialEstimate> {
  return (await call.post(method + 'estimate_material_costs', { pos_profile: profile, item_codes: JSON.stringify(codes) })).message;
}
