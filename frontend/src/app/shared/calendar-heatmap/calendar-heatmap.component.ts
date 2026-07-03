import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { HeatmapDay } from '../../tasks/task-stats.model';

interface Cell {
  date: string;
  count: number;
  level: number; // 0 (none) .. 4 (most)
}

/**
 * GitHub-style calendar heatmap of tasks solved per day. Rendered as a CSS grid (weeks as columns,
 * weekdays as rows) — no charting dependency. Intensity is bucketed 0..4 relative to the busiest day.
 */
@Component({
  selector: 'app-calendar-heatmap',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (cells().length) {
      <div class="heatmap">
        @for (cell of cells(); track cell.date) {
          <span class="cell" [class]="'lvl-' + cell.level" [title]="cell.date + ': ' + cell.count"></span>
        }
      </div>
      <div class="legend">
        <span>Less</span>
        <span class="cell lvl-0"></span>
        <span class="cell lvl-1"></span>
        <span class="cell lvl-2"></span>
        <span class="cell lvl-3"></span>
        <span class="cell lvl-4"></span>
        <span>More</span>
      </div>
    } @else {
      <p class="text-muted mb-0">No completed tasks in range.</p>
    }
  `,
  styles: `
    .heatmap {
      display: grid;
      grid-auto-flow: column;
      grid-template-rows: repeat(7, 1fr);
      grid-auto-columns: 13px;
      gap: 3px;
      overflow-x: auto;
      padding-bottom: 4px;
    }
    .cell {
      width: 13px;
      height: 13px;
      border-radius: 2px;
      background: var(--bs-tertiary-bg, #ebedf0);
    }
    .cell.lvl-1 { background: #9be9a8; }
    .cell.lvl-2 { background: #40c463; }
    .cell.lvl-3 { background: #30a14e; }
    .cell.lvl-4 { background: #216e39; }
    .legend {
      display: flex;
      align-items: center;
      gap: 3px;
      margin-top: 6px;
      font-size: 0.75rem;
      color: var(--bs-secondary-color, #6c757d);
    }
  `,
})
export class CalendarHeatmapComponent {
  readonly data = input<HeatmapDay[]>([]);

  readonly cells = computed<Cell[]>(() => {
    const data = this.data();
    if (!data.length) return [];

    const counts = new Map(data.map((d) => [d.date, d.count]));
    const max = Math.max(...data.map((d) => d.count), 1);
    const dates = data.map((d) => this.parse(d.date)).sort((a, b) => a.getTime() - b.getTime());
    const start = this.mondayOf(dates[0]);
    const end = dates[dates.length - 1];

    const cells: Cell[] = [];
    for (const dt = new Date(start); dt <= end; dt.setDate(dt.getDate() + 1)) {
      const key = this.iso(dt);
      const count = counts.get(key) ?? 0;
      const level = count === 0 ? 0 : Math.min(4, Math.ceil((count / max) * 4));
      cells.push({ date: key, count, level });
    }
    return cells;
  });

  private parse(iso: string): Date {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d);
  }

  private iso(dt: Date): string {
    const m = `${dt.getMonth() + 1}`.padStart(2, '0');
    const d = `${dt.getDate()}`.padStart(2, '0');
    return `${dt.getFullYear()}-${m}-${d}`;
  }

  private mondayOf(dt: Date): Date {
    const copy = new Date(dt);
    const back = (copy.getDay() + 6) % 7; // 0 = Monday
    copy.setDate(copy.getDate() - back);
    return copy;
  }
}
