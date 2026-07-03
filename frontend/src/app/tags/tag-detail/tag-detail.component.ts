import { ChangeDetectionStrategy, Component, OnInit, signal } from '@angular/core';
import { NgClass } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ColorPickerDirective } from 'ngx-color-picker';
import { TagService } from '../tag.service';
import { Tag } from '../tag';
import { ActivatedRoute, Router } from '@angular/router';
import { ReverseLuminanceColorPipe } from '../../reverse-luminance-color.pipe';
import { TaskListComponent } from '../../tasks/task-list/task-list.component';
import { MarkdownComponent } from '../../shared/markdown/markdown.component';

@Component({
  selector: 'app-tag-detail',
  imports: [FormsModule, NgClass, ColorPickerDirective, ReverseLuminanceColorPipe, TaskListComponent, MarkdownComponent],
  templateUrl: './tag-detail.component.html',
  styleUrls: ['./tag-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TagDetailComponent implements OnInit {
  readonly tag = signal<Tag | null>(null);
  editMode: boolean = false;
  color: string = '';

  constructor(
    private tagService: TagService,
    private route: ActivatedRoute,
    private router: Router,
  ) { }

  ngOnInit(): void {
    const id = parseInt(this.route.snapshot.paramMap.get('id')!, 10);
    if (!!id) {
      this.getTag(id);
    } else {
      this.tag.set(<Tag>{
        name: '',
        color: '#FFFFFF',
        description: '',
        slug: '',
      });
      this.editMode = true;
    }
  }

  getTag(id: number): void {
    this.tagService.getTag(id)
      .subscribe(tag => this.tag.set(tag));
  }

  toggleEditMode(): void {
    const tag = this.tag();
    if (this.editMode && tag) {
      if (tag.id) {
        this.tagService.updateTag(tag).subscribe((t: Tag) => this.tag.set(t));
      } else {
        this.tagService.createTag(tag).subscribe((t: Tag) => this.tag.set(t));
      }
    }
    this.editMode = !this.editMode;
  }

  updateTagSlug(): void {
    const tag = this.tag();
    if (!tag) return;

    tag.slug = tag.name.toString().toLowerCase()
      .replace(/\s+/g, '-')           // Replace spaces with -
      .replace(/[^\w\-]+/g, '')       // Remove all non-word chars
      .replace(/\-\-+/g, '-')         // Replace multiple - with single -
      .replace(/^-+/, '')             // Trim - from start of text
      .replace(/-+$/, '');
  }
}
