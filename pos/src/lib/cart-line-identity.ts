/** A preparation has one stable identity, independently of its reusable Item. */
export interface CartLineIdentity {
  id: string;
  custom_flora_arrangement?: string;
  selectedVariant?: { id: string };
  selectedAddons?: Array<{ id: string }>;
  comment?: string;
}

export function getCartLineId(item: CartLineIdentity): string {
  if (item.custom_flora_arrangement) {
    return `flora:${JSON.stringify(item.custom_flora_arrangement)}`;
  }
  const variantId = item.selectedVariant?.id || 'default';
  const addonIds = item.selectedAddons?.map(addon => addon.id).sort().join('-') || 'no-addons';
  const commentStr = item.comment ? item.comment.trim() : '';
  return `${item.id}-${variantId}-${addonIds}-${commentStr}`;
}
