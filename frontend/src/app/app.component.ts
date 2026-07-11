import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs/operators';

import { AuthService } from './auth.service';

@Component({
  selector: 'app-root',
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent implements OnInit {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  readonly currentUser = this.authService.currentUser;
  readonly loggedIn = this.authService.loggedIn;
  /** Off-canvas sidebar state (mobile only; the sidebar is always visible on desktop). */
  readonly menuOpen = signal(false);
  title = 'organizer-ui';

  ngOnInit(): void {
    this.authService.getCurrentUser().subscribe();
    // Any navigation dismisses the mobile drawer.
    this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd))
      .subscribe(() => this.menuOpen.set(false));
  }

  toggleMenu(): void {
    this.menuOpen.update((open) => !open);
  }
}
