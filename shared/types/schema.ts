export interface Endpoint {
  path: string;
  method: string;
  parameters: Parameter[];
  request_body: RequestBody | null;
  responses: Record<string, ResponseInfo>;
}

export interface Parameter {
  name: string;
  location: "query" | "header" | "path" | "cookie";
  required: boolean;
  schema: FieldSchema;
  description?: string;
}

export interface RequestBody {
  content_type: string;
  schema: FieldSchema;
  required: boolean;
}

export interface ResponseInfo {
  description: string;
  schema?: FieldSchema;
}

export interface FieldSchema {
  type: string;
  format?: string;
  nullable?: boolean;
  enum?: string[];
  default?: unknown;
  properties?: Record<string, FieldSchema>;
  items?: FieldSchema;
  min_length?: number;
  max_length?: number;
  minimum?: number;
  maximum?: number;
  pattern?: string;
}
