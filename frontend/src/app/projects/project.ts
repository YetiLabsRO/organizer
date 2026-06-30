import {Tag} from '../tags/tag';

export interface Project {
  id?: number;
  title: string;
  description?: string;
  slug: string;
  start_date?: Date;
  end_date?: Date;

  _tags: Tag[];
  tags: number[]; // for writing references
}
