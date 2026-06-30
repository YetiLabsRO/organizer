import { ChangeDetectionStrategy, Component, OnInit, signal } from '@angular/core';
import { NgClass } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TagInputModule } from 'ngx-chips';
import { Task } from '../task';
import { TaskService } from '../task.service';
import { ActivatedRoute, Router } from '@angular/router';
import { TagService } from '../../tags/tag.service';
import { Observable } from 'rxjs';
import { Tag } from '../../tags/tag';
import { ReverseLuminanceColorPipe } from '../../reverse-luminance-color.pipe';
import { Modal } from 'bootstrap';

@Component({
  selector: 'app-task-detail',
  imports: [FormsModule, NgClass, TagInputModule, ReverseLuminanceColorPipe],
  templateUrl: './task-detail.component.html',
  styleUrls: ['./task-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskDetailComponent implements OnInit {
  readonly task = signal<Task | undefined>(undefined);
  editMode: boolean = false;
  deleteModal?: Modal;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private taskService: TaskService,
    public tagService: TagService) {
  }

  ngOnInit(): void {
    const deleteModalElement = document.getElementById('deleteModal') as HTMLElement;
    this.deleteModal = new Modal(deleteModalElement);

    this.getTask();
  }

  toggleEditMode(): void {
    const task = this.task();
    if (this.editMode && task) {
      this.taskService.updateTask(task).subscribe((t: Task) => this.task.set(t));
    }
    this.editMode = !this.editMode;
  }

  toggleCompleted(): void {
    const task = this.task();
    if (task) {
      task.completed = !task.completed;
      this.taskService.updateTask(task).subscribe((t: Task) => this.task.set(t));
    }
  }

  //  TODO: avoid this as it requires public access to TagService from the template
  public searchTags(tagService: TagService): (text: string) => Observable<Tag[]> {
    return (text: string) => tagService.searchTags(text);
  }

  getTask(): void {
    const id = parseInt(this.route.snapshot.paramMap.get('id')!, 10);
    this.taskService.getTask(id)
      .subscribe(task => this.task.set(task));
  }

  deleteTask(): void {
    const task = this.task();
    if (task && task.id) {
      this.taskService.deleteTask(task.id).subscribe(() => {
        this.router.navigate(['tasks']);
      });
    }
  }
}
