import { Routes } from '@angular/router';

import { TaskListComponent } from './tasks/task-list/task-list.component';
import { TaskDetailComponent } from './tasks/task-detail/task-detail.component';
import { LoginComponent } from './login/login.component';
import { AuthenticatedGuard } from './authenticated-guard.service';
import { TagListComponent } from './tags/tags-list/tag-list.component';
import { TagDetailComponent } from './tags/tag-detail/tag-detail.component';
import { ProjectListComponent } from './projects/project-list/project-list.component';
import { ProjectDetailComponent } from './projects/project-details/project-detail.component';
import { ProjectFormComponent } from './projects/project-form/project-form.component';
import { TemplateListComponent } from './templates/template-list/template-list.component';
import { TemplateFormComponent } from './templates/template-form/template-form.component';

export const routes: Routes = [
  { path: '', redirectTo: '/tasks/focus', pathMatch: 'full' },
  { path: 'login', component: LoginComponent },
  { path: 'tasks', component: TaskListComponent, canActivate: [AuthenticatedGuard] },
  {
    path: 'tasks/focus',
    loadComponent: () =>
      import('./tasks/priority-focus-list/priority-focus-list.component').then((m) => m.PriorityFocusListComponent),
    canActivate: [AuthenticatedGuard],
  },
  {
    path: 'tasks/stats',
    loadComponent: () => import('./tasks/task-stats/task-stats.component').then((m) => m.TaskStatsComponent),
    canActivate: [AuthenticatedGuard],
  },
  { path: 'tasks/:id', component: TaskDetailComponent, canActivate: [AuthenticatedGuard] },
  { path: 'tags', component: TagListComponent, canActivate: [AuthenticatedGuard] },
  { path: 'tags/create/', component: TagDetailComponent, canActivate: [AuthenticatedGuard] },
  { path: 'tags/:id', component: TagDetailComponent, canActivate: [AuthenticatedGuard] },
  { path: 'projects', component: ProjectListComponent, canActivate: [AuthenticatedGuard] },
  { path: 'projects/edit', component: ProjectFormComponent, canActivate: [AuthenticatedGuard] },
  { path: 'projects/:id', component: ProjectDetailComponent, canActivate: [AuthenticatedGuard] },
  { path: 'projects/:id/edit', component: ProjectFormComponent, canActivate: [AuthenticatedGuard] },
  { path: 'templates', component: TemplateListComponent, canActivate: [AuthenticatedGuard] },
  { path: 'templates/edit', component: TemplateFormComponent, canActivate: [AuthenticatedGuard] },
  { path: 'templates/:id/edit', component: TemplateFormComponent, canActivate: [AuthenticatedGuard] },
];
