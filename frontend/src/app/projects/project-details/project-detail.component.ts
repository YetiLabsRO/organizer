import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { of } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';

import { ProjectService } from '../project.service';
import { Project } from '../project';
import { TagColorPipe } from '../../tags/tag-color.pipe';
import { MarkdownComponent } from '../../shared/markdown/markdown.component';
import { TaskListComponent } from '../../tasks/task-list/task-list.component';
import { TaskDrawerService } from '../../tasks/task-drawer.service';

/**
 * A project's workspace: its own metadata on top, its tasks below.
 *
 * The task list is the app's regular one (rows, filters, search, quick-add, live sync) scoped to
 * this project, and "New Task" opens the shared create drawer pre-filled with it — so everything
 * added from here lands in the project without the user selecting it.
 */
@Component({
  selector: 'app-project-details',
  imports: [RouterLink, TagColorPipe, MarkdownComponent, TaskListComponent],
  templateUrl: './project-detail.component.html',
  styleUrls: ['./project-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProjectDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly projectService = inject(ProjectService);
  private readonly drawer = inject(TaskDrawerService);
  private readonly destroyRef = inject(DestroyRef);

  readonly project = signal<Project | null>(null);
  readonly loading = signal(true);
  /** The id resolved to nothing — a deleted project, or a hand-typed URL. */
  readonly notFound = signal(false);

  ngOnInit(): void {
    // Driven by the param map rather than a snapshot: the router reuses this component when
    // navigating from one project straight to another, and that has to reload the page.
    this.route.paramMap
      .pipe(
        switchMap((params) => {
          this.loading.set(true);
          this.notFound.set(false);
          this.project.set(null);
          // Swallowed here (not on the outer stream) so a failed fetch can't end the subscription
          // and leave later navigations dead.
          return this.projectService.fetchProject(params.get('id')!).pipe(catchError(() => of(null)));
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((project) => {
        this.project.set(project);
        this.notFound.set(project === null);
        this.loading.set(false);
      });
  }

  /** Open the app-wide create drawer with this project pre-selected. */
  newTask(): void {
    const id = this.project()?.id;
    if (id == null) return;
    this.drawer.openDrawer({ project: id });
  }
}
