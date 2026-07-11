import {Tag} from '../tags/tag';

export interface TaskComment {
  id?: number;
  task?: number;
  description: string;
  user?: number;
  user_username?: string;
  timestamp?: Date;
}

export interface Task {
  id?: number;
  title: string;
  description?: string;
  start_date?: Date;
  end_date?: Date;
  completed_date?: Date;
  estimated_time?: number;
  parent_task?: number;
  parent_task_title?: string;
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
  // The recurring template that generated this task (read-only; see add-recurring-tasks).
  template?: number;
  template_title?: string;
  comments?: TaskComment[];
}
