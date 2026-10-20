import type { InventoryItem } from '../inventory/types';
import { request } from '../../lib/api';
import type { Draft } from './state';
export interface ServerDraft {
  id:string;owner_id:string;document_type:'receipt'|'issue';version:number;
  payload:{document_date?:string|null;comment?:string;recipient_employee_id?:string|null;receipt_purpose?:string;external_number?:string|null;items:{inventory_item_id:string;quantity:number}[]};
  status:'draft'|'posted'|'archived';posted_document_id:string|null;created_at:string;updated_at:string;archived_at:string|null;
}
export async function readDraft(draft:ServerDraft):Promise<Draft> {
  const lines=await Promise.all(draft.payload.items.map(async line=>({item:await request<InventoryItem>(`/inventory/items/${line.inventory_item_id}`),quantity:line.quantity})));
  return {lines,employee:draft.payload.recipient_employee_id??'',date:draft.payload.document_date??'',comment:draft.payload.comment??'',purpose:draft.payload.receipt_purpose??'delivery',external:draft.payload.external_number??'',saved:{id:draft.id,version:draft.version}};
}
