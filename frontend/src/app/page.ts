/** DRF limit/offset pagination envelope returned by paginated list endpoints. */
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
