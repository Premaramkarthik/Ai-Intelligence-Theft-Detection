export interface ApiEnvelope<T> {
  status: "success" | "error";
  message: string;
  data: T | null;
  error_code?: string | null;
  timestamp: string;
  meta?: Record<string, unknown> | null;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface PaginatedItems<T> {
  items: T[];
  pagination: PaginationMeta;
}

