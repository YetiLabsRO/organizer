import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  effect,
  inject,
  input,
  viewChild,
} from '@angular/core';
import { Chart, ChartConfiguration, registerables } from 'chart.js';

// Register all Chart.js controllers/elements/scales once (bar, line, doughnut, filled areas…).
Chart.register(...registerables);

/**
 * Thin standalone wrapper that renders a Chart.js chart from a `ChartConfiguration` input.
 * Chart.js is used directly (no Angular wrapper) to avoid peer-dependency friction on Angular 21.
 * The host must give this element a height (charts run with `maintainAspectRatio: false`).
 */
@Component({
  selector: 'app-chart-canvas',
  standalone: true,
  template: '<canvas #canvas></canvas>',
  styles: ':host { display: block; position: relative; height: 100%; width: 100%; }',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChartCanvasComponent {
  readonly config = input.required<ChartConfiguration>();
  private readonly canvasRef = viewChild<ElementRef<HTMLCanvasElement>>('canvas');
  private chart?: Chart;

  constructor() {
    effect(() => {
      const config = this.config();
      const ref = this.canvasRef();
      if (!ref) return;
      this.chart?.destroy();
      this.chart = new Chart(ref.nativeElement, config);
    });
    inject(DestroyRef).onDestroy(() => this.chart?.destroy());
  }
}
