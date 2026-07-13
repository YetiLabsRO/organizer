import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs/operators';

import { AuthService } from './auth.service';
import { TaskCreateDrawerComponent } from './tasks/task-create-drawer/task-create-drawer.component';
import { TaskDrawerService } from './tasks/task-drawer.service';

@Component({
  selector: 'app-root',
  imports: [RouterLink, RouterLinkActive, RouterOutlet, TaskCreateDrawerComponent],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent implements OnInit {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  readonly drawer = inject(TaskDrawerService);

  readonly currentUser = this.authService.currentUser;
  readonly loggedIn = this.authService.loggedIn;
  /** Off-canvas sidebar state (mobile only; the sidebar is always visible on desktop). */
  readonly menuOpen = signal(false);
  /** Current URL, tracked so the shell chrome can be hidden on full-screen auth routes. */
  private readonly currentUrl = signal(this.router.url);
  /** "Bare" routes render full-screen without the sidebar/top bar (e.g. login). */
  readonly bare = computed(() => this.currentUrl().startsWith('/login'));
  title = 'organizer-ui';

  ngOnInit(): void {
    this.authService.getCurrentUser().subscribe();
    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((e) => {
        this.menuOpen.set(false); // any navigation dismisses the mobile drawer
        this.currentUrl.set(e.urlAfterRedirects);
      });
  }

  toggleMenu(): void {
    this.menuOpen.update((open) => !open);
  }
}
