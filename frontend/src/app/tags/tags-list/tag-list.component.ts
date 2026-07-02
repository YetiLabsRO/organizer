import { ChangeDetectionStrategy, Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Tag } from '../tag';
import { TagService } from '../tag.service';
import { TagColorPipe } from '../tag-color.pipe';

@Component({
  selector: 'app-tags-list',
  imports: [RouterLink, TagColorPipe],
  templateUrl: './tag-list.component.html',
  styleUrls: ['./tag-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TagListComponent implements OnInit {
  readonly tags = signal<Tag[]>([]);
  selectedTag: Tag | null = null;

  constructor(
    private tagService: TagService,
  ) { }

  ngOnInit(): void {
    this.getTags();
  }

  getTags(): void {
    this.tagService.getTags()
      .subscribe(tags => this.tags.set(tags));
  }

  onSelect(tag: Tag): void {
    this.selectedTag = tag;
  }
}
