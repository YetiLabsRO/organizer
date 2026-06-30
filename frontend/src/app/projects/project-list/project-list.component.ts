import { ChangeDetectionStrategy, Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ProjectService } from '../project.service';
import { Project } from '../project';
import { ReverseLuminanceColorPipe } from '../../reverse-luminance-color.pipe';

@Component({
  selector: 'app-project-list',
  imports: [RouterLink],
  templateUrl: './project-list.component.html',
  styleUrls: ['./project-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProjectListComponent implements OnInit {
  readonly projects = signal<Project[] | null>(null);

  private luminancePipe: ReverseLuminanceColorPipe = new ReverseLuminanceColorPipe();

  constructor(
    private projectService: ProjectService,
  ) { }

  ngOnInit(): void {
    this.getAllProjects();
  }

  reverseLuminance(color: string) {
    return this.luminancePipe.transform(color);
  }

  getAllProjects(): void {
    this.projectService.getProjects().subscribe(
      (projects: Project[]) => this.projects.set(projects)
    );
  }

  onSelect(project: Project): void {
    return;
  }
}
