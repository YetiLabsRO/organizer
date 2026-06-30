import {Tag} from '../tags/tag';

export interface Task {
  id?: number;
  title: string;
  description?: string;
  start_date?: Date;
  end_date?: Date;
  completed_date?: Date;
  estimated_time?: number;
  parent_task?: number;
  order?: number;
  created_date?: Date;
  changed_date?: Date;
  status?: string;
  completed?: boolean;
  priority?: number;
  owner?: number; // todo: Update to User
  _tags: Tag[];
  tags: number[]; // for writing references
  project?: number; // todo: Update to Project
  for_today?: boolean;
}
