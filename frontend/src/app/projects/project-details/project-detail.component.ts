import { ChangeDetectionStrategy, Component, OnInit, signal } from '@angular/core';
import { RouterLink, ActivatedRoute, Router } from '@angular/router';
import { ProjectService } from '../project.service';
import { Project } from '../project';
import { ReverseLuminanceColorPipe } from '../../reverse-luminance-color.pipe';

@Component({
  selector: 'app-project-details',
  imports: [RouterLink, ReverseLuminanceColorPipe],
  templateUrl: './project-detail.component.html',
  styleUrls: ['./project-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProjectDetailComponent implements OnInit {
  readonly project = signal<Project | null>(null);

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private projectService: ProjectService
  ) { }

  ngOnInit(): void {
    this.getProject();
  }

  getProject(): void {
    const id = parseInt(this.route.snapshot.paramMap.get('id')!, 10);
    this.projectService.getProject(id)
      .subscribe(project => this.project.set(project));
  }
}
