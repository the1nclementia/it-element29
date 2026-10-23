export interface Page<T> {
  items: T[];
  total: number;
}
export interface RecordEntry {
  id: string;
  version: number;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface Manufacturer extends RecordEntry {
  name: string;
}
export interface Category extends RecordEntry {
  code: string;
  name: string;
}
export interface PrinterModel extends RecordEntry {
  manufacturer_id: string;
  manufacturer_name: string;
  model: string;
}
export interface Department extends RecordEntry {
  code: string;
  name: string;
}
export interface Employee extends RecordEntry {
  full_name: string;
  personnel_number: string;
  department_id: string;
  department_name: string;
}
export interface InventoryItem extends RecordEntry {
  internal_code: string;
  category_id: string;
  category_name: string;
  manufacturer_id: string;
  manufacturer_name: string;
  model: string;
  article: string | null;
  description: string;
  min_stock: number;
  balance: number;
  unit: 'pcs';
  is_low_stock: boolean;
  primary_photo_url: string | null;
}
export interface Photo {
  id: string;
  content_url: string;
  position: number;
  is_primary: boolean;
  width: number;
  height: number;
  mime_type: string;
  size: number;
  archived_at: string | null;
}
export interface Movement {
  id: string;
  document_id: string;
  document_number: string;
  document_type: string;
  delta: number;
  occurred_at: string;
  reversal_of_id: string | null;
}
export interface DocumentLine {
  id: string;
  inventory_item_id: string;
  internal_code: string;
  model: string;
  manufacturer: string;
  quantity: number;
  delta: number;
  line_number: number;
  unit: 'pcs';
}
export interface InventoryDocument {
  id: string;
  number: string;
  document_type: 'receipt' | 'issue' | 'reversal';
  document_date: string;
  created_at: string;
  created_by_id: string;
  created_by_name: string;
  recipient_employee_id: string | null;
  recipient_name: string | null;
  recipient_personnel_number: string | null;
  recipient_department: string | null;
  recipient_building: string | null;
  comment: string | null;
  receipt_purpose: string | null;
  external_number: string | null;
  supplier_name: string | null;
  recipient_room: string | null;
  reversal_of_id: string | null;
  reason: string | null;
  is_cancelled: boolean;
  reversal_id: string | null;
  reversal_number: string | null;
  items: DocumentLine[];
}
export const documentNames: Record<string, string> = {
  receipt: 'Поступление',
  issue: 'Выдача',
  reversal: 'Отмена',
};
